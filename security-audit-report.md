# Night Diary V2 安全审计报告

- 审计时间：2026-10-28
- 范围：本仓库全部代码（server/、src/、desktop/、部署配置）
- 方法：架构梳理 → 分组攻击面审查（认证与访问控制 / 注入向量 / 外部交互 / 敏感数据处理）→ 每条发现追踪端到端代码路径 → 仅保留可论证可利用性且严重度 ≥ 中危的发现
- 结论：**确认 2 个高危 + 4 个中危漏洞**（具备端到端利用路径）

---

## 高危

### H1. 生产默认 JWT / 模型密钥为公开已知值，可伪造任意用户身份并解密全部 LLM API Key

- **位置**：[docker-compose.yml:59-60](file:///workspace/docker-compose.yml#L59-L60)、[docker-compose.yml:103-104](file:///workspace/docker-compose.yml#L103-L104)、[.env.example:8-9](file:///workspace/.env.example#L8-L9)
- **攻击者画像**：外部匿名攻击者（无需任何凭据）
- **可控输入**：无需输入；仅需 `docker compose up` 未覆盖 `JWT_SECRET_KEY`/`MODEL_KEY_SECRET` 环境变量（默认部署即如此）
- **代码路径**：`docker-compose.yml` 将 `JWT_SECRET_KEY` 恒赋值为公开默认值 `change-me-in-production-min-32-chars` → [config.py:143-147](file:///workspace/server/app/config.py#L143-L147) 读取为非空 → [infrastructure/security.py:48-52](file:///workspace/server/app/infrastructure/security.py#L48-L52) 的 fail-fast 永不触发 → [infrastructure/auth.py:64-65](file:///workspace/server/app/infrastructure/auth.py#L64-L65) 用该公开密钥签发 JWT。同理 `MODEL_KEY_SECRET` 公开默认值经 [security.py:32-46](file:///workspace/server/app/infrastructure/security.py#L32-L46) 作为 Fernet 密钥来源
- **影响**：
  - 伪造任意用户 JWT：攻击者注册账号得知自身 `sub=id`，用公开密钥签发 `{"sub": "<任意id>"}` 的 HS256 token，即可以任意用户身份调用全部 API（含 admin 常用 id=1），读取/篡改任意用户日记、对话、记忆
  - 解密全部加密存储的 LLM API Key（`api_key_encrypted` 字段），泄露用户配置的第三方密钥
- **修复建议**：去掉默认值（改为必填并在缺失时 fail-fast）；`docker compose up` 时强校验 `JWT_SECRET_KEY` 长度 ≥ 32 且非示例值；文档与 `docker-compose.yml` 中删除公开示例密钥

### H2. `/api/v1/dev/*` 全线未认证，匿名可读取任意用户对话/日记原文与 MCP 调用参数，并可删除记录

- **位置**：[server/app/api/v1/dev.py:1-7](file:///workspace/server/app/api/v1/dev.py#L1-L7)（docstring 明言不要求认证）、[router.py:43](file:///workspace/server/app/api/v1/router.py#L43)、[dev.py:147-178](file:///workspace/server/app/api/v1/dev.py#L147-L178)、[dev.py:184-197](file:///workspace/server/app/api/v1/dev.py#L184-L197)、[dev.py:203-215](file:///workspace/server/app/api/v1/dev.py#L203-L215)、[dev.py:482-500](file:///workspace/server/app/api/v1/dev.py#L482-L500)
- **攻击者画像**：外部匿名攻击者（无需 token）
- **可控输入**：`GET /api/v1/dev/traces`（分页枚举，含 `user_id`）、`GET /api/v1/dev/traces/{trace_id}`（返回完整 `trace_json`）、`GET /api/v1/dev/mcp/calls`（按 user_id 过滤读取 MCP 工具入参/结果快照，可能含工具参数中的密钥）、`DELETE /api/v1/dev/traces/{trace_id}`
- **代码路径**：对话/日记流程把用户原文写入 trace span 的 `input_snapshot`（[conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py)），经 `persist_trace` 落库 `pipeline_traces.trace_json`；`dev.py` 路由仅依赖 `DbDep`/`ContainerDep`（无 `CurrentUserDep`），`router.py:43` 无条件挂载、无 `app_env` 门控；[dev.py:192](file:///workspace/server/app/api/v1/dev.py#L192) 直接 `json.loads(row.trace_json)` 原样返回
- **影响**：匿名读取任意用户日记/对话原文（PII）与提示词快照、MCP 工具调用参数（可能含 API Key）；任意删除 trace 记录；`POST /dev/quality-scan` 可触发 LLM 扫描消耗资源
- **修复建议**：为 dev 路由统一加 `CurrentUserDep`（或 `app_env` 生产门控 + 仅管理员角色）；`/traces/{id}` 与 `/mcp/calls` 增加归属校验；默认关闭 trace 持久化或对 `trace_json` 脱敏

---

## 中危

### M1. 未认证 SSRF 探测端点：`POST /api/v1/models/test-connection` 可扫描内网/本机服务

- **位置**：[models.py:42-51](file:///workspace/server/app/api/v1/models.py#L42-L51)、[model_service.py:161-210](file:///workspace/server/app/services/model_service.py#L161-L210)、[url_guard.py:105-136](file:///workspace/server/app/shared/url_guard.py#L105-L136)、[config.py:155-160](file:///workspace/server/app/config.py#L155-L160)
- **攻击者画像**：外部匿名攻击者
- **可控输入**：请求体 `base_url`（任意 http/https URL）+ 攻击者自己的 `api_key` + `model_name`
- **代码路径**：`test_model_connection` 无任何认证依赖 → `validate_model_connection` → `validate_outbound_url(base_url, allow_private=True)`（仅拦截云元数据/链路本地，[url_guard.py:38-55](file:///workspace/server/app/shared/url_guard.py#L38-L55)；回环/内网默认放行）→ 对 `{base_url}/models` 与 chat 探测端点发起带 `Authorization` 头的 HTTP 请求，把 200/401/405/400/超时等区分性响应回传攻击者（[model_service.py:176-206](file:///workspace/server/app/services/model_service.py#L176-L206)）
- **影响**：无授权内网端口/服务指纹扫描（可探测本机 Redis 6379、MySQL 3306、Neo4j 等）；攻击者可用任何内网主机目标做 HTTP 探测。另有延伸向量：已认证用户配置内网 `base_url` 后，[llm_factory.py:234-252](file:///workspace/server/app/shared/llm_factory.py#L234-L252) 请求时不再校验 URL，日记全文可被发往自配主机
- **修复建议**：`test-connection` 增加认证依赖；对 `allow_private_model_hosts` 默认改为 False（仅显式白名单放行本机 Ollama 等）；实际 LLM 请求路径同样接入 `validate_outbound_url`

### M2. 进程级记忆层 first-user-wins，多用户部署跨租户情景记忆泄漏/串扰

- **位置**：[container.py:133-166](file:///workspace/server/app/services/container.py#L133-L166)（"the first user_id wins"）、[conversation_ai_service.py:307-323](file:///workspace/server/app/services/conversation_ai_service.py#L307-L323)（`retrieve_relevant` 无二次用户过滤）、[episodic.py](file:///workspace/server/app/domain/memory/episodic.py)（读写绑定 `self._user_id`）
- **攻击者画像**：多用户部署中，触发 AI 功能的用户 B（相对于先触发用户 A）
- **可控输入**：正常使用会话/日记功能
- **代码路径**：首个触发 AI 栈的用户 A 初始化 `container.episodic_memory` 单例并绑定 `user_id=A`；用户 B 的会话检索 `_format_episodic_memories` 时直接读该单例（不按 B 过滤），B 的上下文混入 A 的情景记忆（含摘要/情绪/洞察），B 的新记忆按 `self._user_id=A` 写入 A
- **影响**：跨租户 PII 泄漏（A 的记忆进入 B 的 LLM 上下文与回复）与记忆污染写入；单用户部署无此风险
- **修复建议**：检索与写入均显式携带当前 `user_id` 过滤；将记忆层按用户实例化而非进程单例；在 `_ensure_memory_layers_locked` 后校验请求用户与单例绑定用户一致

### M3. 注册用户枚举 + 预注册账户接管（无邮箱验证、无找回流程）

- **位置**：[auth.py:51-65](file:///workspace/server/app/api/v1/auth.py#L51-L65)（注册已存在邮箱返回 409）、[auth.py:68-84](file:///workspace/server/app/api/v1/auth.py#L68-L84)（登录统一报错）、[models/user.py:27](file:///workspace/server/app/infrastructure/models/user.py#L27)（`is_active` 默认 True）
- **攻击者画像**：外部匿名攻击者
- **可控输入**：任意邮箱地址
- **代码路径**：`POST /register` 对已注册邮箱返回 `EmailAlreadyExistsError`（409），与登录的通用错误可区分 → 枚举任意邮箱是否注册。注册无激活/邮箱验证，`is_active` 默认 True；全库无密码重置端点
- **影响**：用户枚举（PII 面）；对未注册的目标邮箱，攻击者可抢先注册占据该身份，受害者无法找回（预注册账户接管，需时间窗）
- **修复建议**：注册失败返回与登录一致的通用错误；增加邮箱验证（激活链接）或一次性验证码；补充密码重置流程

### M4. 部署配置暴露基础设施端口且默认口令公开

- **位置**：[docker-compose.yml:5-10](file:///workspace/docker-compose.yml#L5-L10)（MySQL 3306 暴露 + `nightdiary_root`/`nightdiary_pass` 默认口令）、[docker-compose.yml:20-23](file:///workspace/docker-compose.yml#L20-L23)（Redis 6379 无认证暴露）、[docker-compose.yml:33-40](file:///workspace/docker-compose.yml#L33-L40)（Neo4j 7474/7687 暴露 + 固定口令 `nightdiary_neo4j`）、[config.py:104-105](file:///workspace/server/app/config.py#L104-L105)（neo4j 默认口令 "neo4j"）
- **攻击者画像**：可访问部署主机网络的攻击者（LAN / 同网段）
- **可控输入**：直连端口，使用仓库内公开的默认口令
- **代码路径**：所有口令均以公开默认值写入仓库并在 compose 中直接使用（NEO4J_PASSWORD 固定 `nightdiary_neo4j`，不可 env 覆盖）
- **影响**：攻击者直连 MySQL/Neo4j 读写全部用户数据（绕过 JWT 认证）、访问 Redis 缓存与 JWT 黑名单；默认口令公开使利用确定
- **修复建议**：`ports` 仅在需要时暴露（默认 `127.0.0.1:` 绑定或移除）；所有口令改强随机默认 + env 覆盖 + 启动校验；Redis 开启 requirepass；Neo4j 口令参数化

---

## 排除项（已核查，未确认中等及以上可利用性）

- **注入向量**：bm25 为纯内存实现、无原始 SQL 拼接；`subprocess` 均为参数列表、无 `shell=True`、无用户输入；上传/导出路径全部由服务端 UUID 决定，无路径穿越；自定义技能为纯文本，无 eval/exec 代码执行
- **openai_compat（`/v1/*`）**：chat/completions 与 /models 均带 `CurrentUserDep`，未绕过认证
- **JWT**：`decode` 使用单一算法白名单（HS256），无 alg 混淆面
- **API Key 存储**：`encrypt_api_key` 加密落库，响应不回传明文
- **提示注入**：工具输出（含 MCP）经 untrusted 围栏；自定义技能指令为自注入（用户仅影响自身会话），关键词审查可被混淆绕过但无跨租户/提权路径
- **Web 搜索**：仅请求固定域名，无 SSRF 变体
- 低危备注（未计入）：`/models/download/*` 无认证（仅触发模型下载的 DoS/出网消耗）；前端 token 存 localStorage（当前无 XSS sink）；llm_call_logs 持久化对话原文（数据静止态风险，无越权读取 API）；Fernet 密钥单次 SHA256 派生（叠加 H1 默认密钥时失效）

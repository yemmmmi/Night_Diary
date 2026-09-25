# NightDiary 代码仓库安全审计报告

- 审计日期：2026-09-25
- 范围：`server/app`（FastAPI 后端）+ `src`（Vue 前端）+ 部署配置（docker-compose / .env.example / nginx.conf）
- 方法：架构梳理 → 四类攻击面系统性核查 → 端到端利用路径追踪 → 源码级复核（仅保留已确认可利用项）

## 严重度汇总

| 严重度 | 数量 | 关键词 |
|---|---|---|
| 严重 (Critical) | 1 | 硬编码默认密钥 → 账户接管 + 密钥解密 |
| 高危 (High) | 2 | 未授权 dev 接口泄露 PII；未授权 SSRF |
| 中危 (Medium) | 5 | 跨用户密钥解析；LLM 日志明文 PII；账号枚举；登录无限流/弱口令；prompt 注入仅标记不阻断 |

---

## 严重 (Critical)

### C1. docker-compose 生产模式硬编码默认 JWT 与 Fernet 密钥 → 任意账户接管 + 全量解密钥

**攻击者画像**：可访问后端（容器外 `8000`，前端 `80` 反代 `/api/`）的未认证网络攻击者。

**可控输入向量**：`Authorization: Bearer <自制JWT>`，无需任何凭据；或直接使用公开密钥解密已落库数据。

**确切代码路径**：
1. [docker-compose.yml](file:///workspace/docker-compose.yml#L55-L60)：backend 明确设置 `APP_ENV=production`，且 `JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-me-in-production-min-32-chars}`、`MODEL_KEY_SECRET=${MODEL_KEY_SECRET:-change-me-model-key-min-16c}` 均带**公开的、可预测的默认值**（worker `L103-104` 相同；`NEO4J_PASSWORD=nightdiary_neo4j` L70、数据库口令均有默认值）。
2. [auth.py](file:///workspace/server/app/infrastructure/auth.py#L35-L45)：`resolve_jwt_secret` 直接采用该已公开 secret 做 HS256 签名。
3. [deps.py](file:///workspace/server/app/api/deps.py#L44-L57)：`get_current_user` 用同一密钥解码 `sub`→`int(user_id)`→`db.get(UserRow,...)`，仅校验 `is_active`。user_id 为自增整数（首用户=1）。
4. [security.py](file:///workspace/server/app/infrastructure/security.py#L26-L29,L62-L66)：`get_fernet` 对非 44 字符密钥走 `_derive_fernet_key` = `base64.urlsafe_b64encode(sha256(secret))`——对**公开弱口令**做无盐、单轮 sha256 派生得到确定 Fernet 键；`decrypt_api_key`（L73）用它解密所有 `model_providers.api_key_encrypted`。

**影响**：
- 攻击者用已知 secret 本地签发 `{"sub":"<任意user_id>","exp":未来}` 即可**完全冒充任意用户**，读取/导出所有日记、会话、记忆卡、计划等 PII。
- 同时可用公开 `MODEL_KEY_SECRET` 派生 Fernet 键，**解密所有用户保存的第三方 LLM / embedding API key**（对数个 key 全量明文提取）。

**修复建议**：
- 从 `docker-compose.yml` 与 `.env.example` 移除可用默认密钥；生产未显式设置时由 `Settings` 对 `jwt_secret_key`/`model_key_secret` 采用 fail-fast（与 `security.py` 对 `model_key_secret` 的逻辑对齐，避免 compose 用默认值绕过）。
- Fernet 口令改用带盐 KDF（PBKDF2/bcrypt）并强制最小熵，而非裸 sha256 无盐派生。

---

## 高危 (High)

### H1. 未认证的 `/api/v1/dev/*` 端点跨用户泄露私密日记 / 对话 PII 并支持破坏性操作

**攻击者画像**：可访问到后端的**零认证**外部攻击者。

**可控输入向量**：`GET /api/v1/dev/traces`、`GET /api/v1/dev/traces/{id}`、`DELETE /api/v1/dev/traces/{id}`、`GET /api/v1/dev/mcp/calls`、`POST /api/v1/dev/quality-scan` 等，无需 token。

**确切代码路径**：
1. [router.py](file:///workspace/server/app/api/v1/router.py#L39)：`dev.router` 无条件挂载到公开 `/api/v1` 前缀；[main.py](file:///workspace/server/app/main.py#L219-L224) 仅挂 CORS 中间件，无全局鉴权。
2. [dev.py](file:///workspace/server/app/api/v1/dev.py#L147-L197)：`list_traces` / `get_trace_detail` 仅依赖 `DbDep`，返回**所有用户**的 `pipeline_traces.trace_json`（含 `user_id`、`input_snapshot` 中的日记/对话原文快照）；`DELETE`（L203）可任意删除；`/dev/mcp/calls`（L482）可按任意 `user` 过滤 MCP 日志；`/dev/quality-scan`（L447）触发 LLM 抽样。
3. [graph_nodes.py](file:///workspace/server/app/domain/agents/graph.py) / [conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L473-L476)：span 的 `input_snapshot={"raw_text": content}` 将用户原文持久化进 trace。

**影响**：零认证跨租户读取私密日记/对话（信息泄露，高危）、越权删除 trace（完整性）、无授权触发 LLM 消耗（资源，可用性）。`curl /api/v1/dev/traces` 即返回数据；另可获取目标 `user_id`，放大 C1 的 JWT 伪造。

**修复建议**：为 `/dev/*` 与 `/models/download/*` 挂载 `CurrentUserDep` 并按 `user_id` 过滤；生产环境默认不注册这些调试路由（仅 `APP_ENV==development` 下开放）。

### H2. 未认证 SSRF —— `POST /api/v1/models/test-connection`

**攻击者画像**：零认证的远程攻击者（容器内以 `0.0.0.0:8000` 暴露，见 main.py）。

**可控输入向量**：JSON body 中的 `base_url`、`api_key`、`model_name`，全部攻击者可控。

**确切代码路径**：
1. [models.py](file:///workspace/server/app/api/v1/models.py#L42-L51)：`test_model_connection` **无 `CurrentUserDep`**（同文件其余端点均有）。
2. [model_service.py](file:///workspace/server/app/services/model_service.py#L105-L151)：`validate_model_connection` 仅校验 `base_url.startswith(("http://","https://"))`（L111），无主机白名单；用直连客户端（`trust_env=False`）向 `{base_url}/models` GET、`{base_url}/v1/chat/completions` POST，`Authorization: Bearer <attacker_api_key>` 由请求方控制。
3. 响应状态码/超时回显给攻击者，可用于差分探测。

**影响**：服务端代攻击者向内网（`169.254.169.254`、`127.0.0.1`、内部 `mysql`/`redis`/`neo4j`）发起任意 HTTP 连接——内网侦察、向内部服务发送受控请求；CORS 不拦截服务端直连。

**修复建议**：为该端点加 `CurrentUserDep` 并限定仅测试自己配置的 provider；在 `validate_model_connection` 实施出站 SSRF 防护（拒绝 RFC1918/回环/链路本地/云元数据地址），强制经凭证代理出站，对 `base_url` 做 scheme+主机名校验。

---

## 中危 (Medium)

### M1. LLM 分层解析未按 user_id 隔离 → 跨用户使用 / 解密他人 LLM API key 的计费·配额盗用

**攻击者画像**：任一已认证用户（多租户部署下）。

**可控输入向量**：任意触发 AI 的请求（聊天/日记/技能）。

**确切代码路径**：
1. [container.py](file:///workspace/server/app/services/container.py#L376-L381)：`_llm_for_tier` 调用 `resolve_llm_clients_by_tier(...)` **未传 user_id**。
2. [llm_factory.py](file:///workspace/server/app/shared/llm_factory.py#L91-L118)：`resolve_by_tier` 在提供 `user_id=None` 时查询**全部用户**的 `model_providers`，且当 active 集合为空时回退查询**所有用户**的 provider（L112-118），再经 `create_from_provider`→`decrypt_api_key` 解密构建真实 LLM 客户端。

**影响**：用户 A 的 AI 请求命中并消费用户 B 存储的私有 LLM key（账单/配额盗用），跨租户误用私有 provider。不回显 key 字符串，故评定中危。

**修复建议**：所有成品路径统一透传请求用户的 `user_id`；删除无 user_id 的跨用户回退。

### M2. LLM 调用日志明文落库完整 prompt / response（含日记 PII）

**攻击者画像**：能读取数据库（叠加 C1 密钥泄露即全可读）或间接访问 `llm_call_logs` 的内部/运维人员。

**确切代码路径**：[tracing_llm.py](file:///workspace/server/app/shared/tracing_llm.py#L104-L125)：`_record` 将 `prompt[:2000]` 与 `response[:2000]` 写入 LLM 调用日志，而 prompt 含拼装的日记正文/检索记忆原文；[llm_call_tracer.py](file:///workspace/server/app/infrastructure/llm_call_tracer.py#L30-L31) 落表 `llm_call_logs.prompt/response`。叠加 docker-compose 将 MySQL/Redis/Neo4j 端口映射到公网（docker-compose.yml L10/L23/L39-40）。

**影响**：高度敏感日记 PII 在库中明文留存、无脱敏。
**修复建议**：日志/trace 存储对 prompt 脱敏（截断+过滤 PII）；生产不向公网开放 DB/缓存端口。

### M3. 注册接口账号枚举

**攻击者画像**：外部未认证攻击者。
**可控输入向量**：`POST /api/v1/auth/register` 的 `email`。
**路径**：[auth.py](file:///workspace/server/app/api/v1/auth.py#L51-L65)：邮箱已存在返回 409 `EmailAlreadyExistsError`，可用返回 201。
**影响**：确认账号存在性，为爆破/钓鱼提供输入。
**修复**：对已存在邮箱返回同构响应；注册/登录加限流。

### M4. 登录无限流 + 弱口令策略

**攻击者画像**：外部攻击者（结合 M3 在线/离线爆破）。
**可控输入向量**：`POST /api/v1/auth/login`（OAuth2 form）。
**路径**：[auth.py](file:///workspace/server/app/api/v1/auth.py#L68-L84)：无任何限流/退避；`RegisterRequest.password` 仅 `min_length=6`（auth.py:28）。
**影响**：结合已枚举邮箱可无限次试密码；弱口令易被破解。
**修复**：IP+账号维度限流与指数退避；提升密码强度策略。

### M5. Prompt 注入检测仅标记不阻断 + 未隔离拼接进可调用工具的提示

**攻击者画像**：已认证用户主攻自身会话（自攻击）；当配置宽权限 MCP 工具或第三方内容可入 prompt 时升级为可利用。
**可控输入向量**：用户消息、被引用的日记、RAG 检索片段。
**路径**：
1. [input_preprocessor.py](file:///workspace/server/app/services/ai/input_preprocessor.py#L195-L248)：正则命中 `has_injection` 但 `working_text` 原样下传，仅 `logger.warning`。
2. [prompts.py](file:///workspace/server/app/services/ai/prompts.py#L31-L46)：`{pinned_diaries}`/`{retrieved_diaries}`/`{user_message}` 无分界并入可工具调用的提示。
**影响**：诱导代理执行非预期工具调用/信息外泄（前置条件存在；默认单用户自我影响为主，评定中危）。
**修复**：将注入命中降级阻断或净化；对拼入 prompt 的外部文本做隔离/限定；工具调用前加意图校验。

---

## 已核查但未确认（明确排除）

- **原始 SQL 注入**：应用层 CRUD 均走 SQLAlchemy ORM / 参数化；唯一 `text()` 动态 SQL 在迁移/运维代码，标识符为硬编码，值用绑定参数。
- **Shell 命令注入**：MCP stdio 子进程命令来自环境变量 `MCP_STDIOS`（config.py），仓库无任何 API 可改写该配置，非攻击者可控输入。
- **文件路径穿越**：无用户可控文件名进入文件系统；导出/导入为 DB JSON 流，不写文件。
- **模板注入**：全仓无 Jinja2/模板渲染。
- **Webhook 处理器**：不存在。
- **HTTP 层水平越权（IDOR）**：所有业务资源路由的 `user_id` 均取自 `CurrentUserDep`，服务层按 `user_id` 过滤，正常认证链路无跨用户读写。
- **JWT alg=none / 弱签名**：`decode` 显式限 `algorithms=["HS256"]`。

---

## 处置优先级建议

1. 立即修复 **C1**（移除默认密钥 + 生产 fail-fast）与 **H1**（dev 路由鉴权/环境隔离）。
2. 高优先修复 **H2**（SSRF 出站防护 + 鉴权）。
3. 随迭代修复 **M1-M5**（user_id 隔离、日志脱敏、限流与口令策略、prompt 注入防护）。
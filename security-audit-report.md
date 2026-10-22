# 夜记（night-diary）代码仓库安全审计报告

- 审计日期：2026-10-22
- 审计范围：server/（FastAPI 后端）、src/（Vue3 前端）、desktop/（Electron 桌面端）、部署配置（docker-compose.yml / nginx.conf / .env.example）
- 方法：架构梳理 → 四组攻击面审计（认证与访问控制 / 注入向量 / 外部交互 / 敏感数据处理）→ 对候选发现逐条复核端到端利用路径
- 结论：确认 **3 个 Critical、4 个 High、3 个 Medium** 可论证漏洞；注入向量（SQL/Shell/路径穿越/反序列化）未发现可证明漏洞。

---

## Critical

### C1. 未认证 dev API 泄露全部用户私密内容，并支持实时监听与删除

- **位置**：`server/app/api/v1/dev.py:1-6`（模块明言 "do not require authentication"）、`:147`（list_traces）、`:184`（get_trace_detail）、`:203`（delete_trace）、`:221`（SSE 实时流）、`:447`（quality-scan）
- **攻击者画像**：外部未认证（Docker/公网部署下任意可达 8000/80 端口的攻击者）
- **可控输入向量**：`GET /api/v1/dev/traces?page=&scenario=&status=&ref_id=` 分页枚举；`GET /dev/traces/{id}` 取全文；`GET /dev/traces/{id}/stream` 实时订阅；`DELETE /dev/traces/{id}` 删除；`POST /dev/quality-scan` 触发 LLM 判分
- **代码路径**：
  1. 每条对话/日记分析无条件 `persist_trace`（`conversation_ai_service.py:1217-1228` 的 `finally` 块），span 快照含用户消息原文、检索 query、检索到的日记与回复（`pipeline_trace.py:85-112`）；
  2. `list_traces`（`dev.py:159`）`db.query(PipelineTraceRow)` **无 user 过滤**，返回所有用户 trace 摘要；
  3. `get_trace_detail`（`dev.py:187-196`）返回完整 `trace_json`；`stream`（`dev.py:262-298`）订阅 TraceEventBus 实时流；
  4. `/dev/mcp/calls`（`dev.py:482-500`）返回 MCP 调用参数/结果快照，支持 `user=` 按用户遍历。
- **影响**：全用户日记/对话/检索上下文/AI 回复越权泄露；实时监听进行中会话；匿名删除 trace（完整性）；匿名触发 quality-scan 消耗 LLM 配额（成本 DoS）。
- **修复建议**：dev 路由挂 `CurrentUserDep` 并强制按 `user_id` 过滤（或独立开发者令牌）；trace_json 落库前对快照脱敏；生产环境默认不启用 dev 路由。

### C2. 未认证 SSRF：`POST /api/v1/models/test-connection` 可扫描/请求内网

- **位置**：`server/app/api/v1/models.py:42-51`（路由无任何认证依赖）→ `server/app/services/model_service.py:161-210`（`validate_model_connection`）→ `server/app/shared/url_guard.py:105-136` → `server/app/config.py:155-160`（`allow_private_model_hosts` 默认 `True`）
- **攻击者画像**：外部未认证
- **可控输入向量**：`body.base_url`（任意 http/https 目标，如 `http://172.16.0.x`、`http://127.0.0.1:PORT`）、`body.api_key`（自填，随请求发送）
- **代码路径**：
  ```
  POST /api/v1/models/test-connection {"base_url":"http://<内网IP>:<port>"}
   → model_service.validate_model_connection()（model_service.py:161）
   → validate_outbound_url(allow_private=True)（url_guard.py:169）
      仅硬编码拦截 169.254.0.0/16、fe80::/10 等元数据/链路本地段（url_guard.py:88-101），
      RFC1918/回环在默认配置下全部放行
   → httpx GET {base}/models、POST {base}/v1/chat/completions（model_service.py:137-158，含可控 Authorization 头与 JSON body）
   → 错误消息回显状态码与 URL（model_service.py:185、204、206）
  ```
- **影响**：内网端口/服务扫描 oracle（响应码回显）；向内网 HTTP 服务发送受控 POST 原语；同 Docker 网络内其他容器与宿主机回环服务可达。
- **修复建议**：路由挂 `CurrentUserDep`；test-connection 强制 `allow_private=False`；错误消息不回显测试 URL；限频。

### C3. 公开弱默认 JWT/Fernet 密钥 → 任意令牌伪造、账户接管与加密 API Key 解密

- **位置**：`docker-compose.yml:59-60`（backend）、`:103-104`（worker）`JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-me-in-production-min-32-chars}`、`MODEL_KEY_SECRET=${MODEL_KEY_SECRET:-change-me-model-key-min-16c}`；`server/app/config.py:143-147`（`jwt_secret_key` 无强度校验）；`server/app/infrastructure/auth.py:43-45`（`resolve_jwt_secret` 直接采用）；`server/app/infrastructure/security.py:26-29,41-59`（Fernet 密钥派生自 `sha256(已知字符串)`）
- **攻击者画像**：外部未认证（针对按默认 compose 部署的实例）
- **可控输入向量**：无——默认值公开已知（提交在仓库中），可离线计算
- **代码路径**：
  ```
  攻击者用已知默认值 change-me-in-production-min-32-chars
   → 自签 HS256 JWT {"sub":"<任意user_id>","exp":…,"jti":…}
   → GET /api/v1/auth/me（或任意业务端点）Bearer <伪造token>
   → deps.py:44-59 decode_access_token 通过、int(user_id) 命中用户 → 以任意用户身份访问全部数据
  同源：MODEL_KEY_SECRET=change-me-model-key-min-16c → security.py:26-29 派生 Fernet key
   → 解密 model_provider 表中所有加密存储的 LLM API Key（凭据泄露 + 资金滥用）
  ```
  注意 `security.py:48-52` 的生产 fail-fast 只在密钥**为空**时触发，compose 提供的"非空但公开"默认值绕过了该护栏。
- **影响**：全部用户账户接管（读写任意日记/对话/导出）；LLM API Key 明文恢复。
- **修复建议**：compose 移除默认值，未设置即启动失败；启动时校验密钥长度（≥32 字节）并拒绝已知弱值；`.env.example` 仅留占位与生成命令。

---

## High

### H1. 认证后 SSRF 读取原语：`PUT /api/v1/models/{id}` 更新 base_url 无校验

- **位置**：`server/app/services/model_service.py:282-311`（`update_model`：`if base_url is not None: row.base_url = base_url` 直接落库，仅当同时携带 `api_key` 才触发 `validate_model_connection`，见 293-303）→ `server/app/shared/llm_factory.py:234-252`（`ChatOpenAI(base_url=...)`）
- **攻击者画像**：注册用户（开放注册，`auth.py:51-65`）
- **可控输入向量**：`PUT /api/v1/models/{id}` body `{"base_url":"http://169.254.169.254" 或任意内网 IP}`（不传 api_key 即完全跳过校验）
- **代码路径**：注册 → 用合法 URL 创建模型通过校验 → PUT 仅改 base_url（无校验）→ 发起对话 → `llm_factory.create_for_tier → _build_client` → 每次请求向 `{base}/v1/chat/completions` 发送 POST（含用户 API key 与日记内容）→ 响应进入对话流被读取。update 路径甚至绕过 create 时对云元数据段（169.254.0.0/16）的硬编码拦截。
- **影响**：SSRF 读取原语——探测并读取内网 HTTP 服务响应、扫描内网。
- **修复建议**：`update_model` 对 base_url 变更同样执行 `validate_outbound_url`；生产环境 `allow_private_model_hosts` 默认 False；运行时构建客户端前重新校验（防 DNS rebinding TOCTOU）。

### H2. 多用户部署下 RAG 检索跨用户泄露

- **位置**：`server/app/domain/rag/retriever.py:78`（`retrieve(query)` 无 `user_id` 参数）、`server/app/domain/rag/collections.py:44-109`（`upsert_diary` 仅以 `diary_id` 为键，共享 collection）；设计固化于 `server/tests/unit/security/test_tenant_isolation.py:282-292`（"single-tenant by design"）
- **攻击者画像**：外部已认证（多用户 Docker/MySQL 部署中的任一普通用户；compose 提供 MySQL 即支持多用户）
- **可控输入向量**：对话内容（触发检索）
- **代码路径**：用户 A 发消息 → `conversation_ai_service.py:244` `retriever.retrieve(query)`（无 user 过滤）→ 共享集合命中用户 B 的日记 chunk → 进入 A 的 LLM 上下文，回复可能引用 B 的私密日记。
- **影响**：跨用户日记内容泄露进他人 AI 上下文与回复。单用户桌面安装不受影响。
- **修复建议**：chunk 元数据增加 `user_id` 并在 `retrieve` 增加 `user_id` 过滤；更新相应隔离测试。

### H3. LLM/MCP 调用日志明文持久化用户日记全文（PII 静态泄露）

- **位置**：`server/app/infrastructure/llm_call_tracer.py:19-39`（`prompt=entry.prompt` / `response=entry.response` 原样落库）、`server/app/shared/tracing_llm.py:118-119`（仅 2000 字符截断）、`server/app/infrastructure/mcp_call_tracer.py:47-68`（参数/结果快照 2048 字节无脱敏）
- **攻击者画像**：能读取数据库者（配合 C3/H4——DB 默认口令+端口公网暴露、无 TLS 嗅探——即可成立）
- **可控输入向量**：任何 LLM 调用（对话、日记分析、RAG 合成）；prompt 由 `conversation_ai_service` 组装，含 pinned 日记原文与检索结果
- **影响**：用户日记全文、个人情绪数据以明文静态存储且无保留期限策略；DB 泄露即全部日记连带泄露。
- **修复建议**：日志只存摘要/哈希/token 计数；必须留存时做字段级脱敏并加 TTL 清理；敏感表加密。

### H4. 部署默认：DB/中间件弱口令 + 端口公网暴露 + 无 TLS 明文传输

- **位置**：`docker-compose.yml:5-8,9-10,22-23,36-40,57`（MySQL `nightdiary_pass`、Redis 无 requirepass、Neo4j `nightdiary_neo4j`，3306/6379/7474/7687 映射至宿主机 0.0.0.0）；`nginx.conf:1-3,14`（仅 `listen 80`，无 TLS/HSTS）；`src/shared/api/http.ts:51-54`（Authorization 头明文传输）
- **攻击者画像**：触达宿主机端口的网络攻击者 / 与用户同网段的中间人
- **代码路径**：`host:3306` 直连（仓库内公开口令）→ 全库数据（日记、bcrypt 哈希、trace 日志）；浏览器 → nginx `:80` 明文 → 中间人嗅探 `Authorization: Bearer <JWT>` 与日记请求体 → 账户接管/PII 泄露。
- **影响**：全库数据泄露、Redis 未授权读写/队列中毒、凭据劫持。
- **修复建议**：compose 移除硬编码口令默认值、端口仅绑 `127.0.0.1` 或走 Docker 内网、Redis 开 `requirepass`；nginx 配置 443 + HSTS，生产强制 HTTPS。

---

## Medium

### M1. 登录/注册无限流：暴力破解 + 邮箱枚举 + 弱密码策略

- **位置**：`server/app/api/v1/auth.py:26-30`（`password: min_length=6`）、`:51-65`（register 无限流、`EmailAlreadyExistsError` 回显邮箱→409 枚举）、`:68-84`（login 无限流）；全仓库无 rate-limit 中间件
- **攻击者画像**：外部未认证
- **影响**：登录/注册撞库与暴力破解；邮箱存在性枚举；批量垃圾账号。
- **修复建议**：按 IP+邮箱限流；密码最小长度提升并加复杂度要求；注册冲突返回通用错误。

### M2. 无 Redis 时登出黑名单仅存进程内存，多 worker 下吊销失效

- **位置**：`server/app/infrastructure/jwt_blacklist.py:16-28`、`server/app/infrastructure/redis_client.py:21`（进程内 fallback）、`server/Dockerfile:26`（`--workers 4`）
- **攻击者画像**：持有已登出 token 的会话方
- **代码路径**：`logout → blacklist_token(jti)` 写入本进程缓存；其余 worker 的 `get_current_user`（deps.py:53-55）仍放行该 token；进程重启后黑名单丢失。
- **影响**：登出后令牌仍可用（会话吊销失效）。默认 Docker 部署配了 Redis 不受影响。
- **修复建议**：多 worker 部署强制要求 Redis；或将黑名单落库。

### M3. 未认证资源消耗端点（模型下载 / quality-scan）

- **位置**：`server/app/api/v1/model_download.py:14-42`（`GET /status`、`POST /start` 无认证）、`server/app/api/v1/dev.py:447-458`（`POST /dev/quality-scan` 触发 LLM 判分）
- **攻击者画像**：外部未认证
- **影响**：反复触发模型下载消耗带宽/磁盘（有线程去重、影响有限）；反复触发 quality-scan 消耗 LLM 配额/费用。
- **修复建议**：认证 + 限流 + 幂等锁。

---

## 已核实安全的面（无已证明漏洞）

- **注入向量**：业务层全 ORM/参数绑定，无 SQL 拼接注入；生产代码无 `shell=True`/字符串子进程，MCP 子进程有环境白名单 + 密钥名过滤；上传文件名为服务端 UUID、`safe_join` 防路径穿越；无 eval/exec/Jinja2/pickle，动态 import 受静态白名单约束（`task_queue.py:85-86`、`domain/agents/__init__.py:38-65`）。
- **认证正向面**：bcrypt(cost 12) 哈希、JWT HS256 + jti 黑名单、Fernet 静态加密 API key、业务路由普遍按 user_id 隔离、Electron `contextIsolation+sandbox+no nodeIntegration`、preload 仅暴露 backendUrl。
- **SSRF 缓解**：云元数据段（169.254.0.0/16 等）在 `validate_outbound_url` 中始终拦截；HF 下载源白名单；`follow_redirects=False`。
- **错误处理**：`error_handlers.py:46-53` 不向客户端回显堆栈。

## 待确认 / 防御建议（无端到端证据，未计入确认数）

1. localStorage 存 JWT + 7 天长效 + nginx 无 CSP：当前 `src/` 未发现 `v-html/innerHTML` 等 XSS sink，缺少利用前置条件，属纵深防御缺陷。
2. DNS rebinding TOCTOU：`url_guard` 校验与 httpx 连接是两次解析，理论上可绕过；已并入 H1 修复建议。
3. `get_active_provider_for_tier` 跨用户解析（`model_service.py:337-354` 注释自述 legacy 调用方可能不传 user_id）。
4. `seed_dev_traces.py` 弱密码开发账号（`123456`）：仅手动脚本执行，未发现生产/桌面自动调用路径。

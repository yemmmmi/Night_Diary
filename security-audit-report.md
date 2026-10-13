# 安全审计报告

**目标**：夜记（Night Diary）代码仓库（FastAPI 后端 `server/` + Vue SPA `src/` + Electron 桌面端 `desktop/`）
**范围**：仅报告中等及以上严重度、具备**可论证的端到端利用路径**的已确认漏洞。
**审计方式**：架构梳理 + 分组攻击面审查（认证、注入、外部交互、敏感数据）；所有 High 级发现经人工核对源文件确认。

---

## 一、架构概览

- **入口点**：`server/app/main.py::create_app()` 创建 FastAPI 应用，挂载 `app/api/v1/router.py`（`/api/v1` 聚合路由）与 `openai_compat.py`（`/v1` OpenAI 兼容面）。
- **信任边界**：认证依赖集中在 `app/api/deps.py`。`CurrentUserDep`/`UserContextDep` 走 `get_current_user`（JWT 校验 + `is_active` + jti 黑名单）。`DbDep`/`ContainerDep` 不校验身份——凡仅依赖后两者的端点即**未鉴权**。
- **数据流**：外部请求 → API 路由 → 服务层（强制携带 `user_id` 过滤）→ SQLAlchemy（SQLite/MySQL）。LLM 调用经 `llm_factory` 出站；MCP 工具经 stdio/SSE 子进程与远程端点；对话/检索管线写入 `pipeline_traces` 供 `/dev` 调试查看。
- **凭证管理**：JWT 签名与敏感数据加密（Fernet）均基于 `jwt_secret_key`/`model_key_secret`（env → `secrets.key` → 开发自生成）。

---

## 二、高危（High）

### H1. 未鉴权的 `/api/v1/dev/*` 调试接口 → 跨租户个人数据（日记/对话）泄露与任意删除

- **位置**：`server/app/api/v1/dev.py`（`/dev/traces`、`/dev/traces/{trace_id}`、`/dev/traces/{trace_id}/stream`、`/dev/traces/{trace_id}` DELETE、`/dev/mcp/calls`、`/dev/quality-scan`）；挂载点 `server/app/api/v1/router.py:43`。
- **攻击者画像**：任意能对后端端口发起 HTTP 请求的未认证客户端。桌面端默认绑定 `127.0.0.1`，但 Docker 部署将后端映射为 `8000:8000`（`docker-compose.yml:74`），可被远程触达。
- **可控输入向量**：无需任何凭证，直接 `GET /api/v1/dev/traces` 枚举全部 trace（每条含 `user_id`）、`GET /api/v1/dev/traces/{trace_id}` 取详情、`DELETE /api/v1/dev/traces/{trace_id}` 删除任意 trace。
- **确切代码路径**：`dev.py` 模块 docstring（L5-6）明言"do not require authentication"；`list_traces`（`dev.py:147-178`）直接查询全部 `PipelineTraceRow` 无 user 过滤；`get_trace_detail`（`dev.py:184-197`）返回完整 `row.trace_json`；`delete_trace`（`dev.py:203-215`）按任意 id 删除。trace 内容由管线持久化写入，`conversation_ai_service` 各 span 以 `input_snapshot={"raw_text": content}` 记录日记/对话原始正文，`user_id` 亦被记录。
- **影响**：绕过认证读取全部用户的日记与对话正文 PII（跨租户、可枚举租户）；任意删除 pipeline trace 破坏数据完整性；`/dev/quality-scan` 可未认证触发重负载判官 LLM 扫描造成服务成本滥用。**属越权数据泄露 + DoS。**
- **修复建议**：为 `/dev/*` 全部端点追加 `CurrentUserDep` 并强制按 `CurrentUserDep.user_id` 过滤；或仅在生产/非 debug 构建注册该路由；对 MCP 调用参数/结果快照做脱敏；`/dev/quality-scan` 加鉴权。

### H2. docker-compose 生产模式硬编码弱静态默认密钥 → 认证绕过 + 离线解密 Provider API Key

- **位置**：`docker-compose.yml:59-60`（backend）与 `103-104`（worker）；根目录 `.env.example` 亦写有同值。
- **攻击者画像**：按 compose 默认（未在 `.env` 覆盖）部署后，可访问后端 API 的任意远程客户端；以及能读取数据库/数据卷的攻击者。
- **可控输入向量**：无；属**默认配置缺陷**。`APP_ENV=production` 下若未设对应 env 变量，自动落入公开常量 `change-me-in-production-min-32-chars`（JWT）与 `change-me-model-key-min-16c`（Fernet）。
- **确切代码路径**：已知 JWT 密钥 → `app/infrastructure/auth.py::resolve_jwt_secret`（`auth.py:35-45`）直接用它签名，`create_access_token`（`auth.py:48-65`）可被攻击者伪造任意 `sub` 的 token → 无需密码登录任意账号。已知 Fernet passphrase → `app/infrastructure/security.py::_derive_fernet_key`（`security.py:26-29`）可离线派生出解密 `model_providers.api_key_encrypted` 的主密钥（持有数据卷时）。
- **影响**：完全鉴权绕过——伪造任意用户 JWT 读取其全部日记/记忆 PII；且可离线解密所有用户已加密的 LLM Provider API Key。**认证绕过 + 机密泄露。**
- **修复建议**：生产 compose 移除静态兜底默认值；`resolve_jwt_secret`/`_resolve_secret` 在 secret 为空或其等于已知占位/示例值时 fail-fast；启动时校验密钥强度（≥32 随机字节）；`APP_ENV=production` 禁止回退到示例密钥。

---

## 三、中危（Medium）

### M1. 未鉴权 `POST /api/v1/models/test-connection` → 盲 SSRF / 内网端口探测

- **位置**：`server/app/api/v1/models.py:42-51`；`server/app/services/model_service.py:161-202`；根因在 `server/app/config.py:155-159`（`allow_private_model_hosts` 默认 `True`）。
- **攻击者画像**：任意未认证客户端。
- **可控输入向量**：请求体 `{"base_url": "<任意URL>", "api_key": "<任意串>"}`（`api_key` 仅非空校验，不作真实凭据）。
- **确切代码路径**：`test_model_connection` 无 `CurrentUserDep` → `model_service.validate_model_connection(base_url, ...)`（`model_service.py:161`）→ `validate_outbound_url(base_url, allow_private=True)`（`url_guard.py:105`）仅封云元数据/链路本地段（`url_guard.py:38-45`），回环/内网被放行 → 对攻击者控制的 `base_url` 发起 `GET {base}/models`、`POST {base}/v1/chat/completions`（`model_service.py:178-202`）。
- **影响**：匿名后端起对内网任意主机/端口发 HTTP 请求，错误信息携带状态码（如"API 返回状态码 {code}"）形成**状态码侧信道的端口/服务扫描**，可枚举 loopback 服务、Docker 网关、LAN 内未鉴权管理面板等。云元数据网段被硬封，响应体不回显，故判中危而非高危。
- **修复建议**：为 `/test-connection` 追加 `CurrentUserDep`（与 `/models/{id}/test-connection` 对齐）；无认证公开部署时将 `allow_private_model_hosts` 默认置 `False`；私网目标改由管理员白名单配置而非用户输入。

### M2. 未鉴权 `/api/v1/models/download/start|status` → 匿名触发模型下载（资源 DoS）+ 状态泄露

- **位置**：`server/app/api/v1/model_download.py:14-42`；挂载 `router.py:37`。
- **攻击者画像**：任意未认证客户端。
- **可控输入向量**：`POST /api/v1/models/download/start`、`GET /api/v1/models/download/status`（均无 `CurrentUserDep`）。
- **确切代码路径**：`start_download`（`model_download.py:34-42`）→ `get_model_download_service().start()`，下载 embedding/reranker 模型（体积可观）；`snapshot()` 暴露下载进度/错误。
- **影响**：匿名反复触发首次模型下载，消耗磁盘/网络/算力造成资源 DoS；状态接口泄露环境信息。下载目标为白名单常量、仓库不可控，故判中危。
- **修复建议**：追加 `CurrentUserDep` 或限制仅环回访问；对 `/start` 加限流。

---

## 四、加固建议（非确认漏洞，供改进）

以下为审查中发现的低危/防御性观察，因缺少"中等及以上、端到端利用"路径或属设计权衡，未计入确认清单：

- **JWT 有效期 7 天 + 明文存 localStorage**（`src/stores/auth.ts` 写入 `night_diary_token`、`config.py:149-152`）：`src` 未发现可用 XSS 注入点，故无直接利用链；一旦存在 XSS 或设备共享，长期有效令牌可被窃取。建议改用 `httpOnly; Secure` Cookie、缩短有效期。
- **登录/注册无速率限制 + 注册/登录账号枚举**（`auth.py:53-55` 专属 409 错误、`auth.py:73-74` 时序差异）：可被批量弱口令/枚举滥用。
- **`url_guard` 校验与实际 httpx 连接存在两次 DNS 解析（TOCTOU）**：`url_guard.py` 用 `getaddrinfo` 校验后，httpx 连接时另行解析，原理上可通过 DNS-rebinding 越过元数据网段封堵。认证用户已可配置自有 `base_url`，故该风险主要在 M1 修复基础上做纵深加固（对出站请求二次校验已解析 IP、禁用重定向）。
- **JWT 与 Fernet 在仅配置 `MODEL_KEY_SECRET` 时可共用同一密钥**：削弱密钥独立性，建议分离两个密钥。
- **`MCP_STDIOS` 配置驱动的任意命令子进程**（`mcp_config.py`/`mcp_connections.py`）：无任何 API 可被外部改写配置，当前无外部可达路径；仍建议对 stdio 命令做白名单/`shutil.which` 解析并视其为高敏配置。

---

## 五、结论

已确认 **2 项高危、2 项中危**漏洞，均具备明确的端到端利用路径：

- **High**：未鉴权 `/api/v1/dev/*` 跨租户 PII 泄露 + 任意删除（H1）
- **High**：docker-compose 生产弱静态默认密钥 → 认证绕过 + Provider Key 离线解密（H2）
- **Medium**：未鉴权 `/models/test-connection` 盲 SSRF / 内网端口探测（M1）
- **Medium**：未鉴权 `/models/download/*` 匿名资源 DoS + 状态泄露（M2）

核心注入面（SQL / Shell / eval-exec / 目录穿越 / LLM→系统层代码执行）与多租户数据隔离总体干净，未发现可确认的注入类漏洞；Webhook 入站面不存在；MCP 目标不可被外部控制。
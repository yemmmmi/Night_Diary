# Night Diary V2 安全审计报告

**审计日期**：2026-11-06
**范围**：`/workspace`（Vue3 前端 + FastAPI 后端，MySQL/Redis/Neo4j/ChromaDB）
**方法**：架构梳理（入口点/信任边界/数据流转）→ 按攻击面分组追踪从攻击者可控输入到影响的完整代码路径 → 仅保留可论证端到端利用链的已确认发现
**结论**：发现 **3 个 High、5 个 Medium** 已确认漏洞。

---

## High 严重度

### H1. `/api/v1/dev/*` 全部端点无认证，泄露全量用户日记/对话/LLM 调用明文，并可破坏数据

- **攻击者画像**：任意未认证的外部/本机攻击者（仅需可达后端端口；浏览器受 CORS 限制，但 curl/脚本不受限）。
- **可控输入向量**：无（仅需发 GET）；数据由任意启用开发者模式的前端自动附加 `X-Trace-Id` 产生。
- **代码路径**：
  1. 路由注册：`server/app/api/v1/router.py:43` 挂载 `dev.router`；`server/app/api/v1/dev.py:30-34` 前缀 `/dev`，文件头第 5-6 行明确写明 "do not require authentication"，全部 12 个端点仅依赖 `DbDep`/`ContainerDep`，无 `CurrentUserDep`。
  2. 数据来源：`server/app/services/conversation_ai_service.py:526/565/610/652/727/854/896/945/981/1058` 在 `trace_span` 中写入 `input_snapshot={"raw_text": content}` —— **用户消息/日记原文**、检索 query、RAG 上下文、LLM prompt/response 均入 trace；`llm_call_tracer.py:30-31`、`mcp_call_tracer.py:63-64` 记录 2000 字明文快照与工具入参；经 `persist_trace`（conversation_ai_service.py:1222）落库 `PipelineTraceRow.trace_json`。
  3. 读取端：`dev.py:147-198`（`GET /dev/traces` 全表分页含 `user_id`；`GET /dev/traces/{id}` 返回完整 trace_json）、`dev.py:221-298`（SSE 实时流）、`dev.py:482-499`（`GET /dev/mcp/calls`）。
  4. 破坏端：`dev.py:203-215`（`DELETE /dev/traces/{id}` 删任意 trace）、`dev.py:447-458`（`POST /dev/quality-scan` 无认证触发跨用户 LLM 采样评分，成本 DoS）。
- **影响**：全量用户隐私泄露（日记、对话、检索查询、Agent 推理、MCP 调用参数）；任意删除审计数据；未认证触发 LLM 调用造成资源/费用耗尽；`/dev/middleware-status` 泄露基础设施状态。
- **修复建议**：dev 路由整体挂载 `CurrentUserDep`（或独立管理员令牌），trace/MCP 日志按 `user_id` 过滤，`quality-scan` 限频并加认证，生产默认关闭该路由。

### H2. `POST /api/v1/models/test-connection` 无认证 SSRF，且 url_guard 存在 IPv4-mapped IPv6 绕过，可直连云元数据（IMDSv1）

- **攻击者画像**：任意未认证远程攻击者。
- **可控输入向量**：请求体 `base_url`（任意 http/https URL，含 IPv6 字面量）。
- **代码路径**：
  1. `server/app/api/v1/models.py:42-51`：端点无 `db`/`user` 依赖，直接调用 `model_service.validate_model_connection(body.base_url, ...)`。
  2. `server/app/services/model_service.py:161-210`：`validate_outbound_url(base_url, allow_private=settings.allow_private_model_hosts)`，`allow_private_model_hosts` 默认 `True`（`config.py:155-160`），随后 `httpx.Client(trust_env=False, follow_redirects=False)` 向目标发 `GET {base}/models`、`POST {base}/v1/chat/completions`，错误消息回显状态码与 URL（`model_service.py:185/202/204-206`），构成扫描 oracle。
  3. **IPv4-mapped IPv6 绕过（已验证）**：`server/app/shared/url_guard.py:38-45` `_ALWAYS_BLOCKED_NETS` 仅含 IPv4 网段；`_classify_ip`（89-102）对 `::ffff:169.254.169.254` 这类 IPv6 字面量判定 `is_reserved=False`、不命中任何网段 → 放行。实测 `ipaddress.ip_address("::ffff:169.254.169.254") in ipaddress.ip_network("169.254.0.0/16")` 返回 `False`。内核将 IPv4-mapped 地址直连 `169.254.169.254`，**无需 DNS rebinding** 即可直达云元数据（IMDSv1，可读取实例 IAM 临时凭证）。
  4. 另存在 DNS rebinding TOCTOU：校验时 `socket.getaddrinfo`（url_guard.py:70-86）与 httpx 连接时二次解析不一致。
- **影响**：未认证内网端口/服务指纹扫描（状态码回显）；云环境（AWS/GCP/阿里云）下可读取元数据服务获取 IAM 临时凭证 → 云账户横向；攻击者利用服务器作凭据转发点。
- **修复建议**：该端点强制认证；`test-connection` 强制 `allow_private=False`；url_guard 对 `::ffff:0.0.0.0/96`（`ip.ipv4_mapped`）先映射为 IPv4 再归并校验；解析结果与连接目标绑定（自定义 transport 固定解析 IP）；探测请求设短超时并限流。

### H3. docker-compose 内置可预测默认 JWT/Fernet 密钥 → 全量账户接管 + LLM 凭据可解密

- **攻击者画像**：任意未认证远程攻击者（部署可达即可，无需任何输入）。
- **可控输入向量**：无——直接使用仓库公开的 fallback 常量。
- **代码路径**：
  1. `docker-compose.yml:59-60`（backend）与 `103-104`（worker）：`JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-me-in-production-min-32-chars}`、`MODEL_KEY_SECRET=${MODEL_KEY_SECRET:-change-me-model-key-min-16c}`。部署者未显式设置 env 时，公开常量即生效（README 以 Docker Compose 为正式部署方式）。
  2. `server/app/infrastructure/auth.py:35-45`：`resolve_jwt_secret` 优先取 `jwt_secret_key` → `auth.py:64-65` `jwt.encode(..., secret)` HS256 签发。攻击者用公开常量可伪造任意 `sub` 的合法 JWT（exp/iat/jti 自签），经 `api/deps.py:44-59` 校验通过 → 任意账户接管。
  3. 同一常量经 `server/app/infrastructure/security.py:26-29` `sha256(MODEL_KEY_SECRET)` 派生 Fernet 密钥 → `decrypt_api_key`（security.py:73-77）解密 `model_providers.api_key_encrypted` 中全部 LLM API key。
  4. 附：`docker-compose.yml:36` Neo4j `neo4j/nightdiary_neo4j`、`:5-8` MySQL `nightdiary/nightdiary_pass` 亦为公开默认凭据且端口映射到宿主（3306/7687）。
- **影响**：公开常量 + HS256 → 伪造任意用户 JWT，读取全部日记/对话 PII、执行任意用户操作；解密库中全部 LLM API key（SQLite 明文文件、MySQL dump 或 H1 的 dev 接口可触碰 DB 数据）。
- **修复建议**：compose 缺省时 fail-fast 拒绝启动（未设置 env 则报错退出，或随机生成并告警）；生产强制环境变量注入；JWT 密钥与 Fernet 密钥分离；基础设施默认凭据改为随机生成。

---

## Medium 严重度

### M1. 跨租户 LLM 凭据/端点混用：A 的日记内容发送至 B 配置的提供商端点，并消耗 B 的 API key

- **攻击者画像**：已注册用户（多租户部署；README 明确支持多用户）。
- **可控输入向量**：自己的 `base_url`/`api_key`（`POST /api/v1/models` 可创建），或利用他人已配置的 provider。
- **代码路径**：`server/app/services/container.py:378-383` `_llm_for_tier` 调用 `resolve_llm_clients_by_tier(session, ...)` **不传 user_id** → `server/app/shared/llm_factory.py:137-142` 查询**所有用户**的 provider 行（`user_id` 为 None 时不加过滤）→ `rows[0]` 属主的密钥与 `base_url`（llm_factory.py:162-168、`provider_api_keys`）建立客户端；且 `llm_factory.py:144-155` 当用户无匹配行时回退为**全量行**（即使传了 user_id 也丢过滤）。该客户端经 `container.py:362-396` 供会话分类/Agent 编排使用。
- **影响**：恶意用户 B 配置指向自己服务器的 provider 后，用户 A 的日记/对话内容被发送至 B 的服务器（跨租户敏感数据泄露）；A 的请求消耗 B 的 API 配额（账单/滥用归责错误）。
- **修复建议**：所有 LLM 解析路径强制传 `user_id` 并按属主过滤；删除或限定 `llm_factory.py:144-155` 的跨用户回退逻辑。

### M2. `secrets.key` 文件权限 0644，同机本地用户可读 JWT/Fernet 密钥

- **攻击者画像**：与运行用户同机（本地桌面/共享主机）的其他本地用户。
- **可控输入向量**：无（仅需读取文件系统）。
- **代码路径**：`server/app/infrastructure/security.py:54-59` 开发/测试模式自动生成密钥并 `key_file.write_text(generated)`，**无 chmod**；默认 umask 022 下文件 0644，`data_dir` 目录 0755（默认 `~/.local/share/night-diary`）→ 同机任意用户可读；该密钥同时经 `auth.py:35-45` 回退链用作 JWT 签名密钥。
- **影响**：同机本地用户读取密钥后伪造 JWT（账户接管）并解密库中 LLM API key。
- **修复建议**：写盘后 `chmod 0o600`，目录 `0o700`；生产强制 env 注入并 fail-fast。

### M3. 登录无限流 + 注册用户枚举 → 弱口令爆破/撞库

- **攻击者画像**：任意未认证远程攻击者。
- **可控输入向量**：`POST /api/v1/auth/login`（`username`/`password`）、`POST /api/v1/auth/register`（`email`）。
- **代码路径**：`server/app/api/v1/auth.py:68-84` login 无任何限流/失败锁定（`main.py` 仅注册 CORS 中间件，无速率限制中间件）；`auth.py:28` 密码最短仅 6 位；`auth.py:52-65` 注册时邮箱已存在返回 409 `EmailAlreadyExistsError`（`errors.py:125`）→ 用户枚举；登录成功返回 7 天 JWT。
- **影响**：邮箱枚举 + 在线暴力破解/撞库 → 账户接管（受 6 位弱密码策略放大）。
- **修复建议**：登录限流/失败递增锁定（Redis 计数器）；注册/登录响应统一模糊化；提高密码复杂度下限。

### M4. 生产部署无 TLS：7 天 JWT 与登录口令明文过网

- **攻击者画像**：部署链路同网段的嗅探者（局域网/中间人）。
- **可控输入向量**：被动嗅探。
- **代码路径**：`nginx.conf:2` 仅 `listen 80`（无 443/301/HSTS）；`docker-compose.yml:124-125` 仅映射 80；前端 JWT 存 localStorage（7 天有效期，`config.py:149-152`）经明文 HTTP 传输。
- **影响**：同网段攻击者截获 JWT 即会话劫持（完整账户数据访问），截获登录口令。
- **修复建议**：nginx 终止 TLS（443）+ HSTS + HTTP→HTTPS 301；缩短 JWT 有效期并支持刷新令牌。

### M5. MCP SSE 服务无鉴权绑定 `0.0.0.0`（需管理员显式启用 `--transport sse`）

- **攻击者画像**：局域网/本机任意客户端。
- **可控输入向量**：MCP 协议工具调用（读日记/写数据）。
- **代码路径**：`server/app/infrastructure/mcp_server.py:184` `uvicorn.run(app, host="0.0.0.0", port=port)`，无任何认证；同一进程内的工具注册表可调用日记读取等内置工具。
- **影响**：LAN 内任意客户端枚举并调用日记工具，读取/操纵用户数据。**前提**：管理员以 `--transport sse` 显式启动该服务（默认未启用）。
- **修复建议**：绑定 `127.0.0.1`，或加令牌/Bearer 鉴权；文档明确仅在可信网络启用。

---

## 未发现已确认漏洞的类别（防护良好项）

- **注入**：SQL（repository/service 全走 ORM 绑定参数）、Neo4j Cypher（entity_graph.py 全部 `$param` 参数化）、命令注入（MCP stdio 仅来自环境变量 `MCP_STDIOS`，`mcp_config.py:45-66` 白名单+密钥名过滤；`subprocess` 仅 `git rev-parse` 固定参数）、路径遍历（uploads.py 以 content_type 白名单 + uuid 存储、`user_id` 目录隔离；model_downloader 走 `safe_join`）、反序列化（无 pickle/yaml.load）——均未发现可利用链路。
- **JWT 实现**：`decode_access_token` 硬编码 `algorithms=[HS256]`（无算法混淆）；exp/iat 由 PyJWT 校验；logout jti 黑名单生效。
- **IDOR**：diary/card/conversation/plan/schedule/skill/model/upload/feedback/weekly 服务层均按 `user_id` 过滤（含 openai_compat `_resolve_conversation` 校验 user_id）。
- **硬编码密钥**：仓库无真实 `sk-` 密钥；`.env.example` 均为占位符。
- **日志泄露**：无 logger/print 输出 api_key/password/Authorization 明文；500 错误统一回显"内部错误"。

## 修复优先级建议

1. **立即**：H1（dev 路由加认证）、H2（test-connection 加认证 + 修复 url_guard IPv6 绕过）、H3（compose 强制密钥注入 + fail-fast）。
2. **尽快**：M1（LLM 解析按 user_id 过滤）、M3（登录限流）、M4（TLS）。
3. **计划**：M2（文件权限）、M5（MCP 绑定回环）。

---

*注：`PUT /api/v1/models/{id}` 更新 base_url 不重新过 url_guard（`model_service.py:287-288`）与 M1 叠加时放大影响；单用户本地部署下影响有限，已并入 M1 修复建议（base_url 变更路径统一校验），未单列。*

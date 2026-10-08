# 安全审计报告 — night-diary 仓库

- 审计日期：2026-10-08
- 审计范围：`server/`（FastAPI 后端）、`src/`（Vue3 前端）、Docker 部署配置
- 审计方法：静态代码审计 + 端到端利用路径验证。仅报告具备可论证利用路径的已确认漏洞（中等及以上）。
- 结论：确认 **2 个 High、2 个 Medium** 漏洞。共检查候选发现 10 项，剔除 6 项（证据不足/不可利用，见附录）。

---

## 代码库架构摘要

- **入口点**：`server/app/main.py` 创建 FastAPI 应用；`server/app/api/v1/router.py` 聚合 `/api/v1/*` 路由（auth / diary / card / conversation / feedback / models / model_download / stats / tags / weekly / memory / export / dev / plan / mode / skills）。另有 worker（`app/workers/worker.py`）与启动时后台任务（模型预热、任务重派、质量哨兵）。
- **信任边界**：JWT 认证（`app/infrastructure/auth.py`：bcrypt + PyJWT HS256），依赖注入 `app/api/deps.py#get_current_user`（校验签名、过期、`jti` 黑名单、用户是否激活）。**没有全局 HTTP 认证中间件**；中间件管线（`app/shared/middleware/*`）仅作用于 LLM 回复流程，与 HTTP 鉴权无关。
- **数据流转**：API 层 → service 层 →（SQLAlchemy repository / ChromaDB RAG / LLM / MCP 工具）→ SQLite/MySQL + Redis + Neo4j。业务数据（diary/card/memory/plan/tag/weekly/conversation/export/feedback/mode/models/skills）均以 `user_id` 过滤，跨用户隔离总体正确（已逐端点核对）。
- **部署形态**：`docker-compose.yml` 以 `APP_ENV=production` 启动后端并发布 `8000:8000`；`server/Dockerfile` 以 `--host 0.0.0.0` 运行 uvicorn。前端由 nginx 提供并反代。

---

## 已确认漏洞（按严重度分组）

### HIGH

#### H1. `/api/v1/dev/*` 全组端点无认证 → 跨用户敏感数据泄露（日记/对话内容）+ 数据删除 + 资源滥用

- **攻击者画像**：任何能访问后端 8000 端口的外部未认证攻击者（生产 compose 将 8000 映射到宿主机）。
- **可控输入**：无需任何输入即可枚举；可指定任意 `trace_id` / `page` / `ref_id` / `user` 过滤参数。
- **代码路径**：
  1. [router.py](file:///workspace/server/app/api/v1/router.py#L39) 无条件挂载 `dev.router`；
  2. [dev.py](file:///workspace/server/app/api/v1/dev.py#L147-L178) `GET /dev/traces` 无任何认证依赖（仅 `DbDep`），返回**全部用户**的 `PipelineTraceRow` 摘要（含 `user_id`、`trace_id`、`ref_id`）；
  3. [dev.py](file:///workspace/server/app/api/v1/dev.py#L184-L197) `GET /dev/traces/{trace_id}` 返回完整 `trace_json`；[dev.py](file:///workspace/server/app/api/v1/dev.py#L203-L215) `DELETE /dev/traces/{trace_id}` 可删除任意 trace；[dev.py](file:///workspace/server/app/api/v1/dev.py#L447-L458) `POST /dev/quality-scan` 可无认证触发付费 LLM 判定调用；[dev.py](file:///workspace/server/app/api/v1/dev.py#L482-L500) `GET /dev/mcp/calls` 暴露所有用户 MCP 工具调用参数/结果快照（各 2048 字节）。
  4. trace 数据来源（**每次日记/对话回复都会持久化，与开发者模式开关无关**）：
     - [conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L434) `trace_span("S2_crisis", input_snapshot={"raw_text": content})`，以及 [L473](file:///workspace/server/app/services/conversation_ai_service.py#L473)、[L518](file:///workspace/server/app/services/conversation_ai_service.py#L518)、[L560](file:///workspace/server/app/services/conversation_ai_service.py#L560)、[L634](file:///workspace/server/app/services/conversation_ai_service.py#L634) 均把**用户原始对话内容**（截断至 500 字符/快照）写入 span；
     - [memory_gateway.py](file:///workspace/server/app/services/memory_gateway.py#L156-L186)、[analysis_service.py](file:///workspace/server/app/services/analysis_service.py#L355-L369) 记录情绪/事件摘要；
     - 落库：[trace_persistence.py](file:///workspace/server/app/shared/trace_persistence.py#L20-L43) `persist_trace` 将 `trace.to_dict()`（含所有 span 快照）序列化为 `trace_json`；调用点 [conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L1118) 与 [analysis_service.py](file:///workspace/server/app/services/analysis_service.py#L509) 在每次回复后执行。
  5. 部署暴露：[docker-compose.yml](file:///workspace/docker-compose.yml#L73-L74) 发布 `8000:8000`，[Dockerfile](file:///workspace/server/Dockerfile#L26) 绑定 `0.0.0.0`。
- **影响**：**数据泄露**——未认证攻击者可枚举并读取所有用户的日记/对话原文快照与 MCP 工具调用参数（含传入工具的敏感内容）；**数据完整性**——可删除任意用户 trace；**可用性/成本**——可反复触发付费 LLM 质量扫描。
- **修复建议**：
  1. 为 `/api/v1/dev/*` 增加认证（如仅限管理员/所有者），并在查询层按 `user_id` 过滤（`list_traces`/`get_trace_detail`/`stream_trace`/`delete_trace`/`list_mcp_call_logs`）；
  2. `DELETE /traces` 与 `POST /quality-scan` 从公开 API 移除或加权限；
  3. 生产环境禁用 dev 路由（按 `APP_ENV` 条件挂载）；
  4. 若流式场景必须允许订阅 trace（前端需要），则至少对 `list_traces` 枚举端点鉴权，并校验 SSE 订阅者与 trace 的归属关系。

---

#### H2. 生产部署默认使用公开占位 JWT/Fernet 密钥 → JWT 伪造、任意用户账号接管

- **攻击者画像**：任何外部未认证攻击者（无需网络内网访问）。
- **可控输入**：仅需知道默认占位符即可自行伪造 JWT。
- **代码路径**：
  1. [docker-compose.yml](file:///workspace/docker-compose.yml#L56-L60) 在 `APP_ENV=production` 下为 `JWT_SECRET_KEY` / `MODEL_KEY_SECRET` 提供公开默认值 `change-me-in-production-min-32-chars` / `change-me-model-key-min-16c`（用户未显式设置时直接生效）；
  2. [config.py](file:///workspace/server/app/config.py#L116-L120) 直接接收该值，无强度/占位校验；
  3. [auth.py](file:///workspace/server/app/infrastructure/auth.py#L35-L45) `resolve_jwt_secret`：`jwt_secret_key` 非空即返回，绕过 `_resolve_secret` 的生产 fail-fast；
  4. [security.py](file:///workspace/server/app/infrastructure/security.py#L32-L59) 的 fail-fast 仅在 `model_key_secret` **为空**时触发，而 compose 已填充占位值，故不触发；
  5. [deps.py](file:///workspace/server/app/api/deps.py#L39-L60) `get_current_user` 仅校验签名/过期/黑名单，攻击者用公开密钥签发的 `{"sub": "<受害用户id>", "exp": <未来时间>}` 直接通过。
- **影响**：**账号接管 / 完全数据泄露**——伪造任意用户 JWT 后可调用全部业务 API（`/diary/entries`、`/export/all`、`/conversations` 等）读取、导出、修改、删除任意用户的日记/记忆/计划等全部敏感数据；同时 Fernet 密钥（`sha256(占位符)`）可解密 `model_providers` 表中所有加密的 LLM API Key；compose 还发布了 MySQL `3306` 端口（默认口令 `nightdiary/nightdiary_pass`），可直接攻破数据库。
- **修复建议**：
  1. 生产环境启动时校验 `JWT_SECRET_KEY` / `MODEL_KEY_SECRET`：缺失**或等于任何已知占位值**即 fail-fast；
  2. compose 移除占位默认值，改为必填环境变量或首次启动自动生成强随机密钥；
  3. 变更数据库/Neo4j 默认口令，不发布 `3306/6379/7474/7687` 端口（或仅绑定回环）。

---

### MEDIUM

#### M1. 未认证 SSRF —— `POST /api/v1/models/test-connection`

- **攻击者画像**：外部未认证攻击者。
- **可控输入**：`base_url`、`api_key`、`model_name` 请求体字段。
- **代码路径**：
  1. [models.py](file:///workspace/server/app/api/v1/models.py#L42-L51) `test_model_connection` **未声明任何认证依赖**，直接调用 `model_service.validate_model_connection(body.base_url, body.api_key, ...)`；
  2. [model_service.py](file:///workspace/server/app/services/model_service.py#L105-L151) 使用 `httpx.Client(timeout=10.0, trust_env=False)`（绕过系统代理）向 `{base_url}/models`、`{base_url}/v1/models` 发起 GET，并向 `{base_url}/v1/chat/completions` 发起 POST；
  3. 仅校验前缀是 `http://`/`https://`，**无域名/内网/IP 限制**（[model_service.py](file:///workspace/server/app/services/model_service.py#L111)）。
- **影响**：**SSRF（状态码回显型）**——以服务器身份探测内网服务与云元数据端点（如 `http://169.254.169.254/...`、内网主机扫描）；响应体不回显，但通过 200/401/405 等状态码差异可做端口/服务指纹探测与元数据探测（可探测到 IAM 凭证端点是否可达）。
- **修复建议**：
  1. 该端点要求认证；
  2. 对 `base_url` 做校验：仅允许 `https://`，阻止回环/私网/链路本地/云元数据网段（`127.0.0.0/8`、`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`、`169.254.169.254`、`0.0.0.0`、IPv6 `::1`/`fc00::/7` 等），并防止 DNS 重绑定（解析后二次校验 IP）；
  3. 同样的校验应用到 `create_model`/`update_model` 的测试路径（已认证但同样存在 SSRF 面）。

#### M2. 登录无暴力破解防护 + 开放注册 + 账号枚举

- **攻击者画像**：外部未认证攻击者。
- **可控输入**：`/register` 的 `email`，`/login` 的 `username`+`password`。
- **代码路径**：
  1. [auth.py](file:///workspace/server/app/api/v1/auth.py#L51-L65) 开放注册；已存在邮箱返回可区分的 `EmailAlreadyExistsError`（409）→ **账号枚举**；
  2. [auth.py](file:///workspace/server/app/api/v1/auth.py#L68-L84) 登录无任何速率限制/锁定/验证码；bcrypt 增加成本但不构成节流。
- **影响**：在对外暴露的部署上可枚举有效邮箱并对口令实施在线暴力破解/撞库；叠加 H2（默认密钥）时账号接管变得平凡。
- **修复建议**：对 `/login`、`/register` 按 IP + 账号做速率限制与指数退避；注册失败与登录失败返回统一错误信息；可选设备指纹/验证码；监控异常登录。

---

## 附录：已检查并剔除的候选发现

| 候选 | 位置 | 剔除原因 |
|---|---|---|
| 原生 SQL 注入（`ALTER TABLE ... {ddl_type}`） | [database.py](file:///workspace/server/app/infrastructure/database.py#L170-L216) | `table`/`column`/`ddl_type` 全部来自硬编码常量字典且标识符经 `q()` 引号转义，无用户输入参与 |
| LLM 提示词注入（用户技能文档） | [skill_loader.py](file:///workspace/server/app/domain/skills/skill_loader.py#L77-L152)、[injection.py](file:///workspace/server/app/domain/skills/injection.py#L36-L80) | 无任何 API 支持用户上传/自定义技能文档；[skills.py](file:///workspace/server/app/api/v1/skills.py#L15-L18) 仅返回内置技能列表，技能注册表仅含内置技能 → 不可端到端利用 |
| MCP endpoint 连接 SSRF | [mcp_config.py](file:///workspace/server/app/services/ai/mcp_config.py#L27-L48)、[mcp_connections.py](file:///workspace/server/app/services/ai/mcp_connections.py#L189-L213) | `mcp_endpoints`/`mcp_stdios` 仅来自服务器端环境配置，无运行时 API 可修改 → 非攻击者可控 |
| 未认证模型下载触发 | [model_download.py](file:///workspace/server/app/api/v1/model_download.py#L34-L41)、[model_downloader.py](file:///workspace/server/app/services/model_downloader.py#L18-L21) | repo_id 硬编码（BAAI/bge-*），仅能触发固定模型下载 → 影响限于带宽/磁盘，低于确认门槛（建议加认证） |
| 用户可控 `X-Trace-Id` 覆盖他人 trace | [conversation.py](file:///workspace/server/app/api/v1/conversation.py#L98-L108)、[trace_persistence.py](file:///workspace/server/app/shared/trace_persistence.py#L20-L43) | trace_id 为主键，重复提交触发 IntegrityError 被捕获回滚，无法覆盖 |
| JWT 黑名单在 Redis 不可用时的降级 | [jwt_blacklist.py](file:///workspace/server/app/infrastructure/jwt_blacklist.py#L19-L28) | 属可用性/设计稳健性问题，不构成已确认可利用漏洞 |
| 登录会话固定/令牌泄露（前端 localStorage） | [http.ts](file:///workspace/src/shared/api/http.ts#L49-L64) | SPA 常规做法，无证据表明存在可利用 XSS 前置条件 |

---

## 修复优先级建议

1. **H1**：`/api/v1/dev/*` 加认证 + 按用户隔离（或生产禁用）——阻断最直接的跨用户敏感数据泄露。
2. **H2**：生产配置强制校验密钥强度/占位值并 fail-fast，轮换已部署实例的 JWT/Fernet 密钥。
3. **M1**：`/models/test-connection` 认证 + `base_url` 内网/云元数据黑名单校验。
4. **M2**：登录/注册速率限制与统一错误信息。

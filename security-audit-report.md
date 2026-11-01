# 夜记（Night Diary）安全审计报告

**审计日期**: 2026-11-01
**审计范围**: 全仓库（Vue 3 前端 + FastAPI 后端 + MySQL/Redis/Neo4j/ChromaDB + AI 编排/MCP）
**审计标准**: 仅报告中等严重度及以上、具备可论证端到端利用路径的已确认漏洞；不报告理论性/推测性风险。

---

## 架构概览（信任边界）

- **入口点**: nginx → `/api/`（FastAPI `/api/v1/*`，含 20 个路由组）、`/health`、`/ready`；FastAPI 另挂根路径 `/v1/*`（OpenAI 兼容层）与静态目录。
- **认证**: `OAuth2PasswordBearer` + JWT（bcrypt 口令哈希，jti 黑名单吊销）。认证依赖 `get_current_user`（[deps.py](file:///workspace/server/app/api/deps.py#L39-L60)）。
- **数据流**: 前端 → API → 服务层 → MySQL/Redis/Neo4j/ChromaDB；用户输入 → AI 编排（ContentNormalizer/多 Agent）→ 出站 LLM API；MCP stdio/HTTP(S) 子进程。
- **信任边界**: 未认证面（auth/register、`/api/v1/dev/*`、`/api/v1/models/download/*`、health 等）、已认证用户面、基础设施面（config 控制）。

---

# 高危（High）

## H1. 未认证访问 `/api/v1/dev/*` → 全量用户隐私数据越权读取

**攻击者画像**: 外部未认证攻击者（任何能访问 `/api/` 的网络主体）。

**可控输入向量**: 直接调用以下无认证端点（均不携带也不校验 JWT）：
- `GET /api/v1/dev/traces`（列表，分页）
- `GET /api/v1/dev/traces/{trace_id}`（完整 trace JSON）
- `GET /api/v1/dev/traces/{trace_id}/stream`（实时 SSE 事件流）
- `GET /api/v1/dev/mcp/calls?user=<user_id>`（MCP 调用日志，可按用户过滤）
- `DELETE /api/v1/dev/traces/{trace_id}`（删除任意 trace）

**确切代码路径**:
1. [dev.py](file:///workspace/server/app/api/v1/dev.py#L1-L6) 模块文档明确“do not require authentication”；所有 dev 路由仅依赖 `DbDep`/`ContainerDep`，未使用 `CurrentUserDep`（对比其他路由的 [deps.py](file:///workspace/server/app/api/deps.py#L39-L60)）。
2. [dev.py](file:///workspace/server/app/api/v1/dev.py#L147-L178) `list_traces`：`db.query(PipelineTraceRow)` **无 user 过滤**，分页返回所有用户的 trace 摘要（含 `user_id`、`ref_id`、时间）。
3. [dev.py](file:///workspace/server/app/api/v1/dev.py#L184-L197) `get_trace_detail`：按 `trace_id` 直接返回完整 `trace_json`，无所有权校验。
4. [pipeline_trace.py](file:///workspace/server/app/shared/pipeline_trace.py#L241-L278) `trace_span` 将各阶段 `input_snapshot`（含 `raw_text`）截断后落盘；[conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L526-L565) 在 S2/S3 阶段记录 `{"raw_text": content}` —— **即用户日记/对话原文**，连同 LLM 回复存于 [PipelineTraceRow.trace_json](file:///workspace/server/app/infrastructure/models/pipeline_trace.py#L36)。
5. 前端 [conversation.ts](file:///workspace/src/shared/api/conversation.ts#L186-L190) 会随请求发送 `X-Trace-Id`，服务端据此持久化 trace，因此该表在生产使用中会被正常填充。
6. 路由无条件挂载：[router.py](file:///workspace/server/app/api/v1/router.py#L43)；nginx [nginx.conf](file:///workspace/nginx.conf#L13-L18) 将 `/api/` 全量代理到后端 —— 端点对外可达。
7. 同类问题：`/dev/mcp/calls`（[dev.py](file:///workspace/server/app/api/v1/dev.py#L482-L500)）可按 `user_id` 过滤 MCP 工具调用日志（参数/结果快照，可能含敏感数据）；`/dev/traces/{id}/stream`（[dev.py](file:///workspace/server/app/api/v1/dev.py#L221-L298)）可订阅任意 trace 的实时事件流；`/dev/traces/{id}` DELETE（[dev.py](file:///workspace/server/app/api/v1/dev.py#L203-L215)）可删除任意 trace。

**影响**: 未认证攻击者可枚举并读取**所有用户**的日记原文、对话内容、LLM 请求/响应（含 AI 生成的心理画像）、MCP 工具调用参数与结果 —— 大规模隐私数据泄露；并可任意删除 pipeline trace（完整性破坏）。属 CVSS 高危。

**修复建议**:
- 为 `/api/v1/dev/*` 增加 `CurrentUserDep` + 开发者/管理员角色校验，且所有查询强制按 `user_id` 隔离；
- 或将 dev 路由默认禁用，仅在显式配置（如 `ENABLE_DEV_API=1`）时挂载。

---

# 中危（Medium）

## M1. 会话吊销（登出）在 Redis 降级/多进程下静默失效（JWT 黑名单 fail-open）

**攻击者画像**: 持有已登出（被吊销）或被盗 JWT 的一方。

**可控输入向量**: 任意一个已签发、且已被用户通过 `POST /api/v1/auth/logout` 吊销的 JWT（有效期最长 7 天）。

**确切代码路径**:
1. 登出将 jti 写入黑名单：[auth.py](file:///workspace/server/app/api/v1/auth.py#L92-L113) → [jwt_blacklist.py](file:///workspace/server/app/infrastructure/jwt_blacklist.py#L19-L28)。
2. 黑名单检查在认证依赖中执行：[deps.py](file:///workspace/server/app/api/deps.py#L52-L55)；`is_blacklisted` 依赖 `cache_get`。
3. [redis_client.py](file:///workspace/server/app/infrastructure/redis_client.py#L49-L68) `cache_get` 在 Redis 不可用/异常时**返回 `None`（fail-open）**，且当 `REDIS_URL` 未配置时回退到**进程内 dict**（[redis_client.py](file:///workspace/server/app/infrastructure/redis_client.py#L24-L42)）。
4. 后端以多 worker 运行（README：uvicorn 4 workers），进程内回退缓存仅存于处理登出请求的那一个 worker —— 其余 worker 不感知黑名单；进程重启后黑名单清空。
5. 因此：在无 Redis 或 Redis 故障/重启场景下，**登出不生效**，被吊销令牌在剩余有效期内仍可通过认证。

**影响**: 会话管理失效——用户主动登出后，持有旧令牌者（含此前泄露的令牌）仍可继续访问其全部数据直至令牌自然过期（最长 7 天）。属会话管理安全控制失效。

**修复建议**:
- 将 JWT 黑名单/会话状态置于**共享且必需**的存储（Redis 不可用时 fail-closed：拒绝依赖黑名单的认证，而非静默放行）；
- 或改用短生命周期 token + refresh token 轮换机制，降低吊销依赖。

## M2. 登录/注册接口无速率限制与锁定机制，可在线口令爆破

**攻击者画像**: 外部未认证攻击者。

**可控输入向量**: `POST /api/v1/auth/login` 的 `username`/`password` 表单（OAuth2 密码模式），可无限次提交。

**确切代码路径**:
1. [auth.py](file:///workspace/server/app/api/v1/auth.py#L68-L84) `login` 直接 `verify_password`，无任何限流、锁定或验证码逻辑；`register`（[auth.py](file:///workspace/server/app/api/v1/auth.py#L51-L65)）同样无限流，且对已存在邮箱返回明确错误（可用作账号枚举）。
2. 全仓库无速率限制中间件/依赖（检索 `ratelimit|throttle|slowapi` 仅命中 LLM 抽取的节流逻辑，与认证无关）。
3. 口令哈希为 bcrypt（[auth.py](file:///workspace/server/app/infrastructure/auth.py#L25-L32)），单次验证成本高，但**无失败次数上限**，攻击者可无限重试直至命中弱口令。

**影响**: 弱口令账户可被在线爆破接管（JWT 有效期 7 天，接管后可读取该用户全部日记/对话/记忆）；注册接口可枚举有效邮箱。

**修复建议**:
- 登录/注册增加 IP 级与账号级速率限制及临时锁定；
- 注册返回统一错误信息（或对已存在邮箱返回等价响应）以避免枚举。

---

## 未确认项说明

以下子范围经端到端追踪后**未确认**中等及以上漏洞（供参考，不构成发现）：
- **注入向量**: SQL/Neo4j/ChromaDB 查询均参数化（[entity_graph.py](file:///workspace/server/app/infrastructure/entity_graph.py#L115-L256)）；数据库迁移中动态 SQL 的标识符来自静态内部定义并转义（[database.py](file:///workspace/server/app/infrastructure/database.py#L183-L223)）；子进程调用参数静态（[main.py](file:///workspace/server/app/main.py#L33-L49)）；前端无 `v-html` 使用；上传文件名服务端生成 UUID、按用户隔离（[uploads.py](file:///workspace/server/app/api/v1/uploads.py#L50-L90)）。
- **外部交互**: MCP 端点仅来自环境配置（`MCP_ENDPOINTS`），无用户可控 SSRF 入口；模型下载目标为内置白名单并校验出站 URL（[model_downloader.py](file:///workspace/server/app/services/model_downloader.py#L48-L75)）；OpenAI 兼容层 `/v1/*` 需 JWT 认证（[openai_compat.py](file:///workspace/server/app/api/v1/openai_compat.py#L203-L210)）。
- **敏感数据**: 密钥解析生产环境 fail-fast、开发环境随机生成并持久化，无硬编码默认密钥（[security.py](file:///workspace/server/app/infrastructure/security.py#L32-L59)）；LLM API key 以 Fernet 加密落盘。
- **对象级授权**: 日记/记忆/卡片/对话/标签/导出/自定义技能/定时任务等服务层均按 `user_id` 过滤（抽样 [conversation_service.py](file:///workspace/server/app/services/conversation_service.py#L78-L86)、[card_service.py](file:///workspace/server/app/services/card_service.py#L176) 等），未发现 IDOR。

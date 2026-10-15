# 夜记代码仓库 安全审计报告

- **审计日期**：2026-10-15
- **审计范围**：/workspace（FastAPI 后端 `server/`、Vue 前端 `src/`、Electron 桌面端 `desktop/`、部署配置 `docker-compose.yml` / `nginx.conf` / `.env.example`）
- **方法**：架构梳理 → 四大攻击面分组审计（认证与访问控制 / 注入 / 外部交互 / 敏感数据）→ 每条发现追踪完整端到端代码路径 → 按证据标准保留确认项
- **结论**：确认 **2 个 High、2 个 Medium** 漏洞；另有若干未达确认标准的条目列入备注。

---

## HIGH

### H-1 未认证的 `/api/v1/dev/*` 路由泄露全部用户的日记与会话内容（跨租户数据泄露）

**位置**：[dev.py](file:///workspace/server/app/api/v1/dev.py) 全部 13 条路由（`/dev/traces` L147、`/dev/traces/{trace_id}` L184、`/dev/traces/{trace_id}/stream` L221、`/dev/mcp/calls` L482、`/dev/quality-scan` L447 等）；trace 数据来源：[pipeline_trace.py](file:///workspace/server/app/shared/pipeline_trace.py#L70-L117) + [trace_persistence.py](file:///workspace/server/app/shared/trace_persistence.py#L20-L39)。

**攻击者画像**：外部未认证攻击者（无需任何账号/JWT），仅需能访问后端 HTTP 端口。Docker 部署下后端端口以 `8000:8000` 暴露至宿主 0.0.0.0（[docker-compose.yml](file:///workspace/docker-compose.yml#L73-L74)），且 [nginx.conf](file:///workspace/nginx.conf#L13-L14) 将 `/api/` 全部反代到后端——两种部署形态均可达。

**可控输入向量**：`GET /api/v1/dev/traces?page=1&page_size=100`（无认证，可枚举全部 trace）；`GET /api/v1/dev/traces/{trace_id}`（trace_id 为可枚举 UUID 前缀）；`GET /api/v1/dev/mcp/calls?user=<user_id>`。

**代码路径**：
1. 全部 `/dev/*` 路由函数签名只声明 `DbDep` / `ContainerDep`，**不含** `CurrentUserDep`（无 JWT 校验，见 [deps.py](file:///workspace/server/app/api/deps.py#L39-L65)）。
2. 用户正常使用日记/会话时，trace 无条件记录并落库：
   - [analysis_service.py](file:///workspace/server/app/services/analysis_service.py#L502-L534)：`PipelineTrace(scenario="diary_reply", user_id=user_id)` → `persist_trace(trace_db, trace, ...)`；
   - [conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L1222)：会话同样 `persist_trace`；
   - span 快照记录原始用户内容，如 [graph_nodes.py](file:///workspace/server/app/services/ai/graph_nodes.py#L48) `input_snapshot={"raw_text": state["content"]}`；[truncate_snapshot](file:///workspace/server/app/shared/pipeline_trace.py#L28-L67) 仅截断到 500 字符，**不脱敏**。
3. 攻击者请求 `/dev/traces/{trace_id}` → [get_trace_detail](file:///workspace/server/app/api/v1/dev.py#L184-L197) `json.loads(row.trace_json)` 返回全量输入/输出快照；`/dev/traces` 列表同时返回每条记录的 `user_id`，可据此按用户画像批量拉取。

**影响**：
- 机密性破坏 / 跨租户数据泄露：任意未认证者可读取**所有用户**的日记、对话、LLM 回复、检索内容等核心 PII。
- `/dev/quality-scan`（L447）可未认证反复触发 LLM 质量扫描（`limit` ≤ 20），造成 LLM 配额/费用消耗（资源滥用 DoS）。
- `/dev/traces/{trace_id}/stream`（L221）SSE 实时泄露进行中的 trace 内容。

**修复建议**：
- 为 `/dev/*` 全部路由增加认证（`CurrentUserDep`）并追加管理员/开发者开关（如 `app_env=development` 或显式 `ENABLE_DEV_API=1` 才注册该 router），生产默认关闭。
- trace 落库前对 `input_snapshot/output_snapshot` 做 PII 脱敏（身份证/手机号/邮箱等），或将 trace 按 `user_id` 隔离查询。
- 对外部暴露面收敛：Docker 生产部署将 backend 端口改为仅绑定 `127.0.0.1`，由 nginx 反代；nginx 增加 `/api/v1/dev/` 的拒绝规则。

---

### H-2 docker-compose 内置弱默认密钥，可伪造 JWT 实现任意账户接管

**位置**：[docker-compose.yml](file:///workspace/docker-compose.yml#L59-L60)（backend）与 L103-L104（worker）：`JWT_SECRET_KEY=change-me-in-production-min-32-chars`、`MODEL_KEY_SECRET=change-me-model-key-min-16c`；同时 MySQL `nightdiary_root/nightdiary_pass`（L5-L8）、Neo4j `neo4j/nightdiary_neo4j`（L36）。密钥解析链见 [auth.py](file:///workspace/server/app/infrastructure/auth.py#L35-L45)。

**攻击者画像**：外部未认证攻击者；仓库默认配置即为其攻击前提——按 compose 一键部署而未覆盖环境变量是文档化的默认路径。

**可控输入向量**：攻击者用已知默认 secret 自行构造 JWT payload（`sub` 为目标用户 id、`iat/exp/jti` 自拟），以 HS256 签名。

**代码路径**：
1. [auth.py](file:///workspace/server/app/infrastructure/auth.py#L48-L65) `create_access_token` 使用 `resolve_jwt_secret(settings)` 签名；`resolve_jwt_secret` 优先返回 `settings.jwt_secret_key`，而 compose 将其设为公开已知的占位符——无任何强度校验。
2. [deps.py](file:///workspace/server/app/api/deps.py#L39-L60) `get_current_user` 直接 `jwt.decode(token, secret, algorithms=["HS256"])` 后 `db.get(UserRow, int(payload["sub"]))`——伪造 `sub=1` 即获得 ID=1 用户的全部 API 访问权。

**影响**：认证绕过 → 任意账户接管 → 读取/导出/修改该用户全部日记、记忆、计划、上传文件；配合 H-1 可全量拖取。同文件内 MySQL/Neo4j 弱默认口令还允许在端口暴露时（`3306:3306`、`7474/7687`）直连数据库。

**修复建议**：
- 启动时强校验：`app_env=production` 时若 `JWT_SECRET_KEY`/`MODEL_KEY_SECRET` 命中已知占位符（`change-me` 前缀、长度 < 32 等），直接拒绝启动并提示随机生成。
- `docker-compose.yml`/`.env.example` 移除可复用的固定默认值，改为 `${JWT_SECRET_KEY:?must be set}` 强制注入。
- MySQL/Neo4j 口令生成随机值并仅通过 secret 文件注入；生产不要暴露 `3306/7474/7687` 到宿主。

---

## MEDIUM

### M-1 登录/注册无速率限制 + 开放注册 + 注册邮箱枚举

**位置**：[auth.py](file:///workspace/server/app/api/v1/auth.py#L51-L84)；错误定义见 [errors.py](file:///workspace/server/app/shared/errors.py#L125-L130)。

**攻击者画像**：外部未认证攻击者。

**可控输入向量**：`POST /api/v1/auth/register`（email 枚举）、`POST /api/v1/auth/login`（口令猜测）。全库检索确认**不存在**任何限速/锁定中间件（仅人格提取内部节流）。

**代码路径**：
1. 注册：`db.query(UserRow).filter(email==body.email)` 命中即抛 `EmailAlreadyExistsError`，响应 `409` 且消息为 `邮箱 {email} 已注册`（L53-55）→ 攻击者可批量探测任意邮箱是否注册。
2. 登录：`verify_password` 失败仅返回统一 401 消息，无失败计数、无锁定、无 IP 限速（L68-84）；密码策略仅 `min_length=6`（L28）→ 弱口令可被在线暴力破解。

**影响**：用户枚举（确认目标是否使用本服务，为钓鱼/社工提供弹药）；在线口令爆破导致账户被攻破（危害等级视用户口令强度）。

**修复建议**：登录/注册按 IP+账号维度限速并增加失败锁定与指数退避；注册冲突统一返回不带具体邮箱的 409 消息；提高密码最小长度与复杂度要求（如 ≥10 位含混合字符）。

---

### M-2 未认证 `/dev/quality-scan` 可反复触发 LLM 质量扫描（成本/资源滥用）

**位置**：[dev.py](file:///workspace/server/app/api/v1/dev.py#L447-L458)。

**攻击者画像**：外部未认证攻击者（同 H-1 可达性）。

**可控输入向量**：`POST /api/v1/dev/quality-scan?limit=20&scenario=...`，无认证、无节流，可无限次调用。

**代码路径**：`trigger_quality_scan` → `run_quality_scan(db, container, scenarios, limit)` → 对每个场景抽样最近回复并调用 judge LLM 打分（服务层 [quality_sentinel.py](file:///workspace/server/app/services/quality_sentinel.py)）。

**影响**：反复触发消耗 LLM API 配额与费用；在自托管模型场景下造成计算资源占用（拒绝服务/成本放大）。

**修复建议**：与 H-1 一并加认证；或将该接口限制为仅管理员 + 内置节流（如全局每分钟 1 次）。

---

## 备注（未达确认标准 / 低危）

以下条目经核查**不满足"可论证端到端利用"证据标准**，仅记录备查：

- **前端 token 存 localStorage、无 CSP 等安全响应头**（[auth.ts](file:///workspace/src/stores/auth.ts#L35-L53)、静态站点无 CSP/HSTS）：全前端未发现 `v-html` 渲染，聊天输入有清洗，未确认可利用 XSS → 不确认；建议后续加 CSP 与 httpOnly 会话方案作为纵深防御。
- **LLM 提示注入面**（custom skill / MCP 内容）：自定义技能写入路径有确定性审查 [custom_skill.py](file:///workspace/server/app/domain/skills/custom_skill.py#L131-L182)（措辞改写可能绕过，但技能为 per-user，仅影响本人回复，不构成跨用户/系统风险）；MCP/外部返回内容统一经 [untrusted_content.py](file:///workspace/server/app/shared/untrusted_content.py#L83-L104) 围栏进入 LLM 上下文 → 未确认。
- **模型连接测试 SSRF**：`/models/test-connection` 与存储模型探测均经 `validate_outbound_url`（[model_service.py](file:///workspace/server/app/services/model_service.py#L161-L210)）；`allow_private_model_hosts=True` 放行 loopback/RFC1918 是"本地优先、自托管 LLM"的设计权衡，云元数据段（169.254.0.0/16、100.100.100.200 等）恒被拦截，且 `follow_redirects=False` → 未确认可滥用路径。
- **模型下载端点未认证**（[model_download.py](file:///workspace/server/app/api/v1/model_download.py)）：下载目标 repo 固定、`start()` 有 `all_ready` 幂等保护、路径经 `safe_join` 与 HF 主机 allow-list（[model_downloader.py](file:///workspace/server/app/services/model_downloader.py#L13)）→ 低危，未确认。
- **trace / LLM 调用日志持久化 PII 未脱敏**（[llm_call_tracer.py](file:///workspace/server/app/infrastructure/llm_call_tracer.py#L19-L39)）：放大了 H-1 的泄露影响；本身不独立构成可利用漏洞。
- **上传端点**（[uploads.py](file:///workspace/server/app/api/v1/uploads.py#L50-L90)）：MIME 白名单 + uuid 文件名 + `user_id` 目录隔离 + 所有者校验 → 未确认。
- **Electron 桌面端**（[main.ts](file:///workspace/desktop/src/main.ts#L39-L52)）：`contextIsolation:true`、`sandbox:true`、`nodeIntegration:false`，后端绑定 127.0.0.1 → 配置良好。
- **错误处理器**（[error_handlers.py](file:///workspace/server/app/api/v1/error_handlers.py#L46-L53)）：500 响应不泄露堆栈/内部细节 → 正常。

---

## 审计结论

确认 4 项漏洞（2 High / 2 Medium），其中 H-1 与 H-2 均具备从网络可达端口到敏感数据/账户的完整端到端利用路径，建议优先修复（为 `/dev/*` 加认证、消除默认弱密钥）。未发现其他中等及以上严重度的已确认漏洞。

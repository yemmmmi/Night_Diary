# Night Diary V2 安全审计报告

- 审计日期：2026-11-05
- 审计范围：`/workspace`（server/ 后端、docker-compose.yml、.env.example、nginx.conf）
- 审计方法：架构梳理（入口点 / 信任边界 / 数据流）→ 4 大攻击面分组检查 → 逐条验证端到端利用路径
- 结论：**发现 4 个已确认漏洞（2 高 / 2 中）**，均具备可论证的端到端利用路径。

---

## 高严重度

### H1. 默认/硬编码 JWT 签名密钥 → 认证绕过，任意用户接管

- **位置**
  - [docker-compose.yml](file:///workspace/docker-compose.yml#L59-L60) 与 [docker-compose.yml](file:///workspace/docker-compose.yml#L103-L104)：`JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-me-in-production-min-32-chars}`（仓库内置的公开默认值）
  - [.env.example](file:///workspace/.env.example#L8)：示例文件同样使用该占位密钥
  - [auth.py](file:///workspace/server/app/infrastructure/auth.py#L35-L45)：`resolve_jwt_secret` 直接采用该值，无"拒绝已知默认值"校验
  - [deps.py](file:///workspace/server/app/api/deps.py#L39-L60)：`get_current_user` 完全信任 JWT `sub` 字段
- **攻击者画像**：未认证的外部网络攻击者
- **可控输入向量**：无（攻击者仅需构造一个 JWT，不需要任何服务器输入）
- **代码路径**：`docker-compose.yml` 默认注入公开密钥 → [auth.py L64](file:///workspace/server/app/infrastructure/auth.py#L64) 用 HS256 对称签名（密钥公开即可伪造）→ [decode_access_token L78](file:///workspace/server/app/infrastructure/auth.py#L78) 仅按 `algorithms=[HS256]` 验签 → [deps.py L45-L59](file:///workspace/server/app/api/deps.py#L45-L59) 取 `sub` 直接 `db.get(UserRow, int(user_id))`，未绑定任何服务器侧会话 → 攻击者设置 `sub=任意用户id` 即可完全接管。
  - 连带影响：`MODEL_KEY_SECRET` 同样存在公开默认值 `change-me-model-key-min-16c`，[security.py L62-L66](file:///workspace/server/app/infrastructure/security.py#L62-L66) 用其派生 Fernet 密钥，可解密 [model_provider.py](file:///workspace/server/app/infrastructure/models/model_provider.py#L13-L27) 中加密存储的全部用户 LLM API Key。
- **影响**：认证完全绕过 → 任意用户数据读取/篡改/删除（日记、对话、计划、导出）、解密所有已存 LLM API Key。CVSS 9+（默认部署即触发，无需任何交互）。
- **修复建议**：① 启动时校验 `JWT_SECRET_KEY`/`MODEL_KEY_SECRET` 不等于已知默认值且达到最小长度（如 ≥32 字符），否则 fail-fast；② docker-compose 移除占位默认值，改为必填；③ 发布 .env.example 时使用不可用的随机占位（如 `REQUIRED`）并在文档强调。

### H2. `/api/v1/dev/*` 开发路由无认证 → 全量跨用户敏感数据泄露 + 数据删除 + 资源滥用

- **位置**
  - [dev.py](file:///workspace/server/app/api/v1/dev.py#L1-L30)（模块 docstring 自述 "do not require authentication"；路由 `GET /dev/traces`、`GET /dev/traces/{trace_id}`、`GET /dev/traces/{trace_id}/stream`、`DELETE /dev/traces/{trace_id}`、`GET /dev/stats`、`GET /dev/mcp/calls`、`POST /dev/quality-scan` 等均无 `CurrentUserDep`）
  - [router.py](file:///workspace/server/app/api/v1/router.py#L29-L30)：`api_router` 无全局鉴权依赖，[main.py L246](file:///workspace/server/app/main.py#L246) 无条件挂载
  - 数据源：[pipeline_trace.py L28-L67](file:///workspace/server/app/shared/pipeline_trace.py#L28-L67)（span 快照仅截断不脱敏）、[trace_persistence.py L25-L36](file:///workspace/server/app/shared/trace_persistence.py#L25-L36)（完整 trace_json 落库）、[mcp_call_log.py L31-L32](file:///workspace/server/app/infrastructure/models/mcp_call_log.py#L31-L32)（MCP 调用参数/结果快照）
- **攻击者画像**：未认证的外部网络攻击者
- **可控输入向量**：`GET /api/v1/dev/traces?page_size=100`（遍历分页）、`GET /api/v1/dev/traces/{trace_id}`（已知/枚举 trace_id）、`GET /api/v1/dev/mcp/calls?user=<任意user_id>`（按用户过滤）
- **代码路径**：无认证路由 [dev.py L147-L178](file:///workspace/server/app/api/v1/dev.py#L147-L178) 直接查询全表 `PipelineTraceRow`（含 `user_id`）→ [dev.py L184-L197](file:///workspace/server/app/api/v1/dev.py#L184-L197) 返回完整 `trace_json`；trace 内容来自业务管线各阶段的 `input_snapshot`（如 [graph_nodes.py L48](file:///workspace/server/app/services/ai/graph_nodes.py#L48) `raw_text`、[conversation_ai_service.py L526](file:///workspace/server/app/services/ai/conversation_ai_service.py#L526) 危机检测原始文本），即用户日记原文与对话内容；`DELETE` 可删任意 trace；`POST /quality-scan` 可反复触发 LLM 评测产生费用。
- **影响**：未授权读取全部用户隐私数据（日记/对话/LLM 提示词与输出快照）、跨用户数据删除、未授权 LLM 调用成本滥用（资金/DoS）。
- **修复建议**：① 所有 `/dev/*` 路由加 `CurrentUserDep`，并仅允许管理员/开发角色；② 按 `user_id` 强制过滤 trace 查询；③ 生产环境（`app_env=production`）默认禁用 dev 路由；④ `/quality-scan` 需权限与限流。

---

## 中严重度

### M1. 未认证 `POST /api/v1/models/test-connection` → SSRF 内网探测

- **位置**：[models.py L42-L51](file:///workspace/server/app/api/v1/models.py#L42-L51)（无任何鉴权依赖）→ [model_service.py L161-L180](file:///workspace/server/app/services/model_service.py#L161-L180)（`validate_model_connection`）→ [config.py L155-L160](file:///workspace/server/app/config.py#L155-L160)（`allow_private_model_hosts` 默认 **True**）
- **攻击者画像**：未认证的外部网络攻击者
- **可控输入向量**：请求体 `base_url`（任意 URL）
- **代码路径**：`POST /api/v1/models/test-connection {base_url: "http://127.0.0.1:3306"}` → [model_service.py L169](file:///workspace/server/app/services/model_service.py#L169) `validate_outbound_url(base_url, allow_private=True)` → [url_guard.py L95-L102](file:///workspace/server/app/shared/url_guard.py#L95-L102) 仅永久封禁链路本地/云元数据（169.254.169.254 等），**放行 127.0.0.1 与 RFC1918** → [L177-L180](file:///workspace/server/app/services/model_service.py#L177-L180) 以 `Authorization: Bearer <攻击者key>` 发起 `GET /v1/models` 与 `POST /v1/chat/completions` 探测，返回目标状态码/错误信息。
- **影响**：服务器作为跳板对内网（如 Docker 网络中的 MySQL:3306、Redis:6379 及其他容器/宿主机服务）进行端口扫描与服务指纹识别（状态码/错误信息 oracle）；可造成内部服务异常请求（拒绝服务）。云元数据因 [url_guard.py L37-L55](file:///workspace/server/app/shared/url_guard.py#L37-L55) 的固定封禁不受影响。
- **修复建议**：① 该端点加 `CurrentUserDep`；② 默认 `allow_private_model_hosts=False`，仅对显式配置的自托管 LLM 放行内网；③ 增加请求速率限制与 URL 规范化（防 DNS rebinding 需二次解析校验）。

### M2. 登录/注册端点无速率限制 → 暴力破解

- **位置**：[auth.py L51-L84](file:///workspace/server/app/api/v1/auth.py#L51-L84)（`/api/v1/auth/register`、`/api/v1/auth/login`）；全代码库检索未发现任何限流中间件/失败锁定机制（无 ratelimit/slowapi/throttle 实现）
- **攻击者画像**：未认证的外部网络攻击者
- **可控输入向量**：任意数量的登录请求（用户名/密码组合）
- **代码路径**：`POST /api/v1/auth/login` → [auth.py L68-L84](file:///workspace/server/app/api/v1/auth.py#L68-L84) 每次均执行 bcrypt 校验并返回统一成功/失败响应，无尝试次数上限、无 IP 封禁、无验证码。
- **影响**：弱口令用户账号可被在线暴力破解（账号接管）；同时大量 bcrypt 校验可消耗 CPU 造成拒绝服务。
- **修复建议**：为 login/register 增加基于 IP+账号的速率限制与失败锁定（指数退避），引入验证码或设备指纹；对已注册邮箱的枚举响应做统一化。

---

## 已检查并排除的常见风险面（无确认漏洞）

- **SQL 注入**：[database.py L141-L223](file:///workspace/server/app/infrastructure/database.py#L141-L223) 中 `ALTER/UPDATE` 采用字符串拼接，但表名/列名全部来自硬编码字典，非用户输入；各 repository 查询均使用 SQLAlchemy 绑定参数。
- **命令注入**：`model_downloader`（repo_id 为硬编码常量）、`mcp_server`（stdio 配置来自环境变量）均无用户可控命令串。
- **路径穿越**：上传文件名服务端生成 UUID（[uploads.py L76-L78](file:///workspace/server/app/api/v1/uploads.py#L76-L78)），下载路径按 `user_id` 隔离过滤（[uploads.py L39-L47](file:///workspace/server/app/api/v1/uploads.py#L39-L47)），并有 `safe_join` 兜底。
- **跨用户越权（IDOR）**：抽查 diary/card/conversation/plan/memory/export/custom-skills/tags/weekly 等路由，均以 JWT 身份 `user_id` 过滤，未发现客户端可控 user_id 注入。
- **API Key 明文回显**：[model_service.py L232+](file:///workspace/server/app/services/model_service.py) 响应仅返回 `has_api_key`/`key_count`，不回显明文密钥。
- **Web 搜索**：[web_search_service.py L43-L47](file:///workspace/server/app/services/web_search_service.py#L43-L47) 目标 URL 为固定常量，搜索词非 URL，无 SSRF。
- **JWT 算法混淆**：`decode` 显式限定 `algorithms=[settings.jwt_algorithm]`，拒绝 `alg=none`。

---

## 修复优先级建议

1. **立即**：H1（替换默认 JWT/MODEL_KEY 密钥并加启动校验）、H2（dev 路由加鉴权 + 生产禁用）。
2. **近期**：M1（test-connection 加鉴权 + 收紧 allow_private 默认值）、M2（登录限流）。

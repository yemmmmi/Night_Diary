# Night Diary V2 安全审计报告

- **审计日期**：2026-11-09
- **审计对象**：Night Diary V2（服务端 + 前端）
- **审计范围**：`server/`、`docker-compose.yml`、`nginx.conf`、`.env.example`、`src/`
- **审计方法**：架构梳理 + 四组攻击面审查（认证与访问控制 / 注入 / 外部依赖与出站 / 敏感数据）+ 端到端路径确认（对候选发现逐一回读源码验证，剔除理论性候选、合并跨报告重复条目；行号均为 2026-11-09 工作区现状）
- **依据**：`.trae/specs/security-audit/findings-confirmed.md`（Task 6 已确认发现清单）
- **评级口径**：严重（Critical）→ 高（High）→ 中（Medium）→ 低风险补充项（< 中，未达收录阈值，供参考）

---

## 审计总结

本次审计共确认 **10 项中及以上漏洞**，其中**严重 2 项**（CF-1、CF-2）、**高 3 项**（CF-3、CF-4、CF-5）、**中 5 项**（CF-6～CF-10）。另有 2 项评级为「低-中」的补充项（CF-11、CF-12）未达中等阈值，列于报告末尾「低风险补充项」小节供参考，不纳入确认漏洞总数。

**已排除说明**：Task 3 全部注入向量已排除——SQL 全走 ORM/参数化/常量，subprocess 全固定参数或属运维配置面（MCP stdio env 经 `SAFE_ENV_KEYS` 白名单），文件路径由 int user_id + UUID + 扩展名白名单构成，提示词注入无跨用户数据入口（检索内容均同用户自写）；F13（JWT 存 localStorage）因全前端 `src/` 检索无 `v-html`/`innerHTML`/`dangerouslySetInnerHTML`/`document.write`/`eval`、**无已确认 XSS 向量**而被剔除（仅在未来出现 XSS 时放大影响，建议改 httpOnly+Secure cookie 作加固）；F10（Fernet 无 KDF/无轮换）降级为加固缺口（无 KDF 部分已被 CF-2 覆盖）；V-2（web 搜索结果 URL 前端渲染）保留低危观察（建议 `scheme ∈ {http,https}` 白名单）；V-3（ChatOpenAI 走系统代理）属部署上下文待定，与 CF-5 同源随其一并修复；F11/F14/F9/F5 经核查为良好实践（API 面不回显明文/密文 key、拦截器统一注入 Authorization、日志不打印密钥、.env.example 无真实密钥）。

---

## 一、严重（Critical）

### CF-1【严重】默认部署公开 JWT 签名密钥 → 伪造 JWT 任意用户接管

- **位置**：[file:///workspace/docker-compose.yml:59](file:///workspace/docker-compose.yml#L59)、[file:///workspace/docker-compose.yml:103](file:///workspace/docker-compose.yml#L103)；[file:///workspace/server/app/infrastructure/auth.py:35-45](file:///workspace/server/app/infrastructure/auth.py#L35)；[file:///workspace/server/app/infrastructure/security.py:48-52](file:///workspace/server/app/infrastructure/security.py#L48)；[file:///workspace/server/app/api/deps.py:39-60](file:///workspace/server/app/api/deps.py#L39)；[file:///workspace/server/app/api/v1/auth.py:51-65](file:///workspace/server/app/api/v1/auth.py#L51)
- **攻击者画像**：任意网络可达 backend:8000 或 nginx:80 的匿名攻击者（docker-compose 将 backend 8000 直接映射宿主，无需任何账号）。
- **可控输入向量**：`Authorization: Bearer <伪造JWT>`；注册接口（拿合法自增 user id）；未鉴权 `GET /api/v1/dev/traces`（枚举全部 user_id）。
- **确切代码路径**：默认密钥注入（compose:59/103：`JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-me-in-production-min-32-chars}`，未设 env 时 Compose 静默注入公开占位值，且 `APP_ENV=production` 于 :56）→ `resolve_jwt_secret`（auth.py:35-45）占位值非空直接返回，`_resolve_secret` 的生产 fail-fast（security.py:48-52）仅对 `model_key_secret` 为空生效，被默认值绕过（死代码）→ `get_current_user`（deps.py:39-60）→ `decode_access_token`（auth.py:68-78，HS256+占位密钥）→ `db.get(UserRow, int(user_id))` → 返回目标用户。user id 枚举：① `POST /auth/register` 返回自增 `UserResponse.id`（auth.py:51-65）；② 未鉴权 `GET /api/v1/dev/traces` 返回全部 user_id（dev.py:147-178，见 CF-3）。V2 下游：黑名单吊销仅对携带 `jti` 的 token 生效（deps.py:53-54），正常签发必带 jti（auth.py:63），但**伪造 token 可直接省略 jti 或每次换新 jti**，登出黑名单对伪造 token 无效——V2 行为属实，独立利用前提即本条，并入本修复。
- **影响**：任意用户完整接管（CIA 全破坏）；审计不可信；联动 CF-2 解密全部 LLM API Key。
- **修复建议**：① compose 去掉 `:-占位值`，改 `${JWT_SECRET_KEY:?}` 必填，启动校验命中已知占位值/长度不足时生产 fail-fast；② JWT 与 Fernet 密钥分离；③ `decode_access_token` 强制校验 `sub` 为数字、**`jti` 必填**（缺 jti 拒绝）；④ `/dev/*` 路由生产不挂载（CF-3）。

### CF-2【严重】公开 MODEL_KEY_SECRET + MySQL 默认口令 → 全部用户 LLM API Key 可解密

- **位置**：[file:///workspace/docker-compose.yml:60](file:///workspace/docker-compose.yml#L60)、[file:///workspace/docker-compose.yml:104](file:///workspace/docker-compose.yml#L104)；[file:///workspace/server/app/infrastructure/security.py:26-29](file:///workspace/server/app/infrastructure/security.py#L26)、[file:///workspace/server/app/infrastructure/security.py:62-66](file:///workspace/server/app/infrastructure/security.py#L62)；[file:///workspace/server/app/services/model_service.py:252-253](file:///workspace/server/app/services/model_service.py#L252)、[file:///workspace/server/app/services/model_service.py:303](file:///workspace/server/app/services/model_service.py#L303)；[file:///workspace/server/app/shared/llm_factory.py:69](file:///workspace/server/app/shared/llm_factory.py#L69)；[file:///workspace/docker-compose.yml:5-8](file:///workspace/docker-compose.yml#L5)、[file:///workspace/docker-compose.yml:9-10](file:///workspace/docker-compose.yml#L9)
- **攻击者画像**：能连接 MySQL 3306 的局域网攻击者（compose 默认映射宿主且口令公开）；或经 CF-1 越权者；或数据库备份/泄露持有者。
- **可控输入向量**：`model_providers.api_key_encrypted` / `api_keys_encrypted` 密文（库内）；公开占位值 `change-me-model-key-min-16c`。
- **确切代码路径**：默认密钥注入（compose:60/104）→ `_derive_fernet_key` = `base64.urlsafe_b64encode(sha256(passphrase))`（security.py:26-29）——**单轮 SHA256、无 salt**，对公开占位值任何人可直接算出 Fernet 密钥，无需暴力破解；`get_fernet`（security.py:62-66）对非 44 字符密钥走该派生 → 落库加密（model_service.py:252-253/303）、运行时解密（llm_factory.py:69、model_service.py:54-61）。DB 读取链：MySQL 默认口令 `nightdiary/nightdiary_pass`（compose:5-8）+ `3306:3306` 映射宿主（compose:9-10）→ 局域网 `mysql -h host -P 3306 -unightdiary -pnightdiary_pass` 直连 → 读 `model_providers` 表 → 公开派生密钥解密。已核实：`model_to_public_dict` 仅返回 `has_api_key/key_count` 布尔（model_service.py:320-334），密文无 API 出口，故本条依赖 DB 读取链。
- **影响**：全部用户 LLM 厂商凭据泄露（盗刷/转卖/资损）；配合 CF-1 实现无痕接管 LLM 成本面。
- **修复建议**：同 CF-1（强制唯一强密钥 + 拒绝占位值）；MySQL/Redis/Neo4j 默认口令必填化 + 端口仅绑内网（CF-9）；派生改 scrypt/PBKDF2+随机 salt，或直接 `Fernet.generate_key()` 44 字符随机 key（`get_fernet` 已支持）。

---

## 二、高（High）

### CF-3【高】/api/v1/dev/* 全路由无鉴权：跨用户 trace（日记原文/LLM 内容）泄露 + 匿名破坏与资源消耗

- **位置**：[file:///workspace/server/app/api/v1/router.py:43](file:///workspace/server/app/api/v1/router.py#L43)；[file:///workspace/server/app/api/v1/dev.py:1-7](file:///workspace/server/app/api/v1/dev.py#L1)、[file:///workspace/server/app/api/v1/dev.py:147-178](file:///workspace/server/app/api/v1/dev.py#L147)、[file:///workspace/server/app/api/v1/dev.py:184-197](file:///workspace/server/app/api/v1/dev.py#L184)、[file:///workspace/server/app/api/v1/dev.py:221-298](file:///workspace/server/app/api/v1/dev.py#L221)、[file:///workspace/server/app/api/v1/dev.py:203-215](file:///workspace/server/app/api/v1/dev.py#L203)、[file:///workspace/server/app/api/v1/dev.py:447-458](file:///workspace/server/app/api/v1/dev.py#L447)、[file:///workspace/server/app/api/v1/dev.py:482-500](file:///workspace/server/app/api/v1/dev.py#L482)、[file:///workspace/server/app/api/v1/dev.py:409-429](file:///workspace/server/app/api/v1/dev.py#L409)；[file:///workspace/server/app/shared/pipeline_trace.py:28-67](file:///workspace/server/app/shared/pipeline_trace.py#L28)；[file:///workspace/server/app/api/v1/conversation.py:101](file:///workspace/server/app/api/v1/conversation.py#L101)、[file:///workspace/server/app/api/v1/conversation.py:167](file:///workspace/server/app/api/v1/conversation.py#L167)；[file:///workspace/server/app/api/v1/openai_compat.py:226](file:///workspace/server/app/api/v1/openai_compat.py#L226)；[file:///workspace/src/shared/api/http.ts:57-73](file:///workspace/src/shared/api/http.ts#L57)
- **攻击者画像**：任意匿名网络攻击者（backend:8000 直连宿主）。
- **可控输入向量**：`trace_id`/`ref_id`/`scenario`/`user` 查询参数；`POST /quality-scan` 的 `limit/scenario`；请求头 `X-Trace-Id`（任意值，**无需开发者模式**）。
- **确切代码路径**：dev 路由在生产同样无条件挂载（router.py:43 `include_router(dev.router)`，无 `APP_ENV` 条件），全部 dev 函数无 `CurrentUserDep`。① `GET /dev/traces`（dev.py:147-178）：全用户 trace 摘要（`user_id`/`ref_id`=conversation_id/`trace_id`），可按 `ref_id` 锁定目标会话；② `GET /dev/traces/{trace_id}`（dev.py:184-197）：完整 `trace_json`，敏感快照含用户原文 `input_snapshot={"raw_text": content}`（conversation_ai_service.py:526/565/610/652/854/945/981/1120）、检索词（:739/:754）、MCP 工具全量参数（tool_registry.py:173-178）、LLM 生成节点（graph_nodes.py:191），`truncate_snapshot` 仅截断至 500 字符不脱敏（pipeline_trace.py:28-67）；③ trace 落盘触发：任意请求携带 `X-Trace-Id` 即指定 trace_id 并落库（conversation.py:101/167/320、openai_compat.py:226）→ trace_persistence.py:20-43，trace 在生成**完成时**落库（conversation_ai_service.py:1222）；④ `GET /dev/traces/{trace_id}/stream`（dev.py:221-298）：**无鉴权 SSE**，订阅 TraceEventBus 的 `trace_id` topic 获取实时事件并回放 DB 中已完成 span/全量 trace；⑤ `DELETE /dev/traces/{trace_id}`（dev.py:203-215）：匿名删除任意 trace；⑥ `POST /dev/quality-scan`（dev.py:447-458）：匿名触发对**全部用户**近期回复的 LLM 评审（采样无 user 过滤，quality_sentinel.py:95-152）；⑦ `GET /dev/mcp/calls`（dev.py:482-500）：MCP 调用日志（`arguments_snapshot`/`result_snapshot` 全量，2KB 截断无脱敏，mcp_call_tracer.py:63-113），**可按 `user` 参数过滤**跨租户读取；⑧ `GET /dev/middleware-status`（dev.py:409-429）：Redis/Neo4j/MySQL/LLM/RAG 拓扑泄露，辅助内网攻击（联动 CF-6）。**V3 核实结论**：`X-Trace-Id` 客户端完全可控并成为 SSE trace_id（openai_compat.py:226→153），前端仅在开发者模式附加该头（http.ts:57-73）；实时窃听需在流完成前获知 trace_id（默认 uuid4 不可猜）→ **条件性**；trace 完成后的**无鉴权全量读取无条件成立**，V3 并入本条。
- **影响**：多租户完全破坏——匿名读取任意用户日记原文（前 500 字符）、检索词、MCP 工具参数/结果（可能含第三方 API key）、LLM 中间输出；匿名触发跨用户 LLM 评审（数据外发+成本）；匿名删除审计数据；实时流窃听条件性成立。
- **修复建议**：① dev 路由全部加 `CurrentUserDep`，生产（`APP_ENV=production`）不挂载；② trace/mcp 查询强制 `user_id` 过滤；③ `quality-scan` 鉴权+限流；④ 流式会话改走鉴权通道，SSE 订阅前校验 trace 归属；⑤ 敏感 snapshot 落盘前脱敏。

### CF-4【高】跨用户 LLM provider 解析：生产 LLM 调用链未传 user_id → 全站流量使用他人 provider/API Key

- **位置**：[file:///workspace/server/app/services/model_service.py:337-354](file:///workspace/server/app/services/model_service.py#L337)；[file:///workspace/server/app/shared/llm_factory.py:121-175](file:///workspace/server/app/shared/llm_factory.py#L121)、[file:///workspace/server/app/shared/llm_factory.py:234-252](file:///workspace/server/app/shared/llm_factory.py#L234)；[file:///workspace/server/app/services/container.py:362-396](file:///workspace/server/app/services/container.py#L362)、[file:///workspace/server/app/services/container.py:378](file:///workspace/server/app/services/container.py#L378)、[file:///workspace/server/app/services/container.py:498-517](file:///workspace/server/app/services/container.py#L498)；[file:///workspace/server/app/services/ai/conversation_loop.py:516](file:///workspace/server/app/services/ai/conversation_loop.py#L516)、[file:///workspace/server/app/services/ai/conversation_loop.py:844](file:///workspace/server/app/services/ai/conversation_loop.py#L844)
- **攻击者画像**：任意已注册用户（或 CF-1 下伪造身份者）。受害面为**全库其余用户**。
- **可控输入向量**：正常注册 + 配置自己的 ModelProvider（`POST /api/v1/models`，base_url/api_key 用户可控）；或 CF-1 伪造 provider 所有者身份。
- **确切代码路径**：跨用户解析原语 `get_active_provider_for_tier(user_id=None)`（model_service.py:337-354）**不加 user 过滤**，返回全库 id 最小的活跃 provider；`resolve_by_tier(user_id=None)`（llm_factory.py:121-175）初始查询无 user 过滤（L137-141），按 tier 分组后取全库该 tier 首个活跃 provider 所属用户的 provider（L157-168），无活跃时还回退全表（L144-150）。**生产消费点全部未传 user_id**（15+ 处）：主对话路径 `container._llm_for_tier`（container.py:362-396→378）→ conversation_loop.py:516/844（对应 `POST /conversations/{id}/messages`、`/messages/stream`、`/v1/chat/completions`）；digest（digest_worker.py:193）；周报 weekly_service.py:362/512/526（`build_execution_planner`，container.py:498-517）；分析 analysis_service.py:116/120；工具意图 tool_registry.py:137、conversation_ai_service.py:406/720/1051；MCP mcp_server.py:64；技能 user_skill_service.py:68/117；质量哨兵 quality_sentinel.py:169；健康探测 dev.py:110。正确传 user_id 的仅 card.py:238 与 `create_for_tier` 的 3 个调用点（scheduled_task_service.py:454、personality_extractor.py:133、entity_extractor.py:282）。客户端构造 `_build_client`（llm_factory.py:234-252）→ `ChatOpenAI(base_url=provider.base_url, api_key=decrypted_key)`。
- **影响**：跨租户凭据使用与记账错乱；全站 LLM 流量可被单一用户劫持（数据外发、响应投毒）；LLM 层 SSRF 放大（联动 CF-5）。
- **修复建议**：① `get_active_provider_for_tier`/`resolve_by_tier` 删除 user_id=None 回退（或回退仅限 env 默认 LLM，绝不跨用户）；② `_llm_for_tier`/`build_execution_planner`/`build_multi_agent_graph` 强制接收并透传 user_id（llm_factory 全链路传入 user_id）；③ 增加回归测试：多用户各配 provider 时 A 的流量绝不解析到 B 的 provider。

### CF-5【高】PUT /api/v1/models/{id} 仅更新 base_url 绕过 url_guard → 运行时 LLM 直连任意内网 + 默认跟随重定向

- **位置**：[file:///workspace/server/app/services/model_service.py:282-303](file:///workspace/server/app/services/model_service.py#L282)；[file:///workspace/server/app/api/schemas.py:115-121](file:///workspace/server/app/api/schemas.py#L115)；[file:///workspace/server/app/shared/llm_factory.py:234-252](file:///workspace/server/app/shared/llm_factory.py#L234)；[file:///workspace/server/pyproject.toml:22](file:///workspace/server/pyproject.toml#L22)
- **攻击者画像**：任意已登录用户（默认部署下 CF-1 可伪造任意身份）；联动 CF-4 后影响范围扩大到全库用户。
- **可控输入向量**：`PUT /api/v1/models/{id}`，body 仅 `{"base_url": "https://<攻击者域名>"}`（`ModelUpdateRequest` 全字段可选）。
- **确切代码路径**：校验绕过——`update_model`（model_service.py:282-303）中 `base_url` 直接赋值落库（L287-288），`validate_model_connection` **仅在 `api_key is not None` 分支触发**（L293-302），只改 base_url 完全跳过校验；对比 `create_model`（L245 必校验）与 `test_stored_model_connection`（L213-229），update 是唯一绕过路径。运行时出站无二次校验：`_build_client`（llm_factory.py:234-252）`ChatOpenAI(base_url=...)` 无 url_guard、无 `follow_redirects=False`。**重定向跟随实测（本轮）**：项目约束 `openai>=1.40,<2.0`（pyproject.toml:22），实测 openai 1.109.1 的 `_DefaultHttpxClient`/`_DefaultAsyncHttpxClient` 均 `kwargs.setdefault("follow_redirects", True)`（openai/_base_client.py:793/1315）——**SDK 默认跟随重定向**；langchain-openai `ChatOpenAI` 未传 `http_client` → 运行时请求跟随 3xx。触发：`POST /conversations/{id}/messages` → conversation_loop.py:516；或经 CF-4 被全库流量触发。SSRF 端到端判定：① 内网直连**成立**（base_url 写 `http://127.0.0.1:8000`/`http://10.x.x.x` 无校验落库，运行时向内网 HTTP 服务注入固定 LLM 请求）；② 重定向至云元数据**条件成立**（302/307 → `http://169.254.169.254/latest/meta-data/…`，元数据响应按 OpenAI JSON 解析失败故凭据直接回读受限，但 **307/308 保留方法/POST body 转发至内部端点成立**）；③ 攻击者服务器直接接收**无条件成立**（全量 LLM 请求体外传 + 可回投任意模型回复，响应投毒）；④ DNS rebinding 成立（保存时解析公网、运行时重解析内网）；⑤ 无鉴权 `POST /models/test-connection`（CF-6）已显式 `follow_redirects=False`（model_service.py:134）——探测面不跟随，运行时 LLM 面跟随，行为不一致。
- **影响**：已登录用户 → 服务器为跳板访问内网 HTTP 服务/注入请求、LLM 流量劫持与内容外传、模型回复投毒；配合默认公开 JWT 密钥等同无鉴权；联动 CF-4 放大为全库影响。
- **修复建议**：① `update_model` 中 base_url 变更强制走 `validate_model_connection`（与 create 一致）；② `_build_client` 对 base_url 做运行时校验 + 显式 `follow_redirects=False`（`openai.Client(http_client=自定义 httpx)` 或 `max_redirects=0`）+ 校验后 IP 绑定连接防 DNS rebinding；③ 默认关闭 `allow_private_model_hosts`。

---

## 三、中（Medium）

### CF-6【中】无鉴权 POST /api/v1/models/test-connection → 内网 HTTP 探测原语（受限 SSRF）

- **位置**：[file:///workspace/server/app/api/v1/models.py:42-51](file:///workspace/server/app/api/v1/models.py#L42)；[file:///workspace/server/app/services/model_service.py:161-210](file:///workspace/server/app/services/model_service.py#L161)、[file:///workspace/server/app/services/model_service.py:128-134](file:///workspace/server/app/services/model_service.py#L128)；[file:///workspace/server/app/api/schemas.py:124-127](file:///workspace/server/app/api/schemas.py#L124)；[file:///workspace/server/app/config.py:155-160](file:///workspace/server/app/config.py#L155)；[file:///workspace/server/app/shared/url_guard.py:38-45](file:///workspace/server/app/shared/url_guard.py#L38)
- **攻击者画像**：任意匿名攻击者（无需账号）。
- **可控输入向量**：请求体 `ModelTestConnectionRequest` 任意 `base_url`（仅 `min_length=1`）+ 任意 `api_key` + `model_name`。
- **确切代码路径**：入口无鉴权（models.py:42-51，无 `CurrentUserDep`）→ `validate_model_connection`（model_service.py:161-210）：先 `validate_outbound_url(base_url, allow_private=…)`（L169）再 GET `{base}/models` 与 POST `{base}/v1/chat/completions`（payload 固定，带 Bearer 任意 key）。私有放行：`allow_private_model_hosts` 默认 **True**（config.py:155-160），url_guard 仅无条件拦截链路本地/云元数据（url_guard.py:38-45），loopback/RFC1918/ULA 默认放行（L48-55、L98-101）；DNS 校验与请求分离存在 TOCTOU（DNS rebinding，L70-86）。缓解：`follow_redirects=False`、`trust_env=False`（model_service.py:128-134）——无重定向型 SSRF。
- **影响**：匿名内网端口/HTTP 指纹扫描（200/401/404/405 响应码区分，L178-202）；对内部 HTTP 服务发送固定 Bearer POST 体；反复调用消耗资源。响应体不返回 → **受限 SSRF**。联动 CF-3 的 `middleware-status` 可绘制内网拓扑。
- **修复建议**：① 加鉴权 + 限流；② 生产默认 `allow_private_model_hosts=False`；③ 校验与请求原子化（解析 IP 传给连接层，禁止二次解析）。

### CF-7【中】无鉴权触发 HF 权重下载/状态探测 → 资源消耗 DoS

- **位置**：[file:///workspace/server/app/api/v1/model_download.py:14-42](file:///workspace/server/app/api/v1/model_download.py#L14)；[file:///workspace/server/app/services/model_downloader.py:152-174](file:///workspace/server/app/services/model_downloader.py#L152)、[file:///workspace/server/app/services/model_downloader.py:19-22](file:///workspace/server/app/services/model_downloader.py#L19)
- **攻击者画像**：任意匿名攻击者。
- **可控输入向量**：`POST /api/v1/models/download/start`（无参数）、轮询 `GET /api/v1/models/download/status`。
- **确切代码路径**：两路由均无 `CurrentUserDep`（model_download.py:14-42）→ `start()` 起 daemon 线程 `snapshot_download`（model_downloader.py:152-174）。已核实修正：`repo_id` 来自硬编码 `REQUIRED_MODELS`（model_downloader.py:19-22），**无任意模型名/URL 注入**；`hf_endpoint` 过白名单（L59-70）；`safe_join` 防路径逃逸（L79-81）。
- **影响**：匿名反复触发全量权重下载（bge-small-zh≈100MB+/bge-reranker≈1GB）耗尽磁盘/带宽；单线程互斥（L159）降低并发但轮询状态仍放大 I/O。
- **修复建议**：加鉴权（或仅开发环境可用）+ 限流。

### CF-8【中】注册/登录无速率限制：口令爆破、撞库、邮箱枚举

- **位置**：[file:///workspace/server/app/api/v1/auth.py:51-65](file:///workspace/server/app/api/v1/auth.py#L51)、[file:///workspace/server/app/api/v1/auth.py:68-84](file:///workspace/server/app/api/v1/auth.py#L68)；[file:///workspace/server/app/api/v1/auth.py:27-28](file:///workspace/server/app/api/v1/auth.py#L27)
- **攻击者画像**：任意网络攻击者。
- **可控输入向量**：`POST /auth/register`（email/password/nickname）、`POST /auth/login`（OAuth2 表单）。
- **确切代码路径**：register（auth.py:51-65）、login（auth.py:68-84）。全仓无任何限流中间件；登录失败统一文案（L74-75，无登录侧枚举）；但 register 对已存在邮箱返回 `EmailAlreadyExistsError`（L53-55）→ **注册侧邮箱枚举**；密码仅 `min_length=6`（schemas.py:27-28）；bcrypt 12 rounds 抬高单次成本但不防分布式。
- **影响**：口令爆破/撞库、邮箱注册状态枚举、批量注册消耗 bcrypt CPU。
- **修复建议**：IP+账号维度限流（失败计数、锁定/退避）；register 失败与 login 同文案；密码策略加强；可选验证码。

### CF-9【中】基础设施默认口令 + 端口直连宿主

- **位置**：[file:///workspace/docker-compose.yml:5-8](file:///workspace/docker-compose.yml#L5)、[file:///workspace/docker-compose.yml:9-10](file:///workspace/docker-compose.yml#L9)、[file:///workspace/docker-compose.yml:22-23](file:///workspace/docker-compose.yml#L22)、[file:///workspace/docker-compose.yml:36](file:///workspace/docker-compose.yml#L36)、[file:///workspace/docker-compose.yml:38-40](file:///workspace/docker-compose.yml#L38)、[file:///workspace/docker-compose.yml:70](file:///workspace/docker-compose.yml#L70)、[file:///workspace/docker-compose.yml:108](file:///workspace/docker-compose.yml#L108)
- **攻击者画像**：局域网/可直连 3306/6379/7474/7687 端口的攻击者。
- **可控输入向量**：各服务默认口令与宿主端口映射（部署面，无独立业务输入）。
- **确切代码路径**：MySQL `nightdiary_root`/`nightdiary_pass`（compose:5-8）+ `3306:3306`（:9-10）；Redis 无认证 `6379:6379`（:22-23）；Neo4j `neo4j/nightdiary_neo4j` **硬编码无 env 覆盖**（:36）+ `7474/7687`（:38-40）；worker 侧 `:70`、`:108` 同类问题。
- **影响**：默认部署下可直连 MySQL/Redis/Neo4j 读写全部日记/会话/画像数据（MySQL 无 TLS）；是 CF-2 读取链的前置面。
- **修复建议**：Neo4j 口令改 `${NEO4J_PASSWORD:?}` 必填；数据库端口仅绑定内网（127.0.0.1 或 compose 内网网络）；MySQL 启用 TLS；Redis 加认证。

### CF-10【中】MCP 端点 URL 与 stdio 命令未过 url_guard（配置面 SSRF / 任意子进程）

- **位置**：[file:///workspace/server/app/config.py:107-120](file:///workspace/server/app/config.py#L107)；[file:///workspace/server/app/services/ai/tool_registry.py:67-70](file:///workspace/server/app/services/ai/tool_registry.py#L67)；[file:///workspace/server/app/services/ai/mcp_connections.py:198-213](file:///workspace/server/app/services/ai/mcp_connections.py#L198)、[file:///workspace/server/app/services/ai/mcp_connections.py:230-247](file:///workspace/server/app/services/ai/mcp_connections.py#L230)、[file:///workspace/server/app/services/ai/mcp_connections.py:267-288](file:///workspace/server/app/services/ai/mcp_connections.py#L267)
- **攻击者画像**：能篡改部署环境变量者（docker-compose/CI 供应链投毒、配置注入）——非直接网络面，属信任边界缺口。
- **可控输入向量**：`MCP_ENDPOINTS`/`MCP_STDIOS` 环境变量。
- **确切代码路径**：tool_registry.py:67-70 → mcp_connections.py:198-213（SSE）/230-247（streamable HTTP）**直接建连未校验**；stdio 子进程按 `command+args` spawn（:267-288）。已核实缓解：子进程 env 经 `SAFE_ENV_KEYS` 白名单（mcp_config.py:16-66）不透传 LLM/DB 凭据；MCP 返回回灌 prompt 前已 `wrap_untrusted`（untrusted_content.py:83-104 + conversation_loop.py:235）——prompt 注入面已缓解。
- **影响**：配置被篡改时 → 任意 URL SSRF（agent 调用即触发）+ 任意命令在 backend 容器内执行。
- **修复建议**：`ToolRegistry.initialize` 对 http(s) 端点过 `validate_outbound_url(allow_private=False)`；stdio command 允许列表（uvx/npx/绝对路径白名单）；连接目标审计日志。

---

## 四、低风险补充项（未达中等阈值，供参考）

> 以下两项评级为「低-中」，未达到本报告收录阈值（≥ 中），**不纳入确认漏洞总数**，仅作参考。

### CF-11【低-中】流式 abort 端点不校验会话归属（条件性利用）

- **位置**：[file:///workspace/server/app/api/v1/conversation.py:212-229](file:///workspace/server/app/api/v1/conversation.py#L212)、[file:///workspace/server/app/api/v1/conversation.py:228](file:///workspace/server/app/api/v1/conversation.py#L228)
- **攻击者画像**：任意已登录用户（CF-1 下可伪造任意身份）。
- **可控输入向量**：`POST /api/v1/conversations/{conversation_id}/messages/abort`，body 任意 `{"trace_id": ...}`（`body: dict[str, Any]` 无 schema 校验）。
- **确切代码路径**：`abort_message`（conversation.py:212-229）**从不校验 conversation_id 归属**（不调用 `get_conversation`），仅 `get_task_registry().cancel(trace_id)`（L228；注册于 L202）——凭全局 trace_id 即可取消任意用户的流式任务。利用前提：需获知**活跃** trace_id（流完成前）；已核实活跃 trace_id 不可经 `/dev/traces` 枚举（trace 仅完成时落库，conversation_ai_service.py:1222），默认 uuid4 不可猜；但若受害者使用可预测 X-Trace-Id，或攻击者与受害者同进程观察（多租户同容器），可中断他人流式回复。`streaming_enabled` 默认关（config.py:231-236）进一步降低实际暴露。
- **影响**：轻微 DoS（中断他人流式回复），归属校验缺失事实成立。
- **修复建议**：abort 前校验 conversation 归属（与 `get_conversation(db, user_id, conversation_id)` 一致）；body 用 schema 校验；可选：trace→conversation→user 映射表。

### CF-12【低-中】LLM 调用日志与质量评审样本明文留存敏感文本（扩大 DB 泄露影响面）

- **位置**：[file:///workspace/server/app/shared/tracing_llm.py:118-119](file:///workspace/server/app/shared/tracing_llm.py#L118)；[file:///workspace/server/app/infrastructure/models/llm_call_log.py:21-22](file:///workspace/server/app/infrastructure/models/llm_call_log.py#L21)；[file:///workspace/server/app/services/quality_sentinel.py:199](file:///workspace/server/app/services/quality_sentinel.py#L199)
- **攻击者画像**：CF-2/CF-9 的 DB 读取者。
- **可控输入向量**：无独立输入面（随用户会话/日记被动写入）。
- **确切代码路径**：tracing_llm.py:118-119 `prompt=prompt[:2000], response=text[:2000]` 写入 llm_call_log.py:21-22（prompt 含用户日记摘要/检索结果全文）；quality_sentinel.py:199 `reply_text` 写入 reply_quality。无对应读取接口（`load_records` 仅内部/测试），接口面无泄露，但 DB 明文留存放大 CF-2/CF-9 泄露面。
- **影响**：DB 泄露时敏感文本暴露面扩大。
- **修复建议**：评估保留期/脱敏；不存 prompt 全文（存 token 计数+摘要）。

---

## 附：审计方法说明

- **架构梳理**：定位服务边界（backend/worker/db/cache/graph）与认证、配置、出站调用主干。
- **四组攻击面审查**：认证与访问控制（auth-access）、注入（injection）、外部依赖与出站（external）、敏感数据（sensitive-data）。
- **端到端路径确认**：对候选发现逐一回读源码，仅保留可静态推演出「输入向量 → 确切代码路径 → 影响落点」的中/高严重度项；行号对应 2026-11-09 工作区现状；openai/langchain-openai 重定向行为经下载对应版本 wheel 源码实测确认（openai 1.109.1 默认 `follow_redirects=True`）。
- **未执行项**：未运行代码、未修改任何文件；全部结论基于静态回读验证。

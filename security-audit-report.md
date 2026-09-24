# 安全审计报告 — Night Diary

> 审计范围：`/workspace` 仓库（FastAPI 后端 `server/` + Vue3 前端 `src/`）
> 审计方法：架构梳理 → 分组攻击面审查 → 端到端利用路径追踪 → 证据链验证
> 审计日期：2026-09-24

---

## 结论摘要

发现 **2 项已确认漏洞**（1 项高危、1 项中危），均具备从攻击者可控输入到影响的完整端到端利用路径。另记录若干低风险观察项（未达到中等严重度阈值，不作为已确认漏洞上报）。

---

## 高危

### 1. 未认证访问控制缺陷：`/api/v1/dev/*` 暴露全部用户敏感数据并允许删除与资源滥用

**位置**
- [dev.py](file:///workspace/server/app/api/v1/dev.py#L147-L215)（list/detail/delete 未加任何认证依赖）
- [router.py](file:///workspace/server/app/api/v1/router.py#L39)（`dev.router` 无条件挂载，生产环境同样生效）
- [conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L754)（trace span 记录 `input_snapshot={"raw_text": content}`，即用户原文）
- [trace_persistence.py](file:///workspace/server/app/shared/trace_persistence.py#L20-L43)（完整 trace JSON 落库）
- [conversation.py](file:///workspace/server/app/api/v1/conversation.py#L159)（每条流式消息自动生成 `trace_id`）

**攻击者画像**：外部未认证用户（无需任何账号，网络可达即可）。

**可控输入向量**：
- HTTP 直接访问 `/api/v1/dev/traces`、`/api/v1/dev/traces/{trace_id}`、`DELETE /api/v1/dev/traces/{trace_id}`、`/api/v1/dev/traces/{trace_id}/stream`、`POST /api/v1/dev/quality-scan`、`/api/v1/dev/mcp/calls`

**确切代码路径**：
1. 任意用户在对话时，后端在 [conversation.py](file:///workspace/server/app/api/v1/conversation.py#L159) 生成 `trace_id`（或从 `X-Trace-Id` 头读取），调用 `generate_reply` 时在 [conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L738-L740) 创建 `PipelineTrace`。
2. 各处理阶段通过 `trace_span(..., input_snapshot={"raw_text": content})`（危机检测、预处理、意图分类、槽位抽取、Agentic Loop 等，见 [conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L473-L1017)）把**用户原文快照**写入 span。
3. [trace_persistence.py](file:///workspace/server/app/shared/trace_persistence.py#L36) 将完整 `trace.to_dict()`（含所有 span 的 input/output 快照、`user_id`）持久化为 `trace_json`。
4. 攻击者调用未认证的 `GET /api/v1/dev/traces` 枚举全部 trace（含所有用户 `user_id`），再调用 `GET /api/v1/dev/traces/{trace_id}` 直接读取任意用户的完整原始日记/对话内容；`DELETE` 可删除任意 trace；`/traces/{id}/stream` 可订阅任意用户的实时流；`POST /quality-scan` 可反复触发对真实用户回复的 LLM 评测调用。

**影响**：
- **数据泄露**：全部用户的私密日记、对话、心理数据（本应用为心理健康场景，属高度敏感 PII）可被未认证读取。
- **数据完整性破坏**：任意删除 pipeline trace（观测数据）。
- **资源耗尽/成本滥用**：反复触发 `quality-scan` 消耗 LLM 额度与算力。

**修复建议**：
1. 为 `/api/v1/dev/*` 全部路由加 `CurrentUserDep` 认证，并按 `user_id` 做数据隔离（当前查询完全没有用户过滤）。
2. 增加环境开关：`app_env == "production"` 时禁止挂载 dev 路由（或在 `main.py` 中条件注册）。
3. `quality-scan` 增加频率限制与管理员权限。
4. 对 trace 存储中的原文内容做脱敏/匿名化，或默认关闭 trace 落库。

---

## 中危

### 2. 未认证 SSRF：`POST /api/v1/models/test-connection`

**位置**
- [models.py](file:///workspace/server/app/api/v1/models.py#L42-L51)（该路由未声明 `CurrentUserDep`，而同级其他路由均受保护）
- [model_service.py](file:///workspace/server/app/services/model_service.py#L105-L151)（`validate_model_connection` 仅校验协议前缀，随即发起服务端请求）

**攻击者画像**：外部未认证用户。

**可控输入向量**：`body.base_url`（任意 URL）、`body.api_key`、`body.model_name`。

**确切代码路径**：
1. 攻击者 `POST /api/v1/models/test-connection`，传入 `base_url` 指向内网地址（如 `http://169.254.169.254`、`http://192.168.x.x`、`http://127.0.0.1:<port>`）。
2. [model_service.py](file:///workspace/server/app/services/model_service.py#L111) 仅检查 `base_url.startswith(("http://", "https://"))`，不做域名白名单或内网地址过滤。
3. `_external_http_client()`（[L76-L78](file:///workspace/server/app/services/model_service.py#L76-L78)）以 `trust_env=False` 发起 `GET {base}/models`、`GET {base}/v1/models`、`POST {base}/v1/chat/completions`。
4. 响应以状态码/错误消息形式回显给攻击者（[L121-L147](file:///workspace/server/app/services/model_service.py#L121-L147)）：200/404/400 → "连接成功"；其他状态码 → "API 返回状态码 N（{url}）"；连接失败 → "无法连接到 {base_url}"。

**影响**：
- **SSRF / 内网探测**：攻击者可让服务端向任意内网主机/端口发起请求，通过状态码差异与错误消息形成扫描 oracle，确认内网服务存活、端口开放、云元数据端点（169.254.169.254 等）可达性。
- 可被用于滥用服务端网络能力（对第三方/内网资源造成请求洪泛）。

**修复建议**：
1. 为该路由增加 `CurrentUserDep` 认证。
2. 对 `base_url` 做 SSRF 防护：解析 host 后拒绝私有/保留地址段（127.0.0.0/8、10/8、172.16/12、192.168/16、169.254/16、0.0.0.0、[::1] 等），并仅允许 HTTPS。
3. 增加目标域名白名单（仅允许已知 LLM 提供商域名）。

---

## 低风险观察项（未达中等及以上阈值）

以下问题已记录但**不作为已确认漏洞上报**（缺少端到端可利用性证明或影响有限）：

| 观察项 | 位置 | 说明 |
|---|---|---|
| LLM 调用明文 PII 落库 | [tracing_llm.py](file:///workspace/server/app/shared/tracing_llm.py#L104-L124) | `prompt[:2000]`/`response[:2000]` 持久化至 `llm_call_logs`，含用户日记原文；当前无 API 直接暴露该表，但建议脱敏或按需关闭。 |
| JWT 黑名单内存回退 | [jwt_blacklist.py](file:///workspace/server/app/infrastructure/jwt_blacklist.py#L19-L28) | Redis 不可用时回退内存缓存，多 worker 部署下 logout 吊销可能失效（单进程部署无影响）。 |
| 弱密码策略 | [auth.py](file:///workspace/server/app/api/v1/auth.py#L28) | 密码最短 6 位；bcrypt 缓解在线暴力破解，建议提高至 8+。 |
| 未认证模型下载触发 | [model_download.py](file:///workspace/server/app/api/v1/model_download.py#L14-L42) | `start` 有幂等保护（线程存活/已就绪时返回 false），仅可提前触发下载与查看进度，影响有限。 |

---

## 审计结论

**审计完成——发现 2 项已确认漏洞（1 高危 / 1 中危），均已在上文按严重度分组给出位置、影响与修复建议。**

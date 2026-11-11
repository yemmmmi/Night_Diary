# Night Diary 安全审计报告

审计日期：2026-11-11 ｜ 范围：/workspace（FastAPI 后端 `server/` + Vue 前端 `src/`）
门槛：仅报告中等（CVSS 4.0+）及以上、具备可论证端到端利用路径的**已确认**漏洞；理论性/推测性风险不计入。

---

## 高危（High）

### H-1 未认证访问 `/api/v1/dev/*` 调试端点 → 跨用户个人数据（日记/会话内容）泄露

**位置**
- 路由定义：[dev.py](file:///workspace/server/app/api/v1/dev.py)（整个 router 无任何认证依赖，仅 `DbDep`/`ContainerDep`）
- 路由注册：[router.py](file:///workspace/server/app/api/v1/router.py#L43)（`include_router(dev.router)`，生产构建无条件挂载）

**攻击者画像**：匿名外部用户（只要网络可达后端；经 nginx `/api/` 反代同样可达）。

**可控输入向量**：无特殊输入——直接构造 HTTP 请求即可（trace_id 可枚举/遍历列表）。

**代码路径（输入 → 漏洞）**
1. 追踪数据**始终**写入：`conversation_ai_service.py` 每次会话回复无条件 `PipelineTrace(trace_id, scenario="chat_reply", user_id=...)` 并 `set_trace`（[conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L836-L837)）；多个 span 以 `input_snapshot={"raw_text": content}` 捕获用户完整消息（经 `truncate_snapshot` 截断至 500 字符），见 [conversation_ai_service.py](file:///workspace/server/app/services/conversation_ai_service.py#L565)。日记摘要场景同理（[analysis_service.py](file:///workspace/server/app/services/analysis_service.py#L502-L503)）。
2. 未认证读取：`GET /api/v1/dev/traces` 返回**所有用户**的 trace 摘要（含 `user_id`、场景、耗时），见 [dev.py](file:///workspace/server/app/api/v1/dev.py#L147-L178)；`GET /api/v1/dev/traces/{trace_id}` 返回完整 `trace_json`（含上述含用户内容的 spans），见 [dev.py](file:///workspace/server/app/api/v1/dev.py#L184-L197)。

**影响**
- 任意用户（含匿名）可枚举全部用户 ID 并读取每位用户的日记/会话内容片段（每 span 最长 500 字符、多 span/多 trace，可持续拖取），构成敏感个人数据（PII）批量泄露。
- 附带面：`GET /dev/stats/performance` 跨用户聚合 LLM 成本数据；`GET /dev/mcp/calls?user=X` 可按用户过滤读取 MCP 调用日志；`POST /dev/quality-scan` 匿名触发 LLM 采样判定（资源滥用）；`DELETE /dev/traces/{id}` 匿名删除任意 trace（完整性）。

**修复建议**
- 为 `/dev/*` 全部端点强制 `CurrentUserDep`，并让 `traces`/`mcp/calls` 查询按当前 `user_id` 过滤（服务端强隔离，而非仅前端隐藏）。
- 更稳妥：生产环境（`app_env == "production"`）完全不注册 `dev.router`，或拆到独立的调试路由前缀 + 管理令牌。
- `quality-scan` 增加鉴权与频率限制。

---

## 中危（Medium）

### M-1 用户可控 LLM `base_url` 触发对内网/容器网段 SSRF 探测

**位置**
- 校验链：[url_guard.py](file:///workspace/server/app/shared/url_guard.py#L105-L136) + [model_service.py](file:///workspace/server/app/services/model_service.py#L161-L206)（`validate_model_connection` 先 `validate_outbound_url(base_url, allow_private=...)` 再发起探测）
- 配置默认：[config.py](file:///workspace/server/app/config.py#L155) `allow_private_model_hosts` 默认 `True`；接入点 [models.py](file:///workspace/server/app/api/v1/models.py#L42-L75)（`/models/test-connection`、创建模型，均需认证）

**攻击者画像**：已认证用户（多用户部署中任意注册用户）。

**可控输入向量**：模型配置中的 `base_url` 字段（攻击者完全可控字符串）。

**代码路径（输入 → 漏洞）**
1. 攻击者提交 `base_url = http://172.20.0.X:8080` 或 `http://redis:6379` 等内网地址。
2. `validate_outbound_url` 仅永久阻断云元数据/链路本地网段（`169.254.0.0/16`、阿里 `100.100.100.200` 等）；`allow_private=True` 时 `127.0.0.0/8`、`10/8`、`172.16/12`、`192.168/16` 均放行（[url_guard.py](file:///workspace/server/app/shared/url_guard.py#L47-L55)）。
3. 后端以 `httpx`（`follow_redirects=False`、10s 超时，[model_service.py](file:///workspace/server/app/services/model_service.py#L128-L134)）对目标发起 `GET /models` 与 `POST /v1/chat/completions`——内网主机/端口可达性被探测，且向内部 HTTP 服务注入带结构化 JSON 体的 POST。

**影响**
- 容器网络内（MySQL/Redis/Neo4j/ChromaDB 等）主机与端口扫描；可向内网 HTTP 服务注入请求（SSRF POST）。
- 缓解项：云元数据被阻断；`follow_redirects=False` 阻断重定向绕过；对非 OpenAI 协议服务响应体不回显。故实际危害以内网探测/请求注入为主，不构成元数据窃取。

**修复建议**
- 默认 `allow_private_model_hosts=False`；确需本地 LLM（Ollama/LM Studio）时，改为按用户显式开启，并对回环地址单独白名单（`127.0.0.0/8` 允许，其余 RFC1918 需显式配置）。
- 请求发起前与解析后二次校验（缓解 DNS rebinding），并限定探测只发往 `/v1/models`、`/v1/chat/completions` 白名单路径。

---

## 低危（Low，供参考，不计入确认清单）

- **L-1** 未认证 `POST /api/v1/models/download/start`（[model_download.py](file:///workspace/server/app/api/v1/model_download.py#L34-L41)）：匿名可触发 HuggingFace 模型下载（仅首次未就绪窗口内有效），资源/带宽消耗型 DoS；`repo_id` 固定且主机白名单（`huggingface.co/hf.co/hf-mirror.com`），无 SSRF。建议加认证或仅内网可达。

---

## 已验证无问题的面（结论）

| 攻击面 | 结论 |
|---|---|
| 认证核心 | bcrypt 口令哈希；JWT `HS256` 算法白名单 + `exp/iat/jti`；登出黑名单（`jwt:blacklist:<jti>`）；`get_current_user` 的 `user_id` 全部来自令牌并校验 `is_active`（[deps.py](file:///workspace/server/app/api/deps.py#L39-L60)） |
| 资源归属校验 | diary/card/plan/memory/conversation/weekly/tags/stats/export/uploads 等路由全部以 `str(user.id)`（令牌派生）做查询/写入过滤，未见请求体 `user_id` 被信任 |
| SQL 注入 | ORM 参数化查询；迁移 DDL 标识符来自内部逻辑并经 `q()` 转义，无攻击者可控标识符 |
| 命令注入 | 子进程仅 `git rev-parse`（固定参数、无 `shell=True`） |
| 路径穿越 | 上传文件名由服务端生成 UUID；下载器用 `safe_join` 限根目录；无用户可控路径拼接 |
| MCP | API 无注册任意 `command/args/env` 的入口；stdio 规格来自配置层且 env 白名单化；自定义技能仅提示词模板，无代码执行 |
| 密钥/凭证 | 代码树与提交历史未发现硬编码真实密钥；存储的 LLM key 经 Fernet 加密（`encrypt_api_key`）；生产环境缺 `MODEL_KEY_SECRET`/`JWT_SECRET_KEY` 时 fail-fast，无弱默认回退 |
| 日志/PII | 错误处理器不回显堆栈细节；LLM 调用日志在认证的 `/api/v1/stats` 下按用户过滤 |

---

## 结论

已确认 **2 个**达到门槛的漏洞：**H-1（高危）未认证跨用户个人数据泄露**、**M-1（中危）用户可控 base_url 内网 SSRF 探测**。其余面经端到端代码路径验证未发现中等及以上已确认问题。

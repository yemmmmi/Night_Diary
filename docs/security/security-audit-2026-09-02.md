# Night Diary 安全审计报告

- **审计日期**: 2026-09-02
- **审计范围**: `server/`（FastAPI + SQLAlchemy 后端）与 `docker-compose.yml`/`Dockerfile` 部署面
- **审计方法**: 架构梳理 → 按攻击面分组（认证与访问控制 / 注入向量 / 外部交互 / 敏感数据处理）→ 从攻击者可控输入追踪到影响结果，仅收录具备端到端利用路径的确认漏洞

## 审计结论

**确认存在 2 个 Critical、1 个 High、1 个 Medium 已确认漏洞**，均为可论证的无认证 / 弱配置利用路径。

---

## Critical

### C1. 未认证 `/api/v1/dev/*` 端点跨租户泄露全部用户日记/对话 PII

- **攻击者画像**: 未认证外部攻击者（生产环境 `docker-compose` 将 `8000:8000` 对外映射，`server/Dockerfile` 以 `uvicorn --host 0.0.0.0` 运行，端点外网可达）。
- **可控输入向量**: `GET /api/v1/dev/traces`、`GET /api/v1/dev/traces/{trace_id}`、`GET /api/v1/dev/traces/{trace_id}/stream`、`DELETE /api/v1/dev/traces/{trace_id}` 均无需任何凭据。
- **确切代码路径**:
  - 路由无认证依赖：[dev.py](file:///workspace/server/app/api/v1/dev.py#L145-L195) `list_traces` / `get_trace_detail` / `stream_trace` / `delete_trace` 仅带 `db: DbDep`，无 `CurrentUserDep`（文件头注释亦自述 "do not require authentication"）。
  - [dev.py:157](file:///workspace/server/app/api/v1/dev.py#L157) `db.query(PipelineTraceRow)` 全表查询**无 user 过滤**；[dev.py:186-195](file:///workspace/server/app/api/v1/dev.py#L186-L195) 直接返回完整 `trace_json`。
  - PII 捕获与落库：trace span 在正常回复路径必然创建并持久化。
    [conversation_ai_service.py:397](file:///workspace/server/app/services/conversation_ai_service.py#L397) `trace_span(..., input_snapshot={"raw_text": content})` 将用户完整消息写入 span；[pipeline_trace.py:28-67](file:///workspace/server/app/shared/pipeline_trace.py#L28-L67) `truncate_snapshot` 仅按 500 字符截断、**不脱敏**；[trace_persistence.py:36](file:///workspace/server/app/shared/trace_persistence.py#L36) 将含 `user_id` 与 span 快照的 dict 序列化为 `pipeline_traces.trace_json`。
- **影响**: 未认证者可批量读取任意租户的真实日记、对话、（危机检测）情感/PII 内容及 `user_id`，属严重隐私泄露；`DELETE /traces/{id}` 可破坏数据；同一无认证 `/dev` router 还泄露基础设施状态（`middleware-status`）并可无认证触发 LLM 质量扫描造成成本滥用。
- **修复建议**:
  1. 为 `dev` router 全部路由补 `CurrentUserDep`，并在 `list_traces` / `get_trace_detail` / `delete_trace` 追加 `.filter(PipelineTraceRow.user_id == user_id)`。
  2. 生产环境（`app_env == "production"`）默认不挂载 `dev` router。
  3. 对 span 快照做字段级 PII 脱敏（而非仅长度截断）。

### C2. 编排文件内置已知弱默认密钥，可伪造任意用户 JWT（全量认证绕过）

- **攻击者画像**: 未认证外部攻击者；`docker-compose.yml` 中默认值是公开的已知字符串。
- **可控输入向量**: 攻击者自签 `JWT`，`{"sub": "<victim_user_id>", "iat": …, "exp": …}`。
- **确切代码路径**:
  - [docker-compose.yml:59](file:///workspace/docker-compose.yml#L59) `JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-me-in-production-min-32-chars}`、[:60](file:///workspace/docker-compose.yml#L60) `MODEL_KEY_SECRET=${MODEL_KEY_SECRET:-change-me-model-key-min-16c}`（worker 同步）。未显式注入时回退到硬编码已知默认值。
  - [auth.py:35-45](file:///workspace/server/app/infrastructure/auth.py#L35-L45) `resolve_jwt_secret` 在 `jwt_secret_key` 非空即返回 → 直接命中已知默认串，绕过 [security.py:48-52](file:///workspace/server/app/infrastructure/security.py#L48-L52) 的“生产 fail-fast”校验；[auth.py:48-65](file:///workspace/server/app/infrastructure/auth.py#L48-L65) `jwt.encode(..., algorithm="HS256")`。
  - [deps.py:39-60](file:///workspace/server/app/api/deps.py#L39-L60) 用同一 secret 解码校验 `sub` → 任意 `user_id` 均可被冒充。
- **影响**: 用默认配置部署即等同于对认证体系全失守：攻击者可用已知 HS256 密钥伪造任意用户的有效令牌（有效期内，默认 `JWT_EXPIRE_MINUTES=10080`），读取/修改所有受 `CurrentUserDep` 保护的数据 —— 账户接管 / 全租户数据泄露。`MODEL_KEY_SECRET` 同源弱默认使 Fernet 加密的模型 Key 可被解密。
- **修复建议**:
  1. 从 `docker-compose.yml` 移除所有占位默认密钥，缺失即拒绝启动（而非回退）。
  2. 在 `resolve_jwt_secret` / `_resolve_secret` 增加“已知占位串 + min_length”校验，命中即 fail-fast。
  3. 生产环境强制注入强随机密钥，禁止固化在仓库。

---

## High

### H1. 未认证 `POST /api/v1/models/test-connection` 盲 SSRF / 内网探测

- **攻击者画像**: 未认证外部攻击者。
- **可控输入向量**: 请求体 `{base_url, api_key, model_name}` 完全可控。
- **确切代码路径**: [models.py:42-51](file:///workspace/server/app/api/v1/models.py#L42-L51) `test_model_connection` 无认证依赖；[model_service.py:105-151](file:///workspace/server/app/services/model_service.py#L105-L151) 仅校验 `base_url` 以 `http://`/`https://` 开头，即由服务器向攻击者提供的地址发起 `GET /models`、`GET /v1/models`、`POST /v1/chat/completions`（`Authorization: Bearer {api_key}`，`_external_http_client` 用 `httpx` 直连、`trust_env=False`），并对 127.0.0.0/8、RFC1918、169.254.0.0/16 等内网段**无任何拦截**。
- **影响**: 服务器对外发起任意出站请求，通过返回状态码差（200/404/401/405/连接失败/超时）形成**可达性 oracle**，可对云元数据端点与内网服务做盲探测与端口指纹（CWE-918 SSRF）。
- **修复建议**:
  1. 为该路由补 `CurrentUserDep`（与 `/{id}/test-connection` 保持一致）。
  2. 解析 `base_url` host 并拒绝私网/回环/链路本地网段（DNS 解析后校验），收紧为仅 `https://`。
  3. 不向调用方回显内部可达性/状态码诊断细节。

---

## Medium

### M1. 未认证 `POST /api/v1/models/download/start`（及 `/status`）资源滥用 / 出网下载

- **攻击者画像**: 未认证外部攻击者。
- **可控输入向量**: 直接调用 `POST /api/v1/models/download/start`。
- **确切代码路径**: [model_download.py:14-42](file:///workspace/server/app/api/v1/model_download.py#L14-L42) `download_status` / `start_download` 均无认证；[model_downloader.py:140-201](file:///workspace/server/app/services/model_downloader.py#L140-L201) `start()` 触发出站 `huggingface_hub.snapshot_download` 拉取 embedding/reranker 大模型。
- **影响**: 未认证者可反复触发生产服务器拉取大型模型 → 带宽/磁盘耗尽（DoS）与内网出网流量；`GET /status` 泄露下载内部进度。
- **修复建议**: 为 `start`/`status` 加认证；下载加并发锁与频控。

---

## 已排查但未达上报门槛（未确认 ≥ 中等，仅供防御性改进参考）

- **注入向量**（原始 SQL / 命令执行 / 路径穿越 / SSTI）：全部为参数化 SQLAlchemy 列对象过滤；唯一 `subprocess`（`main.py::_app_build_version`）为静态命令、无用户输入；模型 repo_id 为硬编码常量非用户输入 —— **无 ≥ Medium 确认漏洞**。
- **多租户隔离（IDOR）**：diary / card / memory / episodic / model / plan（读写）服务层均按 `user_id` 过滤 —— 达标。`plan_service.create_task`（[plan_service.py:118-146](file:///workspace/server/app/services/plan_service.py#L118-L146)）在传入 `plan_id` 时不校验其归属，可将任务挂到他人计划下；但 `plan_id` 为不可枚举的 32 位 hex UUID、且仅写入攻击者自己的任务行、不读取他人数据 → **Low（建议补归属校验，未列入在线漏洞）**。
- **`llm_call_logs` 明文持久化完整 prompt/response（前 2000 字符）**（[tracing_llm.py:118-119](file:///workspace/server/app/shared/tracing_llm.py#L118-L119)）：当前无 API 端点直接回吐该表，无端到端读取路径 → 未达确认门槛；建议对 prompt/response 加密或仅存摘要（与 C1 修复一并处理）。
- **CORS**：`main.py` 使用 `allow_origin_regex`（默认仅放行 localhost/127.0.0.1），配置合理 —— 无问题。

## 修复优先级

1. **C2**（改默认密钥 + 生产 fail-fast）与 **C1**（`/dev` 鉴权 + user 过滤 + 生产禁用）—— 二者组合可导致生产全量敏感数据泄露，应最先修复。
2. **H1**（test-connection 鉴权 + 内网网段拦截）与 **M1**（download 鉴权）。
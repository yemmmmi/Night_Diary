# 安全审计 Spec — 夜记 (Night Diary) v2

## Why
对夜记本地桌面应用进行周期性安全审计，识别中等严重度及以上且具备可论证端到端利用路径的已确认漏洞。

## What Changes
- 审计代码库架构，识别信任边界与攻击面
- 按认证、注入、外部交互、敏感数据处理四个维度系统检查
- 对每个潜在发现追踪完整代码路径，仅保留可证明可利用性的发现
- 输出结构化报告，按严重度分组，包含位置、影响和修复建议

## Impact
- Affected specs: N/A（审计类 spec）
- Affected code: 全代码库范围审计

---

## 审计范围与威胁模型

### 应用概况
- **类型**: 本地桌面应用（Tauri + Python FastAPI 侧车进程）
- **后端绑定**: 仅 `127.0.0.1`（不暴露到网络）
- **认证**: 无（单用户本地应用，无 JWT、无 Session）
- **数据库**: SQLite（`{data_dir}/night_diary.db`）
- **向量存储**: ChromaDB（本地持久化）
- **LLM 集成**: 用户自配置 API Key，Fernet 加密存储
- **外部依赖**: HuggingFace Hub 模型下载、高德天气 API、用户配置的 LLM API

### 信任边界
1. **Tauri Shell → Python Sidecar**: 同一台机器，loopback HTTP，无认证
2. **Python Sidecar → SQLite**: 本地文件系统，进程内访问
3. **Python Sidecar → 外部 LLM API**: 出站 HTTPS，使用用户提供的 API Key
4. **Python Sidecar → HuggingFace Hub**: 出站 HTTPS，下载模型权重
5. **Python Sidecar → 高德天气 API**: 出站 HTTPS

### 攻击者画像
- **A1**: 同一台机器上的恶意进程（具备文件系统读取权限但无 root 权限）
- **A2**: 通过社工/钓鱼获取用户 `.env` 文件或数据目录的远程攻击者
- **A3**: 获得物理访问的攻击者

---

## 审计结果

### 发现 1：MEDIUM — 硬编码默认加密密钥导致 API Key 可被解密

**严重度**: Medium  
**位置**: [server/app/infrastructure/security.py](file:///workspace/server/app/infrastructure/security.py#L20-L27)

**攻击者画像**: A1（同机恶意进程）、A2（获取数据目录的远程攻击者）

**可控输入向量**: 攻击者读取 `{data_dir}/night_diary.db` 中 `model_providers` 表的 `api_key_encrypted` 字段。

**完整代码路径**:
1. `_resolve_secret()` ([security.py:20-27](file:///workspace/server/app/infrastructure/security.py#L20-L27)) 按以下优先级查找加密密钥：
   - `settings.model_key_secret`（环境变量）
   - `{data_dir}/secrets.key` 文件
   - **硬编码回退值** `"night-diary-local-dev-key"`（第 26 行）
2. 当用户未设置 `model_key_secret` 且 `secrets.key` 文件不存在时，密钥降级为已知常量。
3. `_derive_fernet_key()` ([security.py:14-17](file:///workspace/server/app/infrastructure/security.py#L14-L17)) 对已知常量做 SHA256 + base64 编码，结果可被攻击者离线计算。
4. 攻击者使用派生出的 Fernet 密钥调用 `decrypt_api_key()` 解密数据库中的 `api_key_encrypted` 字段。

**影响**: 存储在数据库中的第三方 LLM API Key（如 DeepSeek、OpenAI）被完全解密。攻击者可使用这些 API Key 进行未授权调用、产生费用、或通过 LLM 提供商的数据查询功能获取用户历史请求信息。

**建议修复**:
1. **移除硬编码回退值** — 如果用户未设置 `model_key_secret` 且无 `secrets.key`，在启动时自动生成一个随机密钥并写入 `secrets.key` 文件。
2. 作为临时缓解措施，在启动日志中警告用户未设置 API Key 加密密钥。

---

### 发现 2：MEDIUM — 天气 API Key 在 SQLite 中明文存储

**严重度**: Medium  
**位置**: [server/app/services/ai/tool_factory.py](file:///workspace/server/app/services/ai/tool_factory.py#L96-L105) 和 [server/app/infrastructure/models/app_config.py](file:///workspace/server/app/infrastructure/models/app_config.py)

**攻击者画像**: A1（同机恶意进程）、A2（获取数据目录的远程攻击者）

**可控输入向量**: 攻击者直接读取 `{data_dir}/night_diary.db` 中 `app_config` 表的 `value` 字段。

**完整代码路径**:
1. 用户在前端设置天气 API Key → 存储在 `app_config` 表中（`key='weather_api_key'`），明文保存。
2. `create_weather_tool()` ([tool_factory.py:96-105](file:///workspace/server/app/services/ai/tool_factory.py#L96-L105)) 通过 `_get_config_value(db, "weather_api_key")` 读取明文值。
3. 该值通过 `_fetch_weather_from_api()` ([tool_factory.py:61-93](file:///workspace/server/app/services/ai/tool_factory.py#L61-L93)) 发送到高德天气 API，作为 URL 参数 `key=`。

**影响**: 攻击者获取高德地图 API Key，可用于：
- 未授权调用高德 API（产生费用，高德 API 按 QPS 和调用量计费）
- 通过高德 API 查询地理/天气数据（隐私泄露）

**建议修复**: 将 `weather_api_key` 和 `user_address` 使用与 LLM API Key 相同的 Fernet 加密机制存储。

---

### 发现 3：LOW — 应用关闭端点无防护

**严重度**: Low  
**位置**: [server/app/main.py](file:///workspace/server/app/main.py#L138-L143)

**攻击者画像**: A1（同机恶意进程）

**可控输入向量**: 向 `POST /shutdown` 发送 HTTP 请求（无需任何认证）。

**完整代码路径**:
1. 路由 `POST /shutdown` ([main.py:138-143](file:///workspace/server/app/main.py#L138-L143)) 直接调用 `os._exit(0)`，无任何认证或来源校验。
2. 虽然 CORS 限制为 `localhost` / `127.0.0.1` / `tauri.localhost`，但同一台机器上的任何进程（包括浏览器中的恶意网页、其他本地应用）都可以发送此请求。

**影响**: 本地拒绝服务（DoS）— 攻击者可通过反复发送 `/shutdown` 请求阻止用户正常使用应用。不造成数据泄露或权限提升。

**建议修复**: 
1. 验证请求来源（如检查 `Origin`/`Referer` header 是否匹配 Tauri 自定义协议）
2. 添加 rate limiting（限制同一来源的关闭请求频率）
3. 作为纵深防御，可要求 Tauri 端传递一个随机 token 进行验证

---

### 发现 4：LOW — LLM 调用日志明文存储提示词与响应内容

**严重度**: Low  
**位置**: [server/app/shared/tracing_llm.py](file:///workspace/server/app/shared/tracing_llm.py#L64-L82) 和 [server/app/infrastructure/llm_call_tracer.py](file:///workspace/server/app/infrastructure/llm_call_tracer.py#L19-L38)

**攻击者画像**: A1（同机恶意进程）、A2（获取数据目录的远程攻击者）

**可控输入向量**: 攻击者读取 `{data_dir}/night_diary.db` 中 `llm_call_logs` 表的 `prompt` 和 `response` 字段。

**完整代码路径**:
1. `TracingLLMClient._record()` ([tracing_llm.py:64-82](file:///workspace/server/app/shared/tracing_llm.py#L64-L82)) 截取提示词和响应的前 2000 字符。
2. `SqliteLLMCallTracer.record()` ([llm_call_tracer.py:19-38](file:///workspace/server/app/infrastructure/llm_call_tracer.py#L19-L38)) 将截取内容原样写入 `llm_call_logs` 表。
3. 提示词中包含用户日记全文，响应中包含 AI 分析结果。这些内容均以明文形式存储在 SQLite 中。

**影响**: 隐私泄露 — 攻击者获取数据库后可读取用户的所有日记内容和 AI 分析结果。这是本地应用的预期风险范围（SQLite 本身无加密），但日志表增加了数据暴露面。

**建议修复**: 
1. 在存储前对 `prompt` 和 `response` 字段使用数据库级加密（如 SQLCipher）或字段级加密
2. 允许用户在设置中关闭 LLM 调用日志记录
3. 缩短日志保留时间，添加自动清理机制

---

## 未确认的潜在风险点（已排除）

以下区域经过审查，未发现可论证的利用路径：

- **SQL 注入**: 所有数据库操作均使用 SQLAlchemy ORM 参数化查询。`database.py` 中的 `ALTER TABLE` 使用硬编码字典值，不接受用户输入。
- **Shell 命令注入**: 唯一的 `subprocess` 调用 ([main.py:28-38](file:///workspace/server/app/main.py#L28-L38)) 使用参数列表形式（`shell=False`），且输入为常量 `["git", "rev-parse", "--short", "HEAD"]`。
- **SSRF via 模型连接测试**: `validate_model_connection()` 的 `_external_http_client()` 使用 `trust_env=False`，阻止了通过环境变量代理的 SSRF。用户自行配置的 `base_url` 属于用户主动行为，且仅用于用户自己的 LLM 服务。
- **越权访问**: 应用为单用户模型，无用户间隔离需求。所有 API 端点均直接访问共享数据。
- **XSS/CSRF**: 后端为纯 REST API（返回 JSON），不渲染 HTML。前端为 Tauri WebView，使用 Vue 组件，Vue 默认转义模板内容。
- **依赖供应链**: 未在本次审计范围内。
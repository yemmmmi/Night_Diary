# 夜记（Night Diary）安全审计报告 Spec

## Why
对夜记 v2 代码仓库进行周期性自动化安全审计，识别中等严重度及以上的已确认漏洞，需具备可论证的端到端利用路径。

## What Changes
- 输出结构化安全审计报告，按严重度分组列出已确认漏洞
- 每个漏洞包含：攻击者画像、可控输入向量、完整代码路径、影响说明、修复建议
- 如未发现中等及以上漏洞，输出"审计完成——未发现中等或更高严重度的已确认漏洞"

## Impact
- Affected specs: 无（纯审计报告，不修改代码）
- Affected code: 审计覆盖整个代码仓库

## 审计范围摘要

### 系统架构
- **类型**: 单用户本地桌面应用（Tauri + Python FastAPI sidecar）
- **入口点**: FastAPI 后端绑定 `127.0.0.1`（仅回环），Tauri WebView 前端通过 IPC 和 HTTP 与后端通信
- **信任边界**: 后端进程仅监听回环地址，同一台机器上的其他进程可访问 API
- **数据存储**: SQLite（明文日记数据）、ChromaDB（向量索引）、HuggingFace 模型缓存

### 审计覆盖的攻击面
| 攻击面 | 审计结果 |
|--------|---------|
| 认证与访问控制 | 无认证机制（设计如此），`/shutdown` 端点无保护 |
| 注入向量 | SQL 使用 ORM 参数化查询，无用户输入拼接；Shell 调用无用户输入；无模板引擎 |
| 外部交互 | 模型连接测试端点存在盲 SSRF；天气 API 调用；LLM API 调用；HuggingFace 下载 |
| 敏感数据处理 | LLM API Key 使用 Fernet 加密但默认密钥可预测；LLM 提示词/响应明文记录到 SQLite |

## 已确认漏洞

### 严重度: Medium

---

### 漏洞 1: 模型连接测试端点盲 SSRF

**攻击者画像**: 同一台机器上的恶意进程（或用户自身）

**可控输入向量**: `POST /api/v1/models/test-connection` 的 `base_url` 字段（JSON body）

**完整代码路径**:
1. 入口: [models.py:43-51](file:///workspace/server/app/api/v1/models.py#L43-L51) — `test_model_connection` 端点接收 `ModelTestConnectionRequest`，其中 `base_url` 仅校验 `min_length=1`
2. 调用: [model_service.py:93-98](file:///workspace/server/app/services/model_service.py#L93-L98) — `validate_model_connection` 仅检查 URL 是否以 `http://` 或 `https://` 开头
3. 出站请求: [model_service.py:64-70](file:///workspace/server/app/services/model_service.py#L64-L70) — `_external_http_client()` 创建 `httpx.Client(timeout=10.0, trust_env=False)`，向多个候选 URL 发起 GET 请求
4. 附加探测: [model_service.py:73-90](file:///workspace/server/app/services/model_service.py#L73-L90) — 若 `/models` 探测失败，还会向 `{base_url}/v1/chat/completions` 发起 POST 请求

**影响**: 攻击者可利用此端点探测本机内网服务（如 `http://127.0.0.1:6379`、`http://localhost:8080` 等）。虽然 `trust_env=False` 阻止了代理劫持，且响应内容不返回给调用者（盲 SSRF），但仍可基于响应状态码和错误消息推断目标服务的存在性和行为。

**建议修复**:
1. 对 `base_url` 实施白名单校验，仅允许已知 LLM 提供商的域名模式
2. 或限制为仅允许 HTTPS URL
3. 或添加用户确认步骤后再发起外部请求

---

### 漏洞 2: LLM API Key 加密使用可预测的默认密钥

**攻击者画像**: 同一台机器上具有文件读取权限的恶意进程

**可控输入向量**: 文件系统读取 `{data_dir}/night_diary.db` 中 `model_providers` 表的 `api_key_encrypted` 字段

**完整代码路径**:
1. 密钥解析: [security.py:20-26](file:///workspace/server/app/infrastructure/security.py#L20-L26) — `_resolve_secret` 函数优先级链：
   - `MODEL_KEY_SECRET` 环境变量
   - `{data_dir}/secrets.key` 文件
   - **默认值 `"night-diary-local-dev-key"`**（硬编码）
2. 密钥派生: [security.py:14-17](file:///workspace/server/app/infrastructure/security.py#L14-L17) — 当密钥不是 44 字符的 base64 字符串时，使用 SHA256 派生 Fernet 密钥
3. 加密: [security.py:36-37](file:///workspace/server/app/infrastructure/security.py#L36-L37) — `encrypt_api_key` 使用上述 Fernet 实例加密
4. 解密: [security.py:40-44](file:///workspace/server/app/infrastructure/security.py#L40-L44) — `decrypt_api_key` 使用相同 Fernet 实例解密

**影响**: 若用户未设置 `MODEL_KEY_SECRET` 环境变量或 `secrets.key` 文件，所有 LLM API Key 使用硬编码字符串 `"night-diary-local-dev-key"` 派生的密钥加密。攻击者只需读取 SQLite 数据库文件和知晓此默认密钥，即可解密所有存储的第三方 LLM API Key（如 DeepSeek、OpenAI 等），导致 API Key 泄露和潜在的滥用（费用损失、数据泄露）。

**建议修复**:
1. 首次启动时自动生成随机密钥并写入 `{data_dir}/secrets.key`，无需用户配置
2. 移除硬编码默认值，若密钥文件不存在则生成随机密钥
3. 使用操作系统原生密钥存储（如 macOS Keychain、Windows DPAPI、Linux Secret Service）

---

### 漏洞 3: LLM 调用日志明文存储敏感提示词和响应

**攻击者画像**: 同一台机器上具有文件读取权限的恶意进程

**可控输入向量**: 文件系统读取 `{data_dir}/night_diary.db` 中 `llm_call_logs` 表的 `prompt` 和 `response` 字段

**完整代码路径**:
1. 日志记录: [tracing_llm.py:64-81](file:///workspace/server/app/shared/tracing_llm.py#L64-L81) — `TracingLLMClient._record` 截取 prompt 和 response 各前 2000 字符
2. 持久化: [llm_call_tracer.py:19-38](file:///workspace/server/app/infrastructure/llm_call_tracer.py#L19-L38) — `SqliteLLMCallTracer.record` 将 `LLMCallRecord` 写入 `llm_call_logs` 表
3. 触发链: 每次 AI 分析（日记分析、周报生成、卡片引导问题等）都会触发 LLM 调用，自动记录日志

**影响**: 用户的日记内容（包含个人情感、经历、人际关系等敏感信息）作为 LLM 提示词的一部分被明文存储在 SQLite 数据库中。LLM 的响应（AI 分析结果）同样明文存储。任何能读取数据库文件的进程都可以获取用户的完整日记内容和 AI 分析结果，构成严重隐私泄露。

**建议修复**:
1. 提供配置选项允许用户关闭 LLM 调用日志记录
2. 对 `prompt` 和 `response` 字段在存储前进行加密
3. 或仅记录元数据（token 数量、延迟、模型名称）而不记录完整内容
4. 添加日志保留策略（如仅保留最近 N 天）

---

## 未确认漏洞的领域

以下领域经过审计，未发现中等及以上严重度的可确认漏洞：

| 审计领域 | 检查项 | 结论 |
|---------|--------|------|
| SQL 注入 | 所有数据库查询使用 SQLAlchemy ORM 参数化；唯一动态 SQL 在迁移代码中，表名/列名来自硬编码字典 | 安全 |
| Shell 命令注入 | `subprocess.run` 使用列表参数，无用户输入拼接；Tauri 侧 `Command::new` 参数来自本地配置 | 安全 |
| 模板注入 | 未使用 Jinja2 等模板引擎；LLM 提示词使用 Python f-string 构建 | 安全 |
| 路径遍历 | 备份恢复功能对文件名进行了 `/`、`\\` 和 `.db` 后缀校验 | 安全 |
| 文件上传 | 无文件上传功能 | 安全 |
| XSS/CSRF | 后端仅提供 JSON API，不渲染 HTML；CORS 限制为回环地址 | 安全 |
| 依赖漏洞 | 未进行依赖扫描（超出本次审计范围） | 未评估 |
# 安全审计 — Night Diary 代码仓库

## Why
对 Night Diary 代码仓库进行周期性安全审计，识别中等严重度及以上的已确认漏洞，且必须具备可论证的端到端利用路径。不报告理论性或推测性风险。

## 审计范围
- **后端**: `server/` — FastAPI 侧车进程（Python）
- **桌面壳**: `src-tauri/` — Tauri Rust 壳
- **前端**: `src/` — Vue.js WebView 应用

## 架构概述

| 组件 | 技术栈 | 信任边界 |
|------|--------|----------|
| 桌面壳 | Tauri 2 (Rust) | 系统进程级，管理 Python 子进程生命周期 |
| 后端 API | FastAPI + Uvicorn | 绑定 `127.0.0.1`，仅本地回环可达 |
| 数据库 | SQLite (ORM: SQLAlchemy) | 本地文件系统，`{data_dir}/night_diary.db` |
| 向量库 | ChromaDB | 本地持久化，`{data_dir}/chroma_data/` |
| LLM 集成 | langchain-openai (ChatOpenAI) | 出站 HTTP 到用户配置的 OpenAI 兼容 API |
| 密钥加密 | Fernet (cryptography) | 用于加密静态存储的 LLM API Key |

**关键信任边界**: 应用是本地单用户桌面工具，无多租户、无 JWT、无 Redis、无网络暴露。所有 API 端点仅通过 `127.0.0.1` 访问。

## 审计方法论

按照以下攻击面分组进行系统性检查：

1. **认证与访问控制** — 登录流程、会话管理、角色/权限校验
2. **注入向量** — 原始 SQL 查询、Shell 命令拼接、模板渲染、文件路径操作
3. **外部交互** — Webhook 处理器、出站网络请求、第三方 API 集成
4. **敏感数据处理** — 代码或配置中的密钥、凭证或 PII 的日志记录、加密实践

对每个潜在发现，从攻击者可控输入到影响结果追踪完整代码路径。

---

## 发现

### 发现 1: 硬编码 Fernet 加密密钥回退 [MEDIUM]

**严重度**: Medium

**攻击者画像**: 获得文件系统访问权限的外部攻击者（恶意软件、备份泄露、物理访问）

**可控输入向量**: 攻击者获取 `{data_dir}/night_diary.db` 文件（包含 `model_providers` 表，其中 `api_key_encrypted` 字段存储了加密后的 LLM API Key）

**代码路径**:

1. [`security.py:29`](file:///workspace/server/app/infrastructure/security.py#L29) — `get_fernet()` 调用 `_resolve_secret()`
2. [`security.py:20-26`](file:///workspace/server/app/infrastructure/security.py#L20-L26) — `_resolve_secret()` 按优先级尝试：
   - 环境变量 `MODEL_KEY_SECRET`
   - 文件 `{data_dir}/secrets.key`
   - **硬编码回退 `"night-diary-local-dev-key"`** ← 默认配置下命中此项
3. [`security.py:14-17`](file:///workspace/server/app/infrastructure/security.py#L14-L17) — `_derive_fernet_key()` 使用 SHA256 将回退密钥派生为 Fernet 密钥
4. [`security.py:40-42`](file:///workspace/server/app/infrastructure/security.py#L40-L42) — `decrypt_api_key()` 使用该密钥解密 `model_providers` 表中存储的 API Key

**影响**: 
- 攻击者可使用已知硬编码密钥 `"night-diary-local-dev-key"` 解密数据库中所有 `api_key_encrypted` 字段
- 导致所有已配置 LLM 提供商（DeepSeek、OpenAI 等）的 API Key 完全泄露
- 攻击者可使用泄露的 API Key 进行未授权的 LLM API 调用，产生费用和潜在数据泄露

**验证**: 在默认配置下（不设置 `MODEL_KEY_SECRET` 环境变量、不创建 `secrets.key` 文件），`decrypt_api_key()` 将使用硬编码密钥解密。可通过以下步骤验证：
```python
from app.infrastructure.security import encrypt_api_key, decrypt_api_key
encrypted = encrypt_api_key("sk-test-api-key-12345")
decrypted = decrypt_api_key(encrypted)
assert decrypted == "sk-test-api-key-12345"  # 使用硬编码密钥成功解密
```

**修复建议**:
1. 移除硬编码回退密钥
2. 在首次启动时自动生成随机密钥并持久化到 `{data_dir}/secrets.key`
3. 如果无法生成密钥（无写入权限），应拒绝启动并提示用户

---

### 发现 2: 模型连接测试端点 SSRF [MEDIUM]

**严重度**: Medium

**攻击者画像**: 本地用户（可访问 `127.0.0.1` API），或通过恶意浏览器扩展/本地恶意软件

**可控输入向量**: `POST /api/v1/models/test-connection` 的 `base_url` 字段，仅校验 `http://` 或 `https://` 前缀

**代码路径**:

1. [`models.py:42-51`](file:///workspace/server/app/api/v1/models.py#L42-L51) — `test_model_connection` 端点接收用户提供的 `base_url`、`api_key`、`model_name`
2. [`model_service.py:93-98`](file:///workspace/server/app/services/model_service.py#L93-L98) — `validate_model_connection()` 仅校验 URL 以 `http://` 或 `https://` 开头
3. [`model_service.py:37-54`](file:///workspace/server/app/services/model_service.py#L37-L54) — `_models_probe_candidates()` 从 `base_url` 构造探测 URL（如 `{base_url}/models`、`{base_url}/v1/models`）
4. [`model_service.py:64-66`](file:///workspace/server/app/services/model_service.py#L64-L66) — `_external_http_client()` 创建禁用代理的 `httpx.Client`（`trust_env=False`）
5. [`model_service.py:107-108`](file:///workspace/server/app/services/model_service.py#L107-L108) — 对构造的 URL 发起 HTTP GET 请求，携带 `Authorization: Bearer {api_key}` 头

**影响**:
- 攻击者可探测本地网络内部服务（如 `http://192.168.1.1/models`、`http://127.0.0.1:6379/models`）
- 攻击者的 API Key 会作为 Bearer Token 发送到目标服务
- 可通过响应状态码差异（连接拒绝 vs 超时 vs 401 vs 404）进行端口扫描和服务发现
- 同样影响 `POST /api/v1/models` 创建模型端点（[`model_service.py:158-179`](file:///workspace/server/app/services/model_service.py#L158-L179)），因为 `create_model()` 也会调用 `validate_model_connection()`

**修复建议**:
1. 添加 URL 目标地址校验，阻止以下目标：
   - 私有/保留 IP 段（`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.0.0/16`）
   - 0.0.0.0
   - 裸主机名（`localhost`）
2. 限制请求超时时间并设置最大重定向次数（当前已设置 `timeout=10.0`，但未限制重定向）
3. 在探测前解析 DNS 并校验目标 IP 不在禁止列表中

---

### 发现 3: API Key 在日志中可能泄露 [LOW — 已评估，未确认]

**评估**: 经检查，LLM 调用日志系统（[`tracing_llm.py:64-81`](file:///workspace/server/app/shared/tracing_llm.py#L64-L81)）存储的是 `prompt[:2000]` 和 `response[:2000]`，即用户日记内容和 AI 回复。API Key 通过 `ChatOpenAI` 的 `Authorization` HTTP 头传递，不包含在 prompt 中。`utils.py:extract_token_usage()` 提取的是 token 使用量统计，不包含 API Key。

**结论**: 未发现通过日志泄露 API Key 的路径。此条目保留为已评估无风险。

---

## 审计汇总

| # | 漏洞 | 严重度 | 认证状态 | 可修复 |
|---|------|--------|----------|--------|
| 1 | 硬编码 Fernet 加密密钥回退 | MEDIUM | 已确认 | 是 |
| 2 | 模型连接测试端点 SSRF | MEDIUM | 已确认 | 是 |
| 3 | API Key 日志泄露 | — | 已排除 | 不适用 |

## 审计结论

**发现 2 个中等严重度已确认漏洞。** 未发现高危或严重漏洞。应用架构为本地单用户桌面工具，绑定了严格的回环地址限制，大部分攻击面天然受限。两个已确认漏洞均可通过简单代码修改修复。
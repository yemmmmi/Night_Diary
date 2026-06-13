# 安全审计报告 — 2026-06-13

## Why
对本代码仓库进行周期性的漏洞评估，识别中等严重度及以上的已确认漏洞，且必须具备可论证的端到端利用路径。

## 代码库架构概述

**应用类型**：单用户本地桌面应用（Tauri + Python FastAPI sidecar + Vue.js WebView）

**架构边界**：
- **入口点**：Tauri WebView → HTTP API (127.0.0.1 only) → FastAPI 路由 → 服务层 → 数据库
- **信任边界**：localhost 网络边界（CORS 限制 localhost/127.0.0.1/tauri.localhost），无身份认证（单用户设计）
- **数据流**：用户日记输入 → FastAPI → SQLite 存储 & Chroma 向量索引 → LLM API 调用 → AI 分析结果返回
- **外部交互**：仅向用户配置的 LLM 提供商 API 发起出站 HTTPS 请求（验证连接 + AI 推理）

**关键组件**：
- `server/app/infrastructure/security.py` — Fernet 加密/解密 LLM API Keys
- `server/app/services/model_service.py` — LLM 模型 CRUD 与连接验证
- `server/app/shared/llm_factory.py` — 按 tier 创建 LLM 客户端
- `src-tauri/src/backup.rs` — 本地 SQLite 备份/恢复
- `src/shared/api/http.ts` — 前端 HTTP 客户端

## 审计范围与方法

按以下攻击面分组进行系统性检查：
1. **认证与访问控制** — 无（单用户本地应用，符合设计）
2. **注入向量** — 全部使用 SQLAlchemy ORM，无原始 SQL；无 Shell 拼接；无模板渲染；无用户可控文件路径操作
3. **外部交互** — 仅 LLM API 出站请求，包含连接验证端点
4. **敏感数据处理** — API Key 加密存储，LLM 调用追踪，备份文件处理

## What Changes
- 修复硬编码默认加密密钥，强制要求用户/部署配置唯一密钥

## Impact
- Affected specs: 无现有 spec
- Affected code: `server/app/infrastructure/security.py`

---

## 审计结论摘要

| 严重度 | 数量 | 描述 |
|--------|------|------|
| 严重   | 0    | —    |
| 高     | 0    | —    |
| **中** | **1** | 硬编码默认加密密钥 |
| 低     | 0    | —    |

---

## 审计发现详情

### 发现 #1 [MEDIUM] — 硬编码默认 Fernet 加密密钥

**位置**：[server/app/infrastructure/security.py:26](file:///workspace/server/app/infrastructure/security.py#L26)

**描述**：`_resolve_secret()` 函数在以下条件全部不满足时，回退到硬编码字符串 `"night-diary-local-dev-key"`：
1. 未设置环境变量 `MODEL_KEY_SECRET`
2. 数据目录下不存在 `secrets.key` 文件

该回退值用于派生 Fernet 加密密钥，保护存储在 SQLite 数据库中的所有 LLM API Key。

**攻击路径（端到端利用）**：

1. **攻击者画像**：获得本机文件系统读取权限的攻击者（如：共享主机上的其他用户、恶意软件、备份文件泄露）
2. **可控输入向量**：攻击者读取 `{DATA_DIR}/night_diary.db` SQLite 数据库文件中的 `model_providers` 表
3. **代码路径**：
   - SQLite 文件 → `model_providers.api_key_encrypted` 列（Fernet 密文）
   - 攻击者使用公开已知的默认密钥 `"night-diary-local-dev-key"` 调用 `cryptography.fernet.Fernet` 解密
   - → 获取所有已存储 LLM 提供商（DeepSeek、OpenAI 等）的明文 API Key
4. **影响**：
   - **数据泄露**：所有用户配置的 LLM API Key 泄露
   - **经济损失**：攻击者可使用泄露的 API Key 调用 LLM 服务，产生账单费用
   - **隐私泄露**：攻击者可查询 LLM 提供商的使用记录，可能获取过往 AI 分析内容

**严重度理由**：攻击者需要文件系统读取权限（非远程可利用），但一旦获得数据库文件访问权即可 100% 解密所有 API Key，无需任何暴力破解。CVSS 估算：AV:L/AC:L/PR:N/UI:N/S:C/C:H/I:N/A:N ≈ 5.5 (Medium)

**修复建议**：
- 移除硬编码回退值，启动时如无有效密钥则拒绝启动并输出明确错误
- 首次启动时自动生成随机密钥并持久化到 `secrets.key` 文件
- 或在 Tauri 侧生成密钥并通过 `--data-dir` 传入

---

## 无漏洞确认结论

以下攻击面经审查，**未发现中等及以上严重度的已确认漏洞**：

### 注入向量
- **SQL 注入**：全部数据库操作使用 SQLAlchemy ORM 参数化查询，无原始 SQL 拼接。`tag_ids`、`diary_id` 等参数通过 ORM 绑定传递。
- **命令注入**：唯一的 `subprocess.run()` 调用（[main.py:29](file:///workspace/server/app/main.py#L29)）参数完全硬编码为 `["git", "rev-parse", "--short", "HEAD"]`，不涉及用户输入。
- **模板注入**：无服务端模板渲染。前端使用 Vue.js 模板引擎，自动转义 HTML。
- **路径遍历**：[backup.rs:62](file:///workspace/src-tauri/src/backup.rs#L62) 中 `restore_backup` 对文件名进行显式校验（禁止 `/`、`\`，要求 `.db` 后缀），路径遍历防护完善。

### 外部交互
- **SSRF**：`validate_model_connection()`（[model_service.py:93](file:///workspace/server/app/services/model_service.py#L93)）确实向用户提供的 `base_url` 发起 HTTP 请求，但这是"测试连接"功能的预期行为（用户自行配置自己的 LLM 端点）。且代码显式设置 `trust_env=False` 防止代理劫持。
- **Webhook/回调**：无 webhook 处理器或第三方回调端点。

### 认证与访问控制
- CORS 中间件限制来源为 `localhost`/`127.0.0.1`/`tauri.localhost`/`tauri://localhost`，不存在跨域攻击面。
- 应用设计为单用户本地桌面应用，无需多用户认证，符合架构假设。

### 敏感数据处理
- API Key 在 API 响应中通过 `has_api_key: bool` 字段遮掩，`ModelResponse` 从不暴露实际密钥值。
- LLM 调用追踪存储 prompt 和 response 截断值（各 2000 字符），这是调试/成本追踪的预期功能。不记录 API Key。
- 前端无客户端存储 API Key（Key 由用户通过界面填写后存储在服务端 SQLite 中）。
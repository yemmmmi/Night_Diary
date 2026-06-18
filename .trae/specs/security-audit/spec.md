# 安全审计 Spec

## Why
对 Night Diary 代码仓库进行周期性漏洞评估，识别中等严重度及以上的已确认漏洞，确保不存在可被利用的安全风险。

## What Changes
- 梳理代码库架构：入口点、信任边界、组件间数据流转
- 系统性地检查高风险攻击面：
  - 认证与访问控制
  - 注入向量（SQL、Shell、模板、路径遍历）
  - 外部交互（Webhook、出站请求、第三方 API）
  - 敏感数据处理（密钥、凭证、日志、加密）
- 对每个潜在发现追踪从攻击者可控输入到影响的完整代码路径
- 仅保留能具体证明可利用性的发现

## Impact
- Affected specs: 无（纯审计，不修改代码）
- Affected code: 审计覆盖以下文件：
  - `server/app/main.py` — 入口点、CORS、shutdown 端点
  - `server/app/config.py` — 配置与密钥管理
  - `server/app/infrastructure/security.py` — 加密实现
  - `server/app/infrastructure/database.py` — SQLite 初始化与迁移
  - `server/app/api/v1/*.py` — 所有 API 路由
  - `server/app/api/deps.py` — 依赖注入
  - `server/app/api/schemas.py` — 请求/响应模型
  - `server/app/services/*.py` — 业务逻辑层
  - `server/app/shared/llm.py` / `llm_factory.py` — LLM 客户端
  - `src-tauri/src/lib.rs` / `process.rs` / `backup.rs` — Tauri 后端
  - `src/shared/api/http.ts` / `composables/useBackend.ts` — 前端 HTTP 层

## ADDED Requirements

### Requirement: 审计报告 — 硬编码默认加密密钥 (Medium)
系统 SHALL 识别并报告 `security.py` 中使用硬编码回退密钥 `"night-diary-local-dev-key"` 的问题，该密钥在用户未配置 `model_key_secret` 且无 `secrets.key` 文件时被用于加密存储的 LLM API Key。

#### Scenario: 攻击者获取数据库文件后可解密 API Key
- **GIVEN** 用户未设置 `MODEL_KEY_SECRET` 环境变量且 `{data_dir}/secrets.key` 文件不存在
- **WHEN** 攻击者通过恶意软件、共享电脑或备份泄露获取 SQLite 数据库文件 `night_diary.db`
- **THEN** 攻击者可使用公开已知的硬编码密钥解密 `model_providers` 表中所有 `api_key_encrypted` 字段，获取明文 LLM API Key
- **AND** 攻击者可利用被盗 API Key 进行未授权的 LLM API 调用，造成用户财务损失

### Requirement: 审计报告 — 无认证的 Shutdown 端点 (Low/Info)
系统 SHALL 识别并报告 `POST /shutdown` 端点无需认证即可调用的问题。

#### Scenario: 本地进程可关闭后端服务
- **GIVEN** 后端绑定在 `127.0.0.1` 且无认证机制
- **WHEN** 同一主机上的任意进程发送 `POST /shutdown` 请求
- **THEN** 后端进程在 0.3 秒后被 `os._exit(0)` 终止
- **AND** 影响为本地拒绝服务，但由于仅限 loopback 且为单用户桌面应用，严重度为信息级

### Requirement: 审计报告 — LLM API Key 通过 HTTP 明文传输 (Info)
系统 SHALL 识别并报告 API Key 在创建/更新模型配置时通过 HTTP 明文传输的问题。

#### Scenario: API Key 在 loopback 接口上明文传输
- **GIVEN** 后端仅绑定 `127.0.0.1`，使用 HTTP 而非 HTTPS
- **WHEN** 用户通过前端配置 LLM 模型（`POST /api/v1/models` 或 `PUT /api/v1/models/{id}`）
- **THEN** API Key 以明文形式在请求体中通过 loopback 接口传输
- **AND** 由于仅限 loopback 且为单用户桌面应用，实际风险为信息级
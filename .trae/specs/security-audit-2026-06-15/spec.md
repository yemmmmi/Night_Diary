# 安全审计报告 Spec

## Why
对 Night Diary V2 代码仓库进行周期性安全审计，识别中等严重度及以上的已确认漏洞，且必须具备可论证的端到端利用路径。

## 审计范围
- 后端：`server/app/` 下所有 Python 代码（FastAPI、服务层、领域层、基础设施层）
- 前端：`src/` 下 Vue 3 + TypeScript 代码
- Tauri 壳：`src-tauri/src/` 下 Rust 代码
- 配置：`server/.env.example`、`tauri.conf.json`、`capabilities/default.json`

## 审计方法
按以下分组系统性检查高风险攻击面：
- **认证与访问控制**：登录流程、会话管理、角色/权限校验
- **注入向量**：原始 SQL 查询、Shell 命令拼接、模板渲染、文件路径操作
- **外部交互**：Webhook 处理器、出站网络请求、第三方 API 集成
- **敏感数据处理**：代码或配置中的密钥、凭证或 PII 的日志记录、加密实践

## 审计结论

审计完成，共发现 **2 个中等严重度**的已确认漏洞。

---

## 已确认漏洞

### 漏洞 1：SSRF — 模型连接测试接口可被滥用于内网探测（Medium）

**严重度**：Medium（CVSS 3.1: 5.3 — AV:L/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:L）

**位置**：
- [server/app/api/v1/models.py#L42-L51](file:///workspace/server/app/api/v1/models.py#L42-L51) — `/api/v1/models/test-connection` 路由
- [server/app/services/model_service.py#L93-L139](file:///workspace/server/app/services/model_service.py#L93-L139) — `validate_model_connection` 函数
- [server/app/services/model_service.py#L64-L66](file:///workspace/server/app/services/model_service.py#L64-L66) — `_external_http_client` 绕过系统代理

**攻击者画像**：与受害者运行在同一台机器上的任意进程（另一个用户账户、恶意软件、或被入侵的浏览器扩展）

**可控输入向量**：`POST /api/v1/models/test-connection` 请求体中的 `base_url` 字段（`ModelTestConnectionRequest` schema，仅校验非空字符串长度 ≥1，无 URL 格式或目标地址限制）

**攻击路径**（端到端可复现）：

1. 攻击者通过 `curl` 或任意本地 HTTP 客户端向 `http://127.0.0.1:8000/api/v1/models/test-connection` 发送 POST 请求：

```json
{
  "model_name": "test",
  "api_key": "dummy",
  "base_url": "http://169.254.169.254"
}
```

2. FastAPI 路由 [models.py#L42-L51](file:///workspace/server/app/api/v1/models.py#L42-L51) 接收请求，调用 `model_service.validate_model_connection(body.base_url, body.api_key, model_name=body.model_name)`

3. `validate_model_connection` 在 [model_service.py#L99](file:///workspace/server/app/services/model_service.py#L99) 仅检查 `base_url.startswith(("http://", "https://"))` — 通过

4. 在 [model_service.py#L106](file:///workspace/server/app/services/model_service.py#L106) 创建 `_external_http_client()`，该客户端设置了 `trust_env=False` 绕过系统代理，使请求直接走系统路由表到达目标

5. 在 [model_service.py#L107-L115](file:///workspace/server/app/services/model_service.py#L107-L115) 遍历候选 URL 列表（如 `http://169.254.169.254/models`、`http://169.254.169.254/v1/models`）发起 GET 请求，并将 `api_key` 作为 `Authorization: Bearer` 头发送

6. 后端返回的 HTTP 状态码被映射为错误消息返回给攻击者（如 "API 返回状态码 401" vs "API 返回状态码 404"），攻击者可据此判断目标端口是否开放、服务是否存在

**影响**：
- 内网服务探测：攻击者可以扫描 `127.0.0.1`、`10.x.x.x`、`192.168.x.x`、`172.16-31.x.x` 等内网地址
- 云环境元数据泄露：在 AWS/阿里云等云环境中，可探测 `169.254.169.254` 获取实例元数据
- API Key 泄露：发送到攻击者控制的外部服务器的 `api_key` 参数（虽为攻击者提供，但可被用于将用户真实的 API Key 通过 SSRF 泄漏到攻击者控制的服务器）

**修复建议**：
1. 对 `base_url` 实施严格的 URL 校验：仅允许 HTTPS 协议，且目标域名/IP 必须在允许列表内（如 `api.deepseek.com`、`api.openai.com` 等已知 LLM 供应商）
2. 禁止目标地址为私有 IP 段（RFC 1918）、回环地址（127.0.0.0/8）、链路本地地址（169.254.0.0/16）
3. 限制出站连接的目标端口为常见 HTTPS 端口（443）
4. 考虑添加用户确认步骤：在向用户提供的 URL 发起连接前，通过 UI 提示用户确认

---

### 漏洞 2：硬编码加密密钥导致 API Key 可被轻易解密（Medium）

**严重度**：Medium（CVSS 3.1: 4.4 — AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N）

**位置**：
- [server/app/infrastructure/security.py#L20-L26](file:///workspace/server/app/infrastructure/security.py#L20-L26) — `_resolve_secret` 函数
- [server/app/infrastructure/security.py#L14-L17](file:///workspace/server/app/infrastructure/security.py#L14-L17) — `_derive_fernet_key` 函数

**攻击者画像**：获得受害者机器文件系统读取权限的本地攻击者（恶意软件、物理访问、或共享主机上的其他用户）

**可控输入向量**：攻击者读取 SQLite 数据库文件 `night_diary.db`（路径为 `{data_dir}/night_diary.db`，默认在 `~/.local/share/night-diary/` 或 `%APPDATA%/night-diary/`）

**攻击路径**（端到端可复现）：

1. 用户未设置 `MODEL_KEY_SECRET` 环境变量，且 `{data_dir}/secrets.key` 文件不存在（这是默认安装的常见情况）

2. `_resolve_secret` 在 [security.py#L26](file:///workspace/server/app/infrastructure/security.py#L26) 返回硬编码密钥 `"night-diary-local-dev-key"`

3. `_derive_fernet_key` 在 [security.py#L16](file:///workspace/server/app/infrastructure/security.py#L16) 对 `"night-diary-local-dev-key"` 执行 `SHA-256` 哈希，然后 `base64.urlsafe_b64encode` 得到 Fernet 密钥

4. 攻击者获取 SQLite 数据库文件后，读取 `model_providers` 表的 `api_key_encrypted` 列

5. 攻击者使用相同的公开密钥 `"night-diary-local-dev-key"` 派生 Fernet 密钥，解密所有已存储的 LLM API Key

6. 攻击者获得用户配置的所有 LLM 供应商的 API Key（如 DeepSeek、OpenAI 等），可用于：
   - 消耗用户的 API 配额
   - 访问用户在这些服务上的账户数据
   - 利用 API Key 进行进一步的攻击

**影响**：
- 所有通过应用配置的 LLM API Key 被泄露
- 攻击者可使用这些密钥调用 LLM API，产生费用
- 若 API Key 具有除聊天外的其他权限（如 OpenAI 的 Codex、DALL-E 等），攻击面更大

**修复建议**：
1. 移除硬编码回退密钥 `"night-diary-local-dev-key"`
2. 在应用首次启动时自动生成随机 Fernet 密钥并持久化到 `{data_dir}/secrets.key`
3. 若 `MODEL_KEY_SECRET` 未设置且 `secrets.key` 不存在，应拒绝启动并提示用户配置密钥
4. 在生成的 `secrets.key` 文件上设置适当的文件权限（仅所有者可读，如 `0o600`）

---

## 审计范围外 / 已评估但非漏洞的发现

以下项目经过了评估，但判定为不构成中等或以上严重度的漏洞：

| 项目 | 评估 | 理由 |
|------|------|------|
| CORS 配置 | 已确认安全 | 仅允许 loopback 来源，正则表达式正确限制了 `localhost`/`127.0.0.1`/`tauri.localhost` |
| SQL 注入 | 未发现 | 所有数据库查询使用 SQLAlchemy ORM 参数化查询 |
| Shell 命令注入 | 未发现 | 唯一 `subprocess.run` 调用（`git rev-parse`）无用户输入 |
| 模板注入 | 未发现 | 无服务端模板渲染 |
| 文件路径遍历 | 已确认安全 | `restore_backup` 正确校验文件名（禁止 `/`、`\`，必须 `.db` 结尾） |
| 认证缺失 | 已评估 | 本地桌面应用，绑定 127.0.0.1，无网络暴露 — 可接受 |
| CSP 为 null | 低风险 | 本地 WebView 加载本地文件，无外部内容加载 |
| LLM 调用日志记录 PII | 已评估 | 设计决策（CLAUDE.md 有明确文档），本地 SQLite 存储，prompt/response 截断至 2000 字符 |
| LLM Prompt 注入 | 已评估 | 用户自写日记内容，自我注入无安全意义；本地应用无多用户场景 |
| 模型下载 URL | 已确认安全 | `repo_id` 来自硬编码 `REQUIRED_MODELS` 元组，不可被用户控制 |
| Tauri Capabilities | 已确认安全 | 仅 `core:default` + `shell:allow-open`，无危险权限 |
| `/shutdown` 端点 | 已评估 | 本地桌面应用，仅 loopback 可达 — 可接受 |
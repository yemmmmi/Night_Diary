# 夜记（Night Diary）安全审计报告 Spec

## Why

对夜记代码仓库进行周期性安全审计，识别中等严重度及以上的已确认漏洞，且必须具备可论证的端到端利用路径。不报告理论性或推测性风险。

## 代码库架构概览

### 系统边界与信任模型

- **应用类型**：本地单用户桌面应用（Electron-like，基于 Tauri + Python FastAPI sidecar）
- **后端绑定**：`127.0.0.1` 仅回环接口，不暴露于网络
- **CORS 策略**：仅允许 `localhost` / `127.0.0.1` / `tauri.localhost` 来源
- **数据库**：本地 SQLite 文件，存储于 `{DATA_DIR}/night_diary.db`
- **认证机制**：无（设计如此——单用户本地应用）
- **会话管理**：无（无 JWT、无 Session、无 Redis）

### 入口点

| 入口 | 类型 | 访问控制 |
|------|------|----------|
| FastAPI REST API (`127.0.0.1:{port}`) | HTTP | 无认证，仅回环可达 |
| Tauri IPC (`invoke` 命令) | 进程内 IPC | 仅前端 WebView 可调用 |
| CLI 参数 (`--port`, `--data-dir`) | 进程启动参数 | 由 Tauri shell 控制 |

### 数据流转

```
用户输入（Vue 前端）
  → HTTP POST/GET → FastAPI sidecar (127.0.0.1)
  → Service Layer → SQLAlchemy ORM → SQLite
  → ChromaDB 向量索引（本地）
  → LLM API 调用（外部，通过用户配置的 API key）
  → 响应返回前端展示
```

### 关键组件

- **`server/app/infrastructure/security.py`**：Fernet 加密/解密 LLM API keys
- **`server/app/infrastructure/database.py`**：SQLAlchemy 引擎与会话管理
- **`server/app/services/model_service.py`**：模型提供商 CRUD 与连接测试
- **`server/app/shared/llm_factory.py`**：LLM 客户端工厂，解密 API key 并创建 ChatOpenAI 实例
- **`server/app/infrastructure/llm_call_tracer.py`**：LLM 调用日志（含 prompt/response 内容）
- **`src-tauri/src/backup.rs`**：SQLite 备份/恢复
- **`src-tauri/src/process.rs`**：Python sidecar 进程生命周期管理

---

## 审计结果

### 审计范围与方法

按以下分组系统性地检查了高风险攻击面：

1. **认证与访问控制**：登录流程、会话管理、角色/权限校验
2. **注入向量**：原始 SQL 查询、Shell 命令拼接、模板渲染、文件路径操作
3. **外部交互**：Webhook 处理器、出站网络请求、第三方 API 集成
4. **敏感数据处理**：代码或配置中的密钥、凭证或 PII 的日志记录、加密实践

对每个潜在发现，从攻击者可控输入到影响结果追踪了完整代码路径。

---

## 已确认漏洞

### 漏洞 1：LLM API Key 加密使用硬编码默认密钥（中等严重度）

**位置**：[`server/app/infrastructure/security.py`](file:///workspace/server/app/infrastructure/security.py#L20-L33)

**严重度**：Medium

**攻击者画像**：
- 本地攻击者（同一物理/多用户机器上的其他用户、恶意软件、或获得文件系统读取权限的攻击者）

**可控输入向量**：
- 攻击者能够读取 `{DATA_DIR}/night_diary.db` SQLite 数据库文件
- 以及 `{DATA_DIR}/secrets.key` 文件（如果存在）

**从输入到漏洞的确切代码路径**：

1. 用户在前端配置 LLM 模型时，API key 通过 `encrypt_api_key()` 函数加密存储：
   - `model_service.py:create_model()` → `encrypt_api_key(api_key, settings)` ([model_service.py](file:///workspace/server/app/services/model_service.py#L175))
   - `model_service.py:update_model()` → `encrypt_api_key(api_key, resolved_settings)` ([model_service.py](file:///workspace/server/app/services/model_service.py#L219))

2. 加密函数调用 `get_fernet()` 获取密钥：
   - [security.py#L29-L33](file:///workspace/server/app/infrastructure/security.py#L29-L33)

3. `get_fernet()` 调用 `_resolve_secret()` 获取原始密钥材料：
   - [security.py#L20-L26](file:///workspace/server/app/infrastructure/security.py#L20-L26)

4. **关键漏洞**：`_resolve_secret()` 的回退逻辑：
   ```python
   def _resolve_secret(settings: Settings) -> str:
       if settings.model_key_secret:          # 1. 环境变量 MODEL_KEY_SECRET
           return settings.model_key_secret
       key_file = Path(settings.data_dir) / "secrets.key"
       if key_file.is_file():                 # 2. 文件 secrets.key
           return key_file.read_text(encoding="utf-8").strip()
       return "night-diary-local-dev-key"     # 3. 硬编码回退 ← 漏洞！
   ```
   - 当 `MODEL_KEY_SECRET` 环境变量未设置（默认状态），且 `secrets.key` 文件不存在时（全新安装的默认状态），使用硬编码字符串 `"night-diary-local-dev-key"`

5. 硬编码密钥通过 `_derive_fernet_key()` 派生为确定性的 Fernet 密钥：
   ```python
   def _derive_fernet_key(secret: str) -> bytes:
       digest = hashlib.sha256(secret.encode("utf-8")).digest()
       return base64.urlsafe_b64encode(digest)
   ```
   SHA256("night-diary-local-dev-key") 的结果是公开可计算的

6. 攻击者读取 SQLite 数据库中的 `model_providers` 表，获取 `api_key_encrypted` 字段，使用同样的派生密钥即可解密

**造成的影响**：
- **凭证泄露**：所有存储在数据库中的 LLM API Key（DeepSeek、OpenAI 等）可被解密
- **财务损失**：攻击者可使用泄露的 API Key 进行未经授权的 LLM 调用，产生费用
- **隐私泄露**：攻击者可通过 API 提供商的控制台查看调用历史（可能包含日记内容摘要）

**建议的修复方案**：

1. **短期（推荐）**：移除硬编码回退。如果用户未配置 `MODEL_KEY_SECRET`，在启动时生成一个随机密钥并持久化到 `secrets.key` 文件：
   ```python
   def _resolve_secret(settings: Settings) -> str:
       if settings.model_key_secret:
           return settings.model_key_secret
       key_file = Path(settings.data_dir) / "secrets.key"
       if key_file.is_file():
           return key_file.read_text(encoding="utf-8").strip()
       # 生成随机密钥并持久化
       import secrets
       new_key = secrets.token_hex(32)
       key_file.parent.mkdir(parents=True, exist_ok=True)
       key_file.write_text(new_key, encoding="utf-8")
       return new_key
   ```

2. **中期**：使用操作系统原生密钥存储（Windows DPAPI、macOS Keychain、Linux Secret Service API）代替文件存储

3. **长期**：考虑对整个 SQLite 数据库启用 SQLCipher 加密，保护所有用户数据（日记内容、分析结果等）

---

### 漏洞 2：未认证的 `/shutdown` 端点（低严重度）

**位置**：[`server/app/main.py`](file:///workspace/server/app/main.py#L138-L143)

**严重度**：Low

**攻击者画像**：
- 本地攻击者（同一机器上的其他进程/用户）

**可控输入向量**：
- HTTP POST 请求到 `http://127.0.0.1:{port}/shutdown`

**从输入到漏洞的确切代码路径**：

1. 路由定义不要求任何认证：
   ```python
   @app.post("/shutdown", tags=["meta"])
   async def shutdown() -> dict[str, str]:
       loop = asyncio.get_running_loop()
       loop.call_later(0.3, lambda: os._exit(0))
       return {"status": "shutting_down"}
   ```
   - [main.py#L138-L143](file:///workspace/server/app/main.py#L138-L143)

2. 任何能访问 `127.0.0.1:{port}` 的本地进程都可以发送 POST 请求触发关闭

**造成的影响**：
- **拒绝服务**：应用程序被强制终止，用户正在编辑的日记内容可能丢失
- 虽然 Tauri shell 会尝试重新启动后端，但用户体验受损

**建议的修复方案**：
- 添加一个简单的共享密钥验证（如读取本地文件中的 token），或通过 Tauri IPC 代理关闭请求而非直接暴露 HTTP 端点

---

## 未确认漏洞的审计结论

以下攻击面经过审计，**未发现**中等及以上严重度的可确认漏洞：

### 注入向量

| 检查项 | 结果 | 说明 |
|--------|------|------|
| SQL 注入 | 无风险 | 所有数据库操作使用 SQLAlchemy ORM 参数化查询。`database.py` 中的 `_run_lightweight_migrations` 使用了 `text()` 配合 f-string，但输入来自硬编码字典，非用户可控 |
| Shell 命令注入 | 无风险 | `main.py:_app_build_version()` 使用 `subprocess.run` 配合硬编码参数列表（非 shell 字符串） |
| 路径遍历 | 无风险 | `backup.rs:restore_backup()` 对文件名进行验证（禁止 `/`、`\`，要求 `.db` 后缀） |
| 模板注入 | 无风险 | 用户内容使用 Python f-string 拼接进 LLM prompt，非服务端模板引擎，无 SSTI 风险 |
| XSS | 无风险 | Vue.js 模板语法默认转义 HTML。`v-html` 未在用户可控内容上使用 |

### 外部交互

| 检查项 | 结果 | 说明 |
|--------|------|------|
| SSRF | 无风险 | `model_service.py:validate_model_connection()` 向用户配置的 URL 发送请求，但这是单用户本地应用——用户自己配置自己的模型 URL |
| 第三方 API 密钥泄露 | 已覆盖 | 见漏洞 1 |
| 不安全的出站请求 | 无风险 | 出站 LLM 请求使用 `httpx` 且 `trust_env=False`，不通过系统代理 |

### 敏感数据处理

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 日志中的敏感信息 | 低风险 | `llm_call_tracer.py` 和 `tracing_llm.py` 将 LLM prompt/response 记录到 SQLite（截断至 2000 字符），日记内容出现在 prompt 中。这是调试功能，在本地单用户应用中属于可接受风险 |
| 数据库加密 | 信息 | SQLite 数据库文件未加密存储。日记内容、分析结果、LLM 调用日志均以明文存储。建议未来版本考虑 SQLCipher |
| 环境变量中的密钥 | 无风险 | `.env.example` 正确标注了敏感字段，`.gitignore` 应排除 `.env` 文件 |

---

## 审计总结

- **审计范围**：全代码仓库（Python 后端 + Rust Tauri shell + Vue 前端）
- **已确认漏洞**：1 个中等严重度，1 个低严重度
- **关键风险**：LLM API Key 加密使用硬编码默认密钥，导致默认配置下加密形同虚设
- **总体安全态势**：作为本地单用户桌面应用，安全设计总体合理。主要改进点在于加密密钥管理
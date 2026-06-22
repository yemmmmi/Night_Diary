# 安全审计报告 — 硬编码加密密钥回退

## Why

在对本代码仓库（Night Diary / 夜记）进行周期性安全审计后，发现 1 个中等严重度已确认漏洞：LLM API Key 的静态加密密钥存在硬编码回退值，导致攻击者在获取数据库文件后可轻易解密所有已存储的 API 密钥。

## 审计范围

- **代码库**：/workspace（完整后端 + 前端 + Tauri 桌面壳）
- **审计方法**：按攻击面分组系统性检查（认证与访问控制、注入向量、外部交互、敏感数据处理）
- **审计标准**：仅报告中等严重度及以上、具备可论证端到端利用路径的已确认漏洞

## 审计架构摘要

| 维度 | 评估 |
|------|------|
| 应用类型 | 单用户本地桌面日记应用 |
| 后端 | FastAPI Python，绑定 `127.0.0.1`，无外部网络暴露 |
| 前端 | Vue.js + Tauri 桌面壳 |
| 数据库 | SQLite，存储于 `~/.local/share/night-diary/` |
| 认证 | 无（单用户本地应用，设计如此） |
| 外部交互 | LLM API（用户可配置 provider）、HuggingFace 模型下载 |
| CORS | 限制为 localhost 来源 |

## 审计结论

**审计完成 — 发现 1 个中等严重度已确认漏洞。**

---

## 已确认漏洞

### [中等] FINDING-001: LLM API Key 加密密钥硬编码回退

**严重度**：中等

**位置**：[`server/app/infrastructure/security.py:26`](file:///workspace/server/app/infrastructure/security.py#L26)

#### 攻击者画像

- **类型**：能够读取本地文件系统的恶意进程或用户（非 root 权限即可）
- **典型场景**：通过钓鱼/恶意软件获取用户机器的文件读取权限，或物理访问未锁定的设备

#### 可控输入向量

攻击者读取以下路径的 SQLite 数据库文件：
- Linux: `~/.local/share/night-diary/night_diary.db`
- Windows: `%APPDATA%/night-diary/night_diary.db`
- macOS: `~/Library/Application Support/night-diary/night_diary.db`

#### 从输入到漏洞的确切代码路径

**步骤 1** — 密钥解析逻辑（[`security.py:20-27`](file:///workspace/server/app/infrastructure/security.py#L20-L27)）：

```python
def _resolve_secret(settings: Settings) -> str:
    if settings.model_key_secret:
        return settings.model_key_secret
    key_file = Path(settings.data_dir) / "secrets.key"
    if key_file.is_file():
        return key_file.read_text(encoding="utf-8").strip()
    return "night-diary-local-dev-key"  # ← 硬编码回退
```

当用户未设置 `MODEL_KEY_SECRET` 环境变量、且 `secrets.key` 文件不存在时，加密密钥直接回退到字符串 `"night-diary-local-dev-key"`。此字符串在源代码中明文可见，对任何能访问 GitHub 仓库或已安装应用二进制文件的人均已知。

**步骤 2** — API Key 加密存储（[`model_service.py:173`](file:///workspace/server/app/services/model_service.py#L173)）：

```python
row = ModelProviderRow(
    ...
    api_key_encrypted=encrypt_api_key(api_key, settings),  # 使用上述回退密钥加密
    ...
)
```

**步骤 3** — 攻击者解密（[`security.py:36-37`](file:///workspace/server/app/infrastructure/security.py#L36-L37)）：

```python
def encrypt_api_key(plain: str, settings: Settings | None = None) -> str:
    return get_fernet(settings).encrypt(plain.encode("utf-8")).decode("utf-8")
```

攻击者只需：
1. 读取 SQLite 数据库文件中的 `model_providers` 表
2. 提取 `api_key_encrypted` 列的值
3. 使用已知密钥 `"night-diary-local-dev-key"` 初始化 Fernet 实例
4. 调用 `decrypt()` 解密所有 API Key

#### 造成的影响

- **凭证泄露**：攻击者获取用户的 LLM API Key（如 DeepSeek、OpenAI 等），可用于：
  - 盗用 API 配额，产生财务损失
  - 通过 LLM provider 的 API 日志获取用户发送的日记内容（如果 provider 记录请求内容）
  - 以用户身份滥用 LLM 服务，可能导致账号被封禁
- **影响范围**：所有未显式配置 `MODEL_KEY_SECRET` 环境变量的用户

#### 建议的修复方案

**方案 A（推荐）**：在应用首次启动时自动生成随机密钥并持久化到 `secrets.key` 文件

修改 `_resolve_secret` 逻辑：

```python
def _resolve_secret(settings: Settings) -> str:
    if settings.model_key_secret:
        return settings.model_key_secret
    key_file = Path(settings.data_dir) / "secrets.key"
    if key_file.is_file():
        return key_file.read_text(encoding="utf-8").strip()
    # 生成安全随机密钥并持久化
    import secrets
    new_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8")
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(new_key, encoding="utf-8")
    # 设置文件权限为仅 owner 可读
    os.chmod(key_file, 0o600)
    return new_key
```

**方案 B**：删除硬编码回退，强制要求用户设置 `MODEL_KEY_SECRET` 或确保 `secrets.key` 存在

---

## 审计排除项说明

以下攻击面经过审查，**未发现**中等及以上严重度的可利用漏洞：

| 攻击面 | 审查结果 |
|--------|----------|
| **SQL 注入** | 所有数据库查询使用 SQLAlchemy ORM 参数化查询，无原始 SQL 拼接 |
| **Shell 命令注入** | 唯一的 `subprocess.run` 调用（`git rev-parse`）使用硬编码参数列表 |
| **模板注入** | 无模板渲染引擎（Jinja2 等），API 响应均为 JSON |
| **路径遍历** | Tauri `restore_backup` 对 `filename` 参数做了 `/`、`\`、`.db` 后缀校验 |
| **认证绕过** | 应用设计为单用户本地应用，无认证系统，后端仅绑定 `127.0.0.1` |
| **CORS 配置** | 正则表达式正确锚定，仅允许 localhost 来源 |
| **敏感数据日志** | LLM 调用追踪中 prompt/response 被截断存储，API Key 不经过 prompt 内容 |
| **外部 SSRF** | `base_url` 校验 `startswith("http://", "https://")`，且 `trust_env=False` 禁用代理。在单用户本地应用场景下，盲 SSRF 风险为低严重度 |
| **模型下载** | `repo_id` 和 `filename` 均为硬编码常量 |
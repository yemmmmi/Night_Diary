# 夜记 (Night Diary) 安全审计报告

## Why
对代码仓库进行周期性漏洞评估，识别中等严重度及以上的已确认漏洞，且必须具备可论证的端到端利用路径。不报告理论性或推测性风险。

## 审计范围

### 代码库架构
- **Tauri (Rust)**: 桌面外壳，管理 Python 后端进程生命周期，处理文件备份/恢复
- **FastAPI (Python)**: 本地 sidecar 后端，绑定 127.0.0.1，提供 REST API
- **Vue.js**: 前端 SPA，通过 HTTP 与本地后端通信
- **SQLite**: 持久化存储（日记、分析、配置、LLM 调用日志）
- **ChromaDB**: 向量嵌入存储（日记内容语义检索）
- **LangChain**: AI/LLM 集成，对接外部 LLM API（DeepSeek 等）

### 信任边界
1. 应用为单用户本地桌面应用，后端仅绑定 `127.0.0.1`
2. 无认证系统、无 JWT、无会话管理、无多租户
3. CORS 仅允许 localhost/127.0.0.1/tauri.localhost 来源
4. Tauri 权限配置为 `shell:allow-open`

### 审计分组
- **认证与访问控制**: 无认证机制，所有 API 端点对本地进程开放
- **注入向量**: SQL（全部使用 ORM 参数化查询，无风险）；Shell（git 命令固定参数，无用户输入）；模板（无服务端模板）；文件路径（备份路径有校验过滤）
- **外部交互**: 出站 LLM API 调用，无 Webhook 处理
- **敏感数据处理**: API Key 加密存储、日记内容日志记录、加密实践

---

## 发现汇总

### HIGH — 2 个已确认漏洞
| ID | 标题 | 位置 |
|----|------|------|
| SEC-01 | 硬编码默认加密密钥导致 API Key 可被解密 | `server/app/infrastructure/security.py:26` |
| SEC-02 | LLM 调用日志明文存储用户日记内容 | `server/app/shared/tracing_llm.py:75-76`, `server/app/infrastructure/models/llm_call_log.py:20-21` |

### MEDIUM — 2 个已确认漏洞
| ID | 标题 | 位置 |
|----|------|------|
| SEC-03 | 未认证的 /shutdown 端点可被本地拒绝服务攻击 | `server/app/main.py:135-140` |
| SEC-04 | 未认证的 /models/test-connection 端点可被用作本地 SSRF 探测 | `server/app/api/v1/models.py:42-51`, `server/app/services/model_service.py:93-139` |

---

## ADDED Requirements

### Requirement: SEC-01 — 硬编码默认加密密钥修复
系统 SHALL 不允许使用硬编码的默认值作为加密密钥。当 `MODEL_KEY_SECRET` 环境变量和 `secrets.key` 文件均未配置时，系统 SHALL 在启动时自动生成一个随机密钥并持久化到 `secrets.key` 文件。

#### Scenario: 首次启动无配置
- **GIVEN** 用户首次启动应用，未设置 `MODEL_KEY_SECRET` 环境变量，且 `secrets.key` 文件不存在
- **WHEN** 应用启动
- **THEN** 系统 SHALL 自动生成一个安全的随机 Fernet 密钥并写入 `secrets.key` 文件

#### Scenario: 已配置环境变量
- **GIVEN** 用户已设置 `MODEL_KEY_SECRET` 环境变量
- **WHEN** 应用启动
- **THEN** 系统 SHALL 使用环境变量中的密钥，不生成新密钥

### Requirement: SEC-02 — LLM 调用日志脱敏
系统 SHALL 不在 `llm_call_logs` 表中明文存储包含日记内容（用户 PII）的 prompt 和 response 字段。

#### Scenario: LLM 调用追踪
- **GIVEN** 系统执行一次 LLM 分析调用
- **WHEN** TracingLLMClient 记录调用日志
- **THEN** prompt 和 response 字段 SHALL 不包含用户日记原文内容，仅存储元数据（如 token 数量、延迟、模型名称、错误信息）或脱敏后的摘要

### Requirement: SEC-03 — /shutdown 端点保护
系统 SHALL 对 `/shutdown` 端点增加基本保护，防止任意本地进程触发关闭。

#### Scenario: 外部进程尝试关闭
- **GIVEN** 后端服务正在运行
- **WHEN** 非 Tauri 外壳进程发送 POST 到 `/shutdown`
- **THEN** 系统 SHALL 拒绝该请求

### Requirement: SEC-04 — /models/test-connection SSRF 防护
系统 SHALL 对 `/models/test-connection` 端点增加 URL 校验，禁止向内网地址发起连接探测。

#### Scenario: 用户测试模型连接
- **GIVEN** 用户在设置中配置了外部 LLM API 地址
- **WHEN** 用户发起连接测试
- **THEN** 系统 SHALL 验证目标 URL 为非内网地址（禁止 localhost、127.0.0.0/8、10.0.0.0/8、172.16.0.0/12、192.168.0.0/16 等）

---

## MODIFIED Requirements
无。

## REMOVED Requirements
无。

---

## 审计结论
共发现 **4** 个已确认漏洞：**2 个 HIGH**、**2 个 MEDIUM**。所有漏洞均有可论证的端到端利用路径。建议优先修复 HIGH 级别漏洞。

### 未发现问题的高风险区域（已验证安全）
- SQL 注入：全部使用 SQLAlchemy ORM 参数化查询
- Shell 命令注入：无用户可控输入传入 shell 命令
- 服务端模板注入：无服务端模板渲染
- 路径遍历：备份恢复接口有路径校验（`/`, `\`, `.db` 后缀）
- API Key 泄露至前端：API 响应仅暴露 `has_api_key` 布尔值，不返回实际密钥
- 跨站请求伪造（CSRF）：本地应用，CORS 限制 localhost 来源，无实际风险
- XSS：本地桌面应用，无可反射用户内容的服务端渲染
# 安全审计检查清单

## 架构梳理
- [x] 后端入口点已分析 (`main.py`, `config.py`)
- [x] API 路由与依赖注入已分析 (`api/v1/*`, `api/deps.py`)
- [x] 数据库层已分析 (`infrastructure/database.py`)
- [x] LLM 集成已分析 (`shared/llm.py`, `shared/llm_factory.py`, `services/ai/*`)
- [x] Tauri 壳已分析 (`src-tauri/src/*`)
- [x] 前端 API 层已分析 (`src/shared/api/*`, `src/shared/composables/*`)

## 认证与访问控制
- [x] 确认无认证系统（单用户本地桌面应用，符合设计意图）
- [x] CORS 配置检查通过 — 仅允许 localhost 来源
- [x] 无会话管理（无需检查）

## 注入向量
- [x] SQL 注入 — 已排除。所有查询使用 SQLAlchemy ORM 参数化查询，动态 SQL 仅使用硬编码表名/列名
- [x] Shell 命令注入 — 已排除。`subprocess.run()` 使用硬编码参数列表，`Command::new()` 参数均来自程序内部
- [x] 模板注入 — 已评估。用户日记内容注入 LLM prompt，但 LLM 输出仅作为文本展示，无代码执行路径
- [x] 路径穿越 — 已排除。`backup.rs` 中 `restore_backup` 正确校验文件名不含 `/` 或 `\`

## 外部交互
- [x] SSRF 在 `model_service.py:validate_model_connection()` 中已确认 — 用户可控 `base_url` 仅校验协议前缀
- [x] 第三方 API 集成 — 天气 API (`restapi.amap.com`) 使用硬编码域名，无注入风险
- [x] 无 Webhook 处理器

## 敏感数据处理
- [x] 硬编码 Fernet 加密密钥回退已确认 — `security.py` 中 `"night-diary-local-dev-key"` 为默认密钥
- [x] 日志敏感信息泄露 — 已排除。LLM 调用日志不包含 API Key（仅存储 prompt 和 response 截断文本）
- [x] 环境变量配置 — `.env.example` 中无硬编码密钥，`MODEL_KEY_SECRET` 默认为空

## 发现确认
- [x] 发现 1: 硬编码 Fernet 加密密钥回退 — 代码路径已追踪，利用性已确认
- [x] 发现 2: 模型连接测试端点 SSRF — 代码路径已追踪，利用性已确认
- [x] 发现 3: API Key 日志泄露 — 已评估并排除

## 报告完整性
- [x] 每个发现包含攻击者画像
- [x] 每个发现包含可控输入向量
- [x] 每个发现包含端到端代码路径（含文件和行号）
- [x] 每个发现包含影响分析
- [x] 每个发现包含修复建议
- [x] 按严重度分组
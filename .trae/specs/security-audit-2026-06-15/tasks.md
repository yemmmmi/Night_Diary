# Tasks

本审计报告为只读分析任务，不涉及代码修改。以下为审计过程中的验证步骤，所有任务均已完成。

- [x] Task 1: 代码库架构梳理
  - [x] 理解入口点（FastAPI routes、Tauri commands）
  - [x] 识别信任边界（loopback 绑定、CORS、无认证）
  - [x] 追踪组件间数据流转（前端 → HTTP → FastAPI → 服务层 → 领域层 → LLM API）

- [x] Task 2: 认证与访问控制检查
  - [x] 审查所有 API 路由的认证状态
  - [x] 审查 CORS 配置
  - [x] 审查 Tauri 权限配置
  - [x] 审查 `/shutdown` 端点安全性

- [x] Task 3: 注入向量检查
  - [x] 审查所有数据库查询（SQLAlchemy ORM）
  - [x] 审查 subprocess 调用
  - [x] 审查文件路径操作（backup restore）
  - [x] 审查 LLM 提示构建（prompt injection）

- [x] Task 4: 外部交互检查
  - [x] 审查 `validate_model_connection` 出站 HTTP 请求
  - [x] 审查模型下载的 HuggingFace 请求
  - [x] 审查 `_external_http_client` 配置

- [x] Task 5: 敏感数据处理检查
  - [x] 审查 API Key 加密存储（Fernet）
  - [x] 审查 `_resolve_secret` 密钥派生逻辑
  - [x] 审查 LLM 调用日志中的 PII 记录
  - [x] 审查 API 响应中的密钥暴露

- [x] Task 6: 漏洞验证与报告编写
  - [x] 对每个潜在发现追踪完整代码路径
  - [x] 确认 SSRF 漏洞的可利用性
  - [x] 确认硬编码密钥漏洞的可利用性
  - [x] 编写结构化审计报告

# Task Dependencies
- 所有任务均为独立审计步骤，无严格依赖关系
- Task 6 依赖 Task 1-5 的分析结果
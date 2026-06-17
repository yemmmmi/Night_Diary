# Tasks

本审计不涉及代码修改，仅输出安全审计报告。任务为审计实施步骤。

- [x] Task 1: 梳理代码库架构 —— 识别入口点、信任边界、数据流转
  - [x] 阅读 [main.py](file:///workspace/server/app/main.py) 了解 FastAPI 应用启动和 CORS 配置
  - [x] 阅读 [config.py](file:///workspace/server/app/config.py) 了解配置结构和敏感信息处理
  - [x] 阅读 [lib.rs](file:///workspace/src-tauri/src/lib.rs) 和 [process.rs](file:///workspace/src-tauri/src/process.rs) 了解 Tauri 进程管理
  - [x] 阅读 [tauri.conf.json](file:///workspace/src-tauri/tauri.conf.json) 了解安全配置

- [x] Task 2: 审计认证与访问控制
  - [x] 检查所有 API 端点是否有认证/授权机制
  - [x] 检查 `/shutdown` 等敏感端点
  - [x] 检查 CORS 配置是否合理

- [x] Task 3: 审计注入向量
  - [x] 检查所有 SQL 查询是否使用参数化（[database.py](file:///workspace/server/app/infrastructure/database.py)）
  - [x] 检查所有 subprocess/Command 调用是否有用户输入拼接
  - [x] 检查是否有模板引擎和用户输入
  - [x] 检查文件路径操作是否有路径遍历防护

- [x] Task 4: 审计外部交互
  - [x] 检查 [model_service.py](file:///workspace/server/app/services/model_service.py) 中的出站 HTTP 请求
  - [x] 检查 [tool_factory.py](file:///workspace/server/app/services/ai/tool_factory.py) 中的天气 API 调用
  - [x] 检查 [model_downloader.py](file:///workspace/server/app/services/model_downloader.py) 中的 HuggingFace 下载

- [x] Task 5: 审计敏感数据处理
  - [x] 检查 [security.py](file:///workspace/server/app/infrastructure/security.py) 中的加密密钥管理
  - [x] 检查 [tracing_llm.py](file:///workspace/server/app/shared/tracing_llm.py) 和 [llm_call_tracer.py](file:///workspace/server/app/infrastructure/llm_call_tracer.py) 中的日志记录
  - [x] 检查日记内容等 PII 的存储方式

- [x] Task 6: 编写安全审计报告 —— 汇总已确认漏洞，输出结构化报告

# Task Dependencies
- Task 2-5 依赖于 Task 1（架构梳理）
- Task 2-5 之间无依赖，可并行执行
- Task 6 依赖于 Task 2-5 全部完成
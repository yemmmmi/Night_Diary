# Tasks

## 高危修复

- [ ] Task 1: 修复硬编码默认加密密钥 (SEC-01) — `server/app/infrastructure/security.py`
  - [ ] 修改 `_resolve_secret()` 函数：当 `model_key_secret` 为空且 `secrets.key` 文件不存在时，自动生成随机 Fernet 密钥并写入 `secrets.key` 文件
  - [ ] 添加日志提示用户密钥已自动生成
  - [ ] 移除硬编码 fallback 值 `"night-diary-local-dev-key"`
  - [ ] 验证：检查 `_resolve_secret` 不再返回硬编码字符串

- [ ] Task 2: LLM 调用日志脱敏 (SEC-02) — `server/app/shared/tracing_llm.py`
  - [ ] 修改 `_record()` 方法：将 `prompt` 字段替换为元数据摘要（如 `{agent_name}: 分析 diary_id={id} (len={n})`），不存储原文
  - [ ] 修改 `_record()` 方法：将 `response` 字段替换为元数据摘要（如 token_usage 信息），不存储完整文本
  - [ ] 验证：确认 `llm_call_logs` 表中不再存储日记原文

## 中危修复

- [ ] Task 3: /shutdown 端点保护 (SEC-03) — `server/app/main.py`
  - [ ] 添加请求来源校验：检查请求是否来自本地 Tauri 进程（通过自定义 Header 如 `X-NightDiary-Shutdown-Key`）
  - [ ] 在 Tauri `graceful_shutdown()` 中发送该 Header
  - [ ] 验证：外部 curl POST /shutdown（无 Header）返回 403

- [ ] Task 4: /models/test-connection SSRF 防护 (SEC-04) — `server/app/services/model_service.py`
  - [ ] 在 `validate_model_connection()` 函数开头添加 URL 校验逻辑
  - [ ] 解析目标 URL，拒绝解析到内网地址的请求（127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, [::1]）
  - [ ] 验证：尝试测试连接 `http://127.0.0.1:8080` 应返回错误

# Task Dependencies
- Task 2 依赖 Task 1（同一文件无直接依赖，可并行）
- Task 3 依赖 Task 1（无直接依赖，可并行）
- Task 4 依赖 Task 1（无直接依赖，可并行）
- 所有 Task 可并行执行
# Tasks — 安全审计修复

本任务列表基于安全审计 spec 中确认的漏洞，按优先级排列。

---

## 发现 1 (Medium): 硬编码默认加密密钥

- [ ] Task 1: 移除硬编码回退密钥，改为自动生成随机密钥
  - [ ] 修改 `_resolve_secret()` 函数：当 `model_key_secret` 未设置且 `secrets.key` 文件不存在时，使用 `secrets.token_urlsafe(32)` 生成随机密钥，并写入 `secrets.key` 文件
  - [ ] 添加启动日志：当自动生成密钥时，记录 INFO 日志说明密钥已生成
  - [ ] 验证：现有加密数据在密钥更新后仍可解密（向后兼容测试）

---

## 发现 2 (Medium): 天气 API Key 明文存储

- [ ] Task 2: 使用 Fernet 加密存储 `weather_api_key` 配置项
  - [ ] 修改 `app_config` 相关的存储逻辑：对 `weather_api_key` 值在写入前加密、读取后解密
  - [ ] 修改 `create_weather_tool()` 中的 `_get_config_value()` 调用，使其对加密值进行解密
  - [ ] 添加数据迁移：对已存在的明文 `weather_api_key` 值进行加密升级
  - [ ] 验证：加密后的值在数据库中不可读，API 调用仍正常工作

---

## 发现 3 (Low): 应用关闭端点无防护

- [ ] Task 3: 为 `/shutdown` 端点添加基础防护
  - [ ] 在 Tauri 启动时生成随机 shutdown token，通过环境变量或命令行参数传递给 Python 后端
  - [ ] 修改 `POST /shutdown` 端点，要求请求头中包含 `X-Shutdown-Token` 且值匹配
  - [ ] 验证：不带 token 或带错误 token 的请求返回 403

---

## 发现 4 (Low): LLM 调用日志明文存储

- [ ] Task 4: 为 LLM 调用日志添加隐私控制
  - [ ] 在 `settings` 中添加 `llm_log_enabled` 配置项（默认开启以保持向后兼容），允许用户关闭日志记录
  - [ ] 修改 `SqliteLLMCallTracer.record()` 方法，当 `llm_log_enabled=False` 时跳过记录
  - [ ] 添加日志自动清理：在 `llm_call_logs` 表添加 `created_at` 索引，支持按时间范围清理
  - [ ] 验证：关闭日志后不产生新记录，开启日志后正常记录

---

# Task Dependencies
- Task 1 和 Task 2 相互独立，可并行执行
- Task 3 和 Task 4 相互独立，可并行执行
- 所有 Task 互不依赖
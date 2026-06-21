# Checklist — 安全审计验证

## 发现 1 (Medium): 硬编码默认加密密钥

- [ ] `_resolve_secret()` 不再包含硬编码回退值 `"night-diary-local-dev-key"`
- [ ] 当 `model_key_secret` 未设置且 `secrets.key` 不存在时，自动生成随机密钥并写入 `secrets.key`
- [ ] 自动生成密钥后，已有加密数据可正常解密（向后兼容）
- [ ] 启动日志中记录密钥来源（env / file / auto-generated）

## 发现 2 (Medium): 天气 API Key 明文存储

- [ ] `app_config` 中 `weather_api_key` 的值在数据库中为加密形式（非明文）
- [ ] `create_weather_tool()` 正常读取并解密天气 API Key
- [ ] 天气 API 调用功能正常（端到端可工作）
- [ ] 已存在的明文 `weather_api_key` 值在启动时自动加密升级

## 发现 3 (Low): 应用关闭端点无防护

- [ ] `/shutdown` 端点拒绝无 token 的请求（返回 403）
- [ ] `/shutdown` 端点拒绝错误 token 的请求（返回 403）
- [ ] Tauri 端正常传递 token 时可成功关闭后端
- [ ] 启动日志中不泄露 shutdown token

## 发现 4 (Low): LLM 调用日志明文存储

- [ ] `llm_log_enabled` 配置项存在于 settings 中且默认值为 `True`
- [ ] 当 `llm_log_enabled=False` 时，`SqliteLLMCallTracer.record()` 不写入新记录
- [ ] 当 `llm_log_enabled=True` 时，日志正常记录
- [ ] 前端设置页面可切换日志开关
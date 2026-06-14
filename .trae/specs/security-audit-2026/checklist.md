# Security Audit Checklist

## SEC-01: 硬编码默认加密密钥修复
- [ ] `_resolve_secret()` 不再包含硬编码字符串 `"night-diary-local-dev-key"`
- [ ] 当 `model_key_secret` 为空且 `secrets.key` 不存在时，自动生成随机 Fernet 密钥并持久化
- [ ] 自动生成的密钥使用 `cryptography.fernet.Fernet.generate_key()` 生成
- [ ] 密钥写入 `{data_dir}/secrets.key` 文件，权限为仅 owner 可读（Linux/macOS: 0o600）
- [ ] 日志记录密钥生成事件

## SEC-02: LLM 调用日志脱敏
- [ ] `TracingLLMClient._record()` 的 `prompt` 参数不再包含日记原文
- [ ] `TracingLLMClient._record()` 的 `response` 参数不再包含完整 AI 回复文本
- [ ] `llm_call_logs` 表的 `prompt` 列仅包含元数据摘要
- [ ] `llm_call_logs` 表的 `response` 列仅包含元数据摘要

## SEC-03: /shutdown 端点保护
- [ ] `/shutdown` 端点检查请求来源
- [ ] 无有效凭证的请求返回 403 Forbidden
- [ ] Tauri `graceful_shutdown()` 发送正确凭证

## SEC-04: /models/test-connection SSRF 防护
- [ ] `validate_model_connection()` 在发送 HTTP 请求前校验目标 URL
- [ ] 拒绝解析到 IPv4 回环地址的 URL（127.0.0.0/8）
- [ ] 拒绝解析到 IPv6 回环地址的 URL（::1）
- [ ] 拒绝解析到私有网络地址的 URL（10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16）
- [ ] 返回明确的错误信息提示用户
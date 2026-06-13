# 安全审计验证清单

## 发现 #1: 硬编码默认加密密钥
- [ ] `_resolve_secret()` 函数不再包含硬编码回退值 `"night-diary-local-dev-key"`
- [ ] 当 `model_key_secret` 未设置且 `secrets.key` 不存在时，自动生成随机 Fernet 密钥并持久化到 `secrets.key`
- [ ] 密钥生成过程记录 INFO 级别日志
- [ ] 新生成的密钥格式正确（urlsafe base64 编码的 32 字节密钥）
- [ ] 现有单元测试全部通过，无回归
- [ ] API Key 加密存储和解密读取功能在自动密钥模式下正常工作
# Checklist

## 漏洞 1：硬编码加密密钥回退（Medium）
- [ ] `_resolve_secret()` 不再返回硬编码字符串 `"night-diary-local-dev-key"`
- [ ] 当 `MODEL_KEY_SECRET` 未设置且 `secrets.key` 不存在时，自动生成随机密钥（≥32 字节）并持久化到 `secrets.key`
- [ ] 已使用旧硬编码密钥加密的数据可被迁移（或提供明确的迁移路径）
- [ ] 相关单元测试通过

## 漏洞 2：未认证的 `/shutdown` 端点（Low）
- [ ] `/shutdown` 端点需要提供有效 token 才能执行关闭
- [ ] Tauri `graceful_shutdown()` 函数正确传递认证 token
- [ ] 功能测试验证：无效 token 返回 403
# Checklist — 修复硬编码 Fernet 加密密钥回退

- [ ] `_resolve_secret` 不再包含硬编码字符串 `"night-diary-local-dev-key"`
- [ ] 当 `secrets.key` 文件不存在时，自动生成密码学安全的随机密钥（`secrets.token_bytes(32)`）
- [ ] 生成的密钥被持久化到 `{data_dir}/secrets.key` 文件
- [ ] `secrets.key` 文件权限设置为 `0o600`（仅 owner 可读写）
- [ ] `secrets.key` 已被添加到 `.gitignore` 中
- [ ] `get_fernet` 函数仍能正确处理自动生成的密钥（base64 编码后长度为 44 字符）
- [ ] 现有单元测试全部通过（`server/tests/`）
- [ ] 修复后新安装用户无需手动配置密钥即可获得安全的 API Key 加密
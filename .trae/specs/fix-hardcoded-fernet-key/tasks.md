# Tasks — 修复硬编码 Fernet 加密密钥回退

- [ ] Task 1: 修改 `_resolve_secret` 函数，使硬编码回退改为自动生成随机密钥并持久化
  - [ ] 1.1 在 `server/app/infrastructure/security.py` 的 `_resolve_secret` 函数中，将硬编码字符串 `"night-diary-local-dev-key"` 替换为自动生成 `secrets.token_bytes(32)` 并 base64 编码的逻辑
  - [ ] 1.2 将生成的密钥写入 `{data_dir}/secrets.key` 文件
  - [ ] 1.3 在写入后设置文件权限为 `0o600`（仅 owner 可读写）
  - [ ] 1.4 确保 `secrets.key` 被添加到 `.gitignore`（如果尚未添加）

- [ ] Task 2: 验证修复不会破坏现有加密数据
  - [ ] 2.1 确认 `get_fernet` 函数签名和调用方兼容新的密钥生成逻辑
  - [ ] 2.2 确认 `_derive_fernet_key` 回退路径仍然可用（处理非标准密钥长度的情况）

- [ ] Task 3: 运行现有测试套件验证
  - [ ] 3.1 运行 `server/tests/` 下的单元测试确保无回归
  - [ ] 3.2 特别关注 `security.py` 相关的测试

# Task Dependencies

- Task 2 依赖 Task 1
- Task 3 依赖 Task 1 和 Task 2
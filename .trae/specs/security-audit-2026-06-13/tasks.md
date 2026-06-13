# Tasks

- [ ] Task 1: 修复硬编码默认加密密钥 — 移除 `_resolve_secret()` 中的回退值并实现安全密钥生命周期管理
  - [ ] 修改 `server/app/infrastructure/security.py` 中的 `_resolve_secret()` 函数：
    - 移除 `return "night-diary-local-dev-key"` 回退行
    - 当未设置 `model_key_secret` 且 `secrets.key` 文件不存在时，自动生成一个随机 Fernet 密钥（使用 `Fernet.generate_key()`）并写入 `secrets.key` 文件
    - 记录一条 INFO 级别日志说明已自动生成新密钥
  - [ ] 确保所有现有调用点（`encrypt_api_key`、`decrypt_api_key`、`get_fernet`）不受影响
- [ ] Task 2: 验证修复 — 确保 API Key 加密/解密在自动密钥生成后正常工作
  - [ ] 运行现有单元测试套件确认无回归
  - [ ] 手动验证：在无 `MODEL_KEY_SECRET` 且无 `secrets.key` 的环境下启动，确认密钥自动生成，并验证 LLM 模型配置功能正常

# Task Dependencies
- Task 2 依赖 Task 1
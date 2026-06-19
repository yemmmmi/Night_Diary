# Tasks

- [ ] Task 1: 修复硬编码加密密钥回退 (Medium) — 移除 `security.py` 中的硬编码默认密钥，改为启动时自动生成随机密钥并持久化
  - [ ] SubTask 1.1: 修改 `_resolve_secret()` 函数，移除硬编码回退，改为生成随机密钥并写入 `secrets.key` 文件
  - [ ] SubTask 1.2: 更新 `security.py` 中的 `get_fernet()` 以适配新的密钥解析逻辑
  - [ ] SubTask 1.3: 确保对已有使用硬编码密钥加密的数据的兼容性处理（迁移方案）
  - [ ] SubTask 1.4: 更新相关单元测试

- [ ] Task 2: 加固 `/shutdown` 端点 (Low) — 添加基本认证或改为通过 Tauri IPC 代理
  - [ ] SubTask 2.1: 在 `main.py` 的 `/shutdown` 端点添加共享密钥验证（读取本地 token 文件）
  - [ ] SubTask 2.2: 更新 `process.rs` 中的 `graceful_shutdown()` 以传递认证 token

# Task Dependencies

- Task 1 和 Task 2 相互独立，可并行执行
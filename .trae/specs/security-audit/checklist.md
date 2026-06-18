# Checklist

- [x] 代码库架构已梳理（入口点、信任边界、数据流转）
- [x] 所有 FastAPI 路由已检查认证状态
- [x] CORS 配置已审计
- [x] `/shutdown` 端点风险已评估
- [x] SQL 注入向量已全部检查（ORM 参数化查询、`_run_lightweight_migrations`）
- [x] Shell 命令注入向量已检查（`subprocess.run`、`Command::new`）
- [x] 路径遍历向量已检查（`restore_backup`、文件操作）
- [x] 模板注入已排除（无服务端模板引擎）
- [x] LLM API Key 的加密存储实现已审计
- [x] 加密密钥派生逻辑已审计（`_resolve_secret` → `get_fernet`）
- [x] 硬编码默认密钥 `"night-diary-local-dev-key"` 的可利用性已确认
- [x] 日志中敏感信息泄露已检查
- [x] API Key 在请求/响应中的暴露已检查
- [x] 外部 HTTP 请求配置已审计（代理、TLS）
- [x] HuggingFace 下载流程已审计
- [x] 每个已确认漏洞均包含：攻击者画像、可控输入、代码路径、影响、修复建议
- [x] 审计报告按严重度分组输出
- [x] 审计完成——已发现 1 个中等严重度漏洞
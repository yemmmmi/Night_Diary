# Security Audit Checklist

## Authentication & Access Control
- [ ] deps.py 认证依赖完整且安全
- [ ] security.py 实现正确的加密和哈希
- [ ] 所有API路由都有适当的权限校验
- [ ] 会话管理机制安全

## Injection Vectors
- [ ] 数据库查询使用参数化查询或ORM
- [ ] 无原始SQL拼接
- [ ] 文件路径操作有适当的验证
- [ ] 无命令注入风险
- [ ] 模板渲染无注入风险

## External Interactions
- [ ] Webhook/回调有输入验证
- [ ] 第三方API调用有适当的超时和错误处理
- [ ] 无提示注入漏洞

## Sensitive Data Handling
- [ ] 配置中无硬编码密钥
- [ ] 日志中无敏感数据
- [ ] 加密实践符合安全标准
- [ ] 前端无敏感数据暴露

## Final Report
- [ ] 所有检查项已完成
- [ ] 如有漏洞，已提供完整证据（攻击画像、输入向量、代码路径、影响、修复建议）
- [ ] 如无漏洞，输出"审计完成——未发现中等或更高严重度的已确认漏洞。"

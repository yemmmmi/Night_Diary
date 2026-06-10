# Tasks

## Task 1: 审计认证与访问控制
- [ ] 1.1: 检查 server/app/api/deps.py 认证依赖实现
- [ ] 1.2: 检查 server/app/infrastructure/security.py 安全实现
- [ ] 1.3: 检查各API路由的权限校验（diary.py, analysis.py, feedback.py, stats.py, tags.py）
- [ ] 1.4: 验证会话管理和token处理安全性

## Task 2: 审计注入向量
- [ ] 2.1: 检查 server/app/infrastructure/database.py 的SQL查询安全性
- [ ] 2.2: 检查 server/app/domain/knowledge/extractor.py 文件处理安全性
- [ ] 2.3: 检查 server/app/domain/agents/prompts.py 模板注入风险
- [ ] 2.4: 检查 server/app/services/ai/tool_factory.py 命令拼接风险
- [ ] 2.5: 检查文件路径操作安全性

## Task 3: 审计外部交互
- [ ] 3.1: 检查 webhook/回调处理逻辑
- [ ] 3.2: 检查第三方API调用的输入验证
- [ ] 3.3: 检查LLM调用中的提示注入风险

## Task 4: 审计敏感数据处理
- [ ] 4.1: 检查配置中的密钥和凭证管理
- [ ] 4.2: 检查日志记录中的敏感数据泄露
- [ ] 4.3: 检查加密实践和密钥存储
- [ ] 4.4: 检查前端API调用中的敏感数据暴露

## Task 5: 编译报告
- [ ] 5.1: 整理所有发现
- [ ] 5.2: 按严重度分组输出结构化报告

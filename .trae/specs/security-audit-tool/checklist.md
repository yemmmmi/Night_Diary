# Checklist

- [ ] `Finding` 数据类包含字段：severity、title、attacker_profile、input_vector、code_path、impact、fix_suggestion
- [ ] `Severity` 枚举定义 critical、high、medium 三个级别
- [ ] `AuditReport` 支持按严重度分组输出和 "无漏洞" 消息
- [ ] 认证审计器成功扫描所有 API 路由端点
- [ ] 认证审计器检测到 `/shutdown` 端点无认证保护
- [ ] 注入审计器扫描所有 `.py` 文件中的 SQL 拼接模式
- [ ] 注入审计器检测到 `main.py` 中 `subprocess.run` 调用
- [ ] 外部交互审计器检测到 `model_service.py` 中用户可控 URL 的 SSRF 风险
- [ ] 敏感数据审计器检测到 `security.py` 中硬编码默认密钥 `night-diary-local-dev-key`
- [ ] 敏感数据审计器检测到日志中可能泄露用户内容的模式
- [ ] CLI 支持 `--format` 和 `--output` 参数
- [ ] CLI 执行后输出结构化报告
- [ ] 审计结果中每个发现均包含完整的攻击者可控输入到影响的代码路径
- [ ] 无理论性或推测性风险被报告
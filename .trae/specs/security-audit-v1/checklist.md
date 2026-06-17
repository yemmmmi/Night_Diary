# Checklist

- [x] 架构梳理完成：入口点、信任边界、数据流转已记录
- [x] 所有 API 端点已审计认证/授权状态
- [x] `/shutdown` 端点已审计
- [x] CORS 配置已审计
- [x] 所有 SQL 查询已审计（注入风险）
- [x] 所有 subprocess/Command 调用已审计（命令注入风险）
- [x] 模板引擎使用已审计
- [x] 文件路径操作已审计（路径遍历风险）
- [x] 模型连接测试端点已审计（SSRF 风险）
- [x] 天气 API 调用已审计
- [x] HuggingFace 下载已审计
- [x] 加密密钥管理已审计（[security.py](file:///workspace/server/app/infrastructure/security.py)）
- [x] LLM 调用日志已审计（PII 泄露风险）
- [x] 日记内容存储已审计
- [x] 每个已确认漏洞具有完整的攻击者画像、输入向量、代码路径、影响说明和修复建议
- [x] 安全审计报告已输出，格式符合要求
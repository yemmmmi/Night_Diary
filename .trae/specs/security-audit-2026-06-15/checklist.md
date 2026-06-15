# Checklist

## 审计方法论验证
- [x] 代码库架构已完整梳理（入口点、信任边界、数据流转）
- [x] 所有四个高风险攻击面分组均已系统性检查
- [x] 每个潜在发现已追踪完整代码路径（攻击者可控输入 → 影响结果）

## 漏洞 1：SSRF — 模型连接测试接口
- [x] 攻击者画像已明确（同机任意进程）
- [x] 可控输入向量已识别（`base_url` 字段）
- [x] 从输入到漏洞的完整代码路径已追踪（[models.py#L42-L51](file:///workspace/server/app/api/v1/models.py#L42-L51) → [model_service.py#L93-L139](file:///workspace/server/app/services/model_service.py#L93-L139)）
- [x] 影响已明确说明（内网探测、元数据泄露、API Key 泄露）
- [x] 修复建议已提供

## 漏洞 2：硬编码加密密钥
- [x] 攻击者画像已明确（本地文件系统读取权限）
- [x] 可控输入向量已识别（SQLite 数据库文件）
- [x] 从输入到漏洞的完整代码路径已追踪（[security.py#L20-L26](file:///workspace/server/app/infrastructure/security.py#L20-L26) → `api_key_encrypted` 列解密）
- [x] 影响已明确说明（LLM API Key 泄露）
- [x] 修复建议已提供

## 排除项验证
- [x] CORS 配置已验证安全（loopback-only 正则）
- [x] SQL 注入已验证无风险（ORM 参数化查询）
- [x] Shell 命令注入已验证无风险（无用户输入子进程）
- [x] 模板注入已验证无风险（无服务端模板）
- [x] 文件路径遍历已验证安全（backup restore 正确校验）
- [x] 认证缺失已评估（本地桌面应用，可接受）
- [x] CSP 为 null 已评估（本地 WebView，低风险）
- [x] LLM 日志 PII 已评估（设计决策，本地存储）
- [x] Tauri Capabilities 已评估（无危险权限）
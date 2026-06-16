# 自动化安全审计工具 规格说明

## Why
代码仓库需要周期性的安全审计能力，以识别中等严重度及以上的已确认漏洞。当前缺乏系统化、自动化的安全审计流程，人工审计依赖经验且容易遗漏高风险攻击面。该工具将提供可重复、有据可依的漏洞评估能力。

## What Changes
- 新增 `server/app/tools/security_audit.py` —— 安全审计引擎核心模块，包含四组审计器
- 新增 CLI 入口 `server/scripts/run_security_audit.py` —— 命令行审计执行脚本
- 审计覆盖四大攻击面：认证与访问控制、注入向量、外部交互、敏感数据处理
- 输出结构化 JSON/Markdown 审计报告，按严重度分组，包含端到端利用路径证据
- 每个发现必须包含：攻击者画像、可控输入向量、完整代码路径、影响说明、修复建议

## Impact
- Affected specs: 无（新增独立工具）
- Affected code: `server/app/tools/`（新建）, `server/scripts/`（新建）

## ADDED Requirements

### Requirement: 认证与访问控制审计
系统 SHALL 审计所有 API 端点是否存在认证缺失、越权访问和会话管理缺陷。

#### Scenario: 识别无认证保护的敏感操作端点
- **WHEN** 审计器扫描所有 API 路由定义
- **THEN** 系统 SHALL 列出所有未经过认证中间件保护却执行数据增删改操作的端点
- **AND** 报告每个端点的 HTTP 方法、路径、操作类型和风险等级

#### Scenario: 识别横纵向越权可能
- **WHEN** 审计器分析通过 ID 参数访问资源的端点
- **THEN** 系统 SHALL 检查端点是否校验资源归属（如 user_id 关联）
- **AND** 标记存在 IDOR（Insecure Direct Object Reference）风险的端点

### Requirement: 注入向量审计
系统 SHALL 审计代码中潜在的 SQL 注入、命令注入、模板注入和路径遍历风险点。

#### Scenario: 检测原始 SQL 拼接
- **WHEN** 审计器扫描数据库访问代码
- **THEN** 系统 SHALL 识别使用字符串拼接或 f-string 构建 SQL 查询的代码位置
- **AND** 报告文件路径、行号和拼接内容

#### Scenario: 检测 Shell 命令注入
- **WHEN** 审计器扫描 `subprocess`、`os.system` 等系统调用
- **THEN** 系统 SHALL 检查命令参数是否包含用户可控输入
- **AND** 报告潜在的命令注入路径

#### Scenario: 检测路径遍历风险
- **WHEN** 审计器扫描文件操作（文件读写、路径拼接）
- **THEN** 系统 SHALL 检查文件路径是否由用户输入直接拼接构成
- **AND** 报告无路径校验的文件操作点

### Requirement: 外部交互审计
系统 SHALL 审计出站网络请求和第三方 API 集成中的 SSRF、数据泄露和中间人攻击风险。

#### Scenario: 检测 SSRF 风险
- **WHEN** 审计器扫描 HTTP 客户端调用（httpx、requests 等）
- **THEN** 系统 SHALL 检查请求 URL 是否部分或全部受用户输入控制
- **AND** 报告用户可控 URL 的出站请求代码位置

#### Scenario: 检测明文传输敏感数据
- **WHEN** 审计器扫描外部 API 调用
- **THEN** 系统 SHALL 检查请求头或请求体中是否携带未加密的 API Key 或凭证
- **AND** 报告敏感数据外发风险

### Requirement: 敏感数据处理审计
系统 SHALL 审计代码中的密钥管理、凭证泄露和隐私数据日志记录风险。

#### Scenario: 检测硬编码凭证
- **WHEN** 审计器扫描配置文件和源代码
- **THEN** 系统 SHALL 识别硬编码的 API Key、密码或密钥材料
- **AND** 报告具体的文件路径、行号和凭证类型

#### Scenario: 检测敏感数据日志泄露
- **WHEN** 审计器扫描日志输出语句（logger.info/error 等）
- **THEN** 系统 SHALL 检查日志内容是否包含 API Key、用户内容或 PII
- **AND** 报告潜在的日志泄露点

#### Scenario: 检测弱加密实践
- **WHEN** 审计器扫描加密相关代码
- **THEN** 系统 SHALL 检查是否使用弱哈希算法（MD5、SHA1）、硬编码密钥或可预测的密钥派生
- **AND** 报告弱加密使用位置

### Requirement: 漏洞报告输出
系统 SHALL 以结构化格式输出审计结果，只包含中等严重度及以上的已确认漏洞。

#### Scenario: 按严重度分组输出
- **WHEN** 审计完成
- **THEN** 系统 SHALL 按 Critical > High > Medium 分组输出发现
- **AND** 每个发现包含字段：严重度、标题、攻击者画像、输入向量、代码路径（文件:行号）、影响、修复建议

#### Scenario: 无已确认漏洞时的输出
- **WHEN** 审计完成且无中等及以上漏洞
- **THEN** 系统 SHALL 输出："审计完成——未发现中等或更高严重度的已确认漏洞。"

#### Scenario: 仅报告可论证的漏洞
- **WHEN** 审计器发现潜在风险
- **THEN** 系统 SHALL 遍历从攻击者可控输入到影响的完整代码路径
- **AND** 仅当端到端利用路径可具体证明时才报告
- **AND** 排除理论性或推测性风险
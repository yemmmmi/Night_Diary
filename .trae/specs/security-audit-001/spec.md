# Security Audit Specification

## Why
本代码仓库需要周期性的安全审计，以识别并修复中等严重度及以上的已确认漏洞，确保不存在可利用的端到端攻击路径。

## What Changes
本次审计为纯分析任务，不修改代码。审计范围覆盖以下高风险攻击面：
- **认证与访问控制**：登录流程、会话管理、角色/权限校验
- **注入向量**：原始 SQL 查询、Shell 命令拼接、模板渲染、文件路径操作
- **外部交互**：Webhook 处理器、出站网络请求、第三方 API 集成
- **敏感数据处理**：密钥、凭证、PII 的日志记录、加密实践

## Impact
- 受审计代码：整个代码库（server/ 和 src/）
- 入口点：server/app/main.py, src/main.ts, src-tauri/

## ADDED Requirements

### Requirement: Security Audit
系统必须能够识别并报告所有中等严重度及以上的已确认漏洞。

#### Scenario: 发现漏洞
- **WHEN** 审计过程中发现可利用的安全漏洞
- **THEN** 必须输出结构化报告，包含：攻击者画像、输入向量、代码路径、影响、修复建议

#### Scenario: 无漏洞
- **WHEN** 审计完成且未发现中等及以上漏洞
- **THEN** 输出："审计完成——未发现中等或更高严重度的已确认漏洞。"

## Audit Scope

### 1. 认证与访问控制
- [server/app/api/deps.py](file:///workspace/server/app/api/deps.py) - 认证依赖
- [server/app/infrastructure/security.py](file:///workspace/server/app/infrastructure/security.py) - 安全实现
- [server/app/api/v1/diary.py](file:///workspace/server/app/api/v1/diary.py) - 日记API权限
- [server/app/api/v1/analysis.py](file:///workspace/server/app/api/v1/analysis.py) - 分析API权限
- [server/app/api/v1/feedback.py](file:///workspace/server/app/api/v1/feedback.py) - 反馈API权限

### 2. 注入向量
- [server/app/infrastructure/database.py](file:///workspace/server/app/infrastructure/database.py) - SQL查询
- [server/app/domain/knowledge/extractor.py](file:///workspace/server/app/domain/knowledge/extractor.py) - 文件处理
- [server/app/domain/agents/prompts.py](file:///workspace/server/app/domain/agents/prompts.py) - 模板渲染
- [server/app/shared/llm.py](file:///workspace/server/app/shared/llm.py) - LLM调用
- [server/app/services/ai/tool_factory.py](file:///workspace/server/app/services/ai/tool_factory.py) - 工具创建

### 3. 外部交互
- [server/app/api/v1/feedback.py](file:///workspace/server/app/api/v1/feedback.py) - Webhook处理
- [server/app/shared/llm_factory.py](file:///workspace/server/app/shared/llm_factory.py) - 第三方API调用
- [server/app/services/ai/agent_executor.py](file:///workspace/server/app/services/ai/agent_executor.py) - Agent网络请求

### 4. 敏感数据处理
- [server/app/config.py](file:///workspace/server/app/config.py) - 配置中的密钥
- [server/app/infrastructure/security.py](file:///workspace/server/app/infrastructure/security.py) - 加密实践
- [server/app/shared/tracing.py](file:///workspace/server/app/shared/tracing.py) - 日志中的敏感数据
- [.env.example](file:///workspace/.env.example) - 环境变量示例

## Evidence Requirements
每个报告的问题必须包含：
1. **攻击者画像**：外部用户、已认证用户、内部服务等
2. **输入向量**：攻击者可控制的输入点
3. **代码路径**：从输入到漏洞的完整调用链
4. **影响**：数据泄露、权限提升、拒绝服务等
5. **修复建议**：具体的修复方案

## Output Format
```json
{
  "severity": "HIGH|MEDIUM",
  "title": "漏洞标题",
  "attacker_profile": "攻击者画像",
  "input_vector": "输入向量",
  "code_path": ["file1.py:line", "file2.py:line"],
  "impact": "影响描述",
  "remediation": "修复建议"
}
```

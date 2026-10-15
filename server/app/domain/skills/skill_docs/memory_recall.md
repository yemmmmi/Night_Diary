---
name: memory_recall
triggers: [上次, 之前, 记得吗, 说过, 聊过, 提到过, 那天, 那次, 以前, 昨天, 上周]
priority: 1.5
category: retrieval
token_cost_estimate: 200
---

# 记忆回溯技能

## 一句话摘要
当用户引用过往事件时，检索相关情节记忆并注入上下文。

## 触发条件
当 intent 为 retrospective_query 或 advice_seeking 时激活（分数 0.85）；
文本包含 2 个以上回溯触发词时激活（分数 0.8）；
单个回溯触发词时分数 0.6。

以上为第一阶段规则打分（规则地板）。当规则分数低于阈值 0.3 且本轮意图为
弱信号意图（情绪/回溯/建议/实体类）时，该技能进入灰色名单，由注册表的
第二阶段轻量 LLM 判定统一补打语义分，最终分数取 max(规则分, LLM分)——
LLM 只能救回漏检，不能否决规则已命中的激活。LLM 失败时降级为纯规则结果。

回溯触发词包括：上次、之前、记得吗、说过、聊过、提到过、那天、那次、
以前、昨天、上周。

## 能力详述
场景 2（多轮对话）专用技能，与场景 1 的 crisis_detector、sentiment_skill
互补。当用户引用过去发生的事情时，触发记忆回溯机制。

执行时返回触发标记，提示上游 Agent 在上下文中注入相关情节记忆
（来自情节记忆存储 EpisodicMemory）。实际记忆检索由上游
MemoryGateway / RetrievalAgent 完成，本技能负责声明回溯需求。

依赖数据库（requires_db=True）。

## 调用方式
- 参数: context (dict)，包含 diary_content、user_id、intent 等
- 返回: 记忆回溯触发标记字符串

## 输出示例
[memory_recall] 已触发记忆回溯，请在上下文中包含相关情节记忆。

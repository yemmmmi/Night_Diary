---
name: sentiment_skill
triggers: [难过, 焦虑, 开心, emotional_support]
priority: 1.2
category: analysis
token_cost_estimate: 150
---

# 情感分析技能

## 一句话摘要
调用 LLM 分析文本的情感倾向、强度和关键情感词。

## 触发条件
当用户 intent 为 emotional_support 时激活（分数 0.9）；或文本包含 2 个以上
情感关键词时激活（分数 0.85）；单个情感关键词时分数 0.7；
retrospective_review 意图下分数 0.6；长文本（>80 字）的 pure_record 分数 0.4。

支持的情感关键词包括：开心、难过、焦虑、生气、愤怒、伤心、高兴、烦躁、
压力、崩溃、抑郁、孤独、幸福、感动、失望、无聊、兴奋、紧张、害怕、
恐惧、羞愧、内疚、嫉妒、委屈、绝望、迷茫、疲惫、心累、释然、满足、感恩。

## 能力详述
通过注入的 LLM 客户端（LLMClient）对文本进行情感分析，输出三项结果：

1. 情感倾向：正面 / 负面 / 中性
2. 情感强度：1-5（1=很弱，5=很强）
3. 关键情感词：最多 5 个

该技能依赖 LLM（requires_network=True），若缺少 LLM 实例则返回降级提示。

## 调用方式
- 参数: text 或 context.diary_content (str)、context.llm (LLMClient)
- 返回: 格式化的情感分析结果文本

## 输出示例
情感倾向：负面
情感强度：4
关键情感词：委屈, 想哭, 无力

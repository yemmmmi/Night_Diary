# Skill-Call Accuracy Baseline (Progressive Disclosure A/B)

> 30 条标注用例（6 类）上双注入策略（FullInjection 全量注入 / ProgressiveDisclosure 摘要渐进式披露）的技能选择准确率基线，
> 供后续改动 SkillInjector / SkillDocLoader / SKILL.md 后对照，确认无明显退化。
> 数据集与标注见 `test_cases.json`（静态、人工标注）。

## 运行方式

```bash
# 1. 安装 eval 依赖（核心运行时不含）
cd server && pip install -e ".[dev,eval]"

# 2.（可选）真实模式：在 server/.env 配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
#    未配置时自动退化为 stub 模式（CI 友好，验证框架接线 + 解析管道）

# 3. 跑评估（输出双策略对比表 + 分类明细 + 失败样例）
make eval-skill

# 4. 首次/刻意刷新基线（写入 baseline.json，供回归对照）
EVAL_UPDATE_BASELINE=1 make eval-skill
```

## 双策略 A/B 设计

| 策略 | 注入内容 | LLM 声明方式 | 说明 |
|------|----------|-------------|------|
| full | `FullInjectionStrategy` — 注入每个技能的 `full_text`（完整文档） | LLM 阅读完整文档后声明 `<use_skill>name</use_skill>` | 全量注入，token 开销大但信息完整；LLM 拥有全部上下文做决策 |
| progressive | `ProgressiveDisclosureStrategy` — 仅注入每个技能的 `summary`（一句话摘要） | LLM 根据摘要声明 `<use_skill>name</use_skill>`，系统按需加载完整 `body` | 渐进式披露，初始 prompt 更精简（省 token），但 LLM 需从摘要推断是否需要某技能 |

> 两种策略均通过 `parse_use_skill_tags` 解析 `<use_skill>name</use_skill>` 标签，将声明集合与标注的 `expected_skills` 对比。
> progressive 路径的 `disclosure_rounds` = LLM 声明的技能数（每声明一个技能触发一次按需 body 加载）。
> stub 模式下两路径均为满分（oracle 输入 → 正确解析），仅用于证明解析管道与指标接线无误；
> 真实模式下才反映 LLM 从不同信息量中做技能选择的实际能力差异，是 token 节省 vs 准确率权衡的核心信号。

## 数据集（30 条 / 6 类）

| 类别 | 数量 | 说明 |
|------|------|------|
| emotional | 6 | 情绪表达 → 主要激活 sentiment_skill |
| crisis | 5 | 危机信号 → 激活 crisis_detector（部分同时激活 sentiment_skill） |
| retrospective | 6 | 回忆过往 → 激活 memory_recall（部分同时激活 sentiment_skill） |
| entity_query | 5 | 人物查询 → 激活 entity_tracker |
| multi_skill | 4 | 多技能同时激活（回溯+实体+情感等组合） |
| no_skill_casual | 4 | 闲聊，不应激活任何技能（测假阳性抑制） |

## 4 个技能

| 技能名 | 类别 | 说明 |
|--------|------|------|
| crisis_detector | analysis | 识别极端负面情绪并触发安全干预 |
| sentiment_skill | analysis | 调用 LLM 分析文本情感倾向和强度 |
| memory_recall | retrieval | 用户引用过往事件时检索相关情节记忆 |
| entity_tracker | memory | 用户提及具体人物时查询实体图关联信息 |

## 指标说明

### 选择准确率指标

| 指标 | 范围 | 含义 |
|------|------|------|
| skill_selection_accuracy | 0..1 | 预测技能集合与预期完全匹配的比例 |
| skill_selection_f1 | 0..1 | 集合级 F1（micro-averaged：P=TP/pred, R=TP/exp, F1=2PR/(P+R)） |
| false_activation_rate | 0..1 | 不该激活的技能中被误激活的比例（FP / should_not_activate） |
| missed_activation_rate | 0..1 | 该激活的技能中未激活的比例（FN / should_activate = 1 - recall） |

### 效率指标

| 指标 | 范围 | 含义 |
|------|------|------|
| avg_prompt_tokens | int | 每用例平均注入 prompt token 数 |
| avg_latency_ms | float | 每用例平均 LLM 往返延迟（毫秒） |
| avg_disclosure_rounds | float | 渐进式平均按需加载轮次（full 路径恒为 0） |
| token_savings | 0..1 | 1 - progressive_tokens / full_tokens（渐进式相对全量的 token 节省率） |

> 回归容差：单策略的 `skill_selection_accuracy` / `skill_selection_f1` 相对自身 baseline 下降 > `0.05`（绝对）判定为退化。
> 效率指标（tokens / latency / rounds）受环境影响较大，不参与回归判定，仅作 A/B 对比参考。

## Baseline 指标

> 记录日期：2026-07-06 · 环境：deepseek-v4-flash（REAL_MODE）

| 策略 | accuracy | f1 | FAR | MAR | avg_tok | avg_ms | rounds |
|------|----------|----|-----|-----|---------|--------|--------|
| full        | 0.8000 | 0.8857 | 0.0122 | 0.1842 | 2763.37 | 4538.86 | 0.00 |
| progressive | 0.6667 | 0.8308 | 0.0000 | 0.2895 |  678.90 | 3311.57 | 0.90 |

| token_savings |
|---------------|
| 75.43% |

> 渐进式披露节省 75.43% prompt token，但准确率从 0.80 降至 0.67（summary 信息不足以判断多 Skill 场景）。
> 全量注入的 MAR=0.18 表明 LLM 偶尔漏选 sentiment_skill（情绪场景应同时激活情感分析）。

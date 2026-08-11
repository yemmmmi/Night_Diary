# Chat-Intent Classification Baseline

> 250 条标注用例上双方案（Baseline A 规则层+通用 LLM / Treatment B 规则层+微调小模型）的意图分类基线，
> 供微调模型上线、调整规则层或替换 LLM 后对照，确认无明显退化。
> 数据集与标注见 `dataset/test_cases.json`（静态、人工标注，8 类意图；含 P2 新增 plan_exploration / task_command）。

## 运行方式

```bash
# 1. 安装 eval 依赖（核心运行时不含）
cd server && pip install -e ".[dev,eval]"

# 2.（可选）真实模式：在 server/.env 配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
#    未配置时自动退化为 stub 模式（CI 友好，验证框架接线 + A/B 对比接线）

# 3. 跑评估（输出 A/B 对比表 + per-class P/R/F1 + 8x8 混淆矩阵 + 分类明细 + 失败样例）
make eval-intent

# 4. 首次/刻意刷新基线（写入 baseline.json，供回归对照）
EVAL_UPDATE_BASELINE=1 make eval-intent
```

## 双方案设计

两个方案共享**同一个规则层**（`ChatIntentClassifier._rule_classify`，confidence > 0.9 短路，
零 token），仅在规则层未短路（confidence <= 0.9）时调用各自的 LLM 层。因此两方案的
`rule_short_circuit_rate` 与短路 case 划分**完全相同**，差异只来自 LLM 层对歧义/边界用例的纠偏能力。

| 方案 | LLM 层 | stub 模式行为 | 真实模式行为 |
|------|--------|---------------|--------------|
| **Baseline A** | 通用 LLM（当前生产配置） | `_RuleEchoStubLLM`：重跑规则层并原样回执（LLM 不纠偏），stub 下准确率 = 规则层准确率，仅验证框架接线 | `HttpLLM(temperature=0)`，反映通用大模型的真实意图判别能力，回归监控核心 |
| **Treatment B** | 微调小模型（暂用 stub 占位） | `StubFineTunedLLM`：按 gold 回执（oracle 占位），stub 下 `llm_layer_accuracy` 恒为 1.0，验证接线 + 标定上界 | 微调完成后替换 `treatment_b_llm` fixture 内部实现为真实微调客户端 |

> stub 模式下 Treatment B 为 oracle（满分），仅验证解析管道与指标接线无误；
> Baseline A 在 stub 模式下为规则回声（不纠偏），仅验证 LLM 层调用与度量接线。
> 真实 A/B 对比数值需在 REAL_MODE 下生成；首次 `EVAL_UPDATE_BASELINE=1` 后 `baseline.json` 的
> `_placeholder` 标记会被移除，回归测试随之生效。

## 数据集（250 条 / 8 类意图）

| 字段 | 说明 |
|------|------|
| `case_id` | 唯一标识（ic001..ic200 原始 6 类；p001..p025 plan_exploration；t001..t025 task_command） |
| `text` | 用户消息原文 |
| `gold_intent` | 人工标注的真实意图（8 类之一） |
| `rule_confidence` | 规则层给出的置信度 |
| `rule_short_circuits` | 规则层是否短路（confidence > 0.9） |
| `category` | 用例类别（clear_* / ambiguous_* / boundary_*） |
| `notes` | 标注说明 |

8 类意图：原始 6 类（`casual_chat` / `emotional_vent` / `retrospective_query` / `advice_seeking` /
`crisis_signal` / `entity_query`，各约 33 条）+ P2 新增 `plan_exploration`（25 条）/ `task_command`（25 条）。类别覆盖：

- `clear_*`：规则层高置信命中，短路
- `ambiguous_*`：规则层低置信（规则与 gold 一致但置信不足），需 LLM 层确认
- `boundary_*`：规则层判错（规则判 X，gold=Y），考验 LLM 层纠偏能力

## 指标说明

| 指标 | 范围 | 含义 |
|------|------|------|
| `accuracy` | 0..1 | 整体准确率（预测 == gold） |
| `macro_f1` | 0..1 | 8 类 F1 宏平均 |
| `weighted_f1` | 0..1 | 8 类 F1 按支持度加权平均 |
| `per_class_precision/recall/f1` | 0..1 | 每类 P/R/F1 |
| `confusion_matrix` | 8x8 int | 混淆矩阵（行=gold，列=predicted） |
| `rule_short_circuit_rate` | 0..1 | 规则层短路率（A/B 共享，规则层固有属性） |
| `llm_layer_accuracy` | 0..1 | 仅非短路 case 的准确率（衡量 LLM 层纠偏能力） |
| `avg_latency_ms` | float | 每用例平均分类延迟（含规则层，短路 case ~0） |
| `avg_tokens_per_call` | float | LLM 层平均 token 消耗（仅统计实际调用 LLM 的 case） |

> 回归容差：
> - 准确率类指标（`accuracy` / `macro_f1` / `weighted_f1` / `llm_layer_accuracy`）：相对自身 baseline 下降 > `0.05`（绝对）判定退化。
> - 成本类指标（`avg_latency_ms` / `avg_tokens_per_call`）：相对 baseline 上升 > `25%` 判定退化。
> - `rule_short_circuit_rate` 为规则层固有属性，不参与回归（由 `test_rule_short_circuit_matches_dataset` 单独守卫与数据集一致）。

## Baseline 指标

`baseline.json` 当前为 **stub 模式** 校准（250 条 / 8 类，数据集扩展后重新 seed），
供 CI / 本地无 `LLM_API_KEY` 时回归对照。REAL_MODE 数值需由运维在配置 `LLM_API_KEY` 后
重新 `EVAL_UPDATE_BASELINE=1 make eval-intent` 刷新（会覆盖下表）。

> stub seed · 250 cases / 8 intents（baseline_a = 规则回声占位；treatment_b = oracle 占位）

| 方案 | accuracy | macro_f1 | weighted_f1 | sc_rate | llm_acc | lat_ms | tok/call |
|------|----------|----------|-------------|---------|---------|--------|----------|
| baseline_a  | 0.6960 | 0.6968 | 0.7012 | 0.3040 | 0.5747 |   0.02 |  175.00 |
| treatment_b | 0.9920 | 0.9919 | 0.9920 | 0.3040 | 1.0000 |   0.04 |  112.00 |

> 历史 REAL_MODE 记录（200 条 / 6 类，2026-07-06，deepseek-v4-flash）：
> baseline_a accuracy=0.87 / llm_acc=0.83；treatment_b(oracle) accuracy=0.995。
> 数据集扩展到 250 条 / 8 类后该记录不再可直接对照，需在 250 条上重新跑 REAL_MODE 刷新。
>
> stub 解读：Baseline A（规则回声）accuracy=0.696；新意图 plan_exploration / task_command 的
> 边界 case（规则判为 casual_chat / advice_seeking）拉低了 recall（0.44 / 0.48），正是 LLM 层
> 需纠偏之处；Treatment B（oracle）非短路子集 llm_layer_accuracy=1.0，accuracy=0.992（2 条规则
> 高置信误判的短路 case 无法被 LLM 层挽救）。

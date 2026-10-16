# Skill-Routing Clarification Baseline (B4 Acceptance Gate)

> 31 条标注用例（7 类）上对生产意图路由器
> （`app/domain/skills/intent.py::classify_user_intent`）的**澄清决策**验收基线，
> 供后续改动路由规则 / 澄清阈值 / 路由器 prompt 后对照，确认无明显退化。
> 数据集与标注见 `test_cases.json`（静态、人工标注）。
>
> 这是 Hermes 调研 E2「把 eval 基线扩展为改进项验收闸门」为 B4
> （低置信度歧义澄清）挂载的离线闸门，已纳入 CI stub 闸门。

## 运行方式

```bash
# 1. 安装 eval 依赖（核心运行时不含）
cd server && pip install -e ".[dev,eval]"

# 2.（可选）真实模式：在 server/.env 配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
#    未配置时自动退化为 stub 模式（CI 友好，验证框架接线 + 澄清决策）

# 3. 跑评估（输出指标块 + 分类明细 + 误路由样例）
make eval-routing

# 4. 首次/刻意刷新基线（写入 baseline.json，供回归对照）
EVAL_UPDATE_BASELINE=1 make eval-routing
```

## 双模式设计

| 模式 | 路由器 LLM | 说明 |
|------|-----------|------|
| stub | `ProgrammableStubLLM` — 按 `用户输入：<text>` 锚点返回该用例标注的 `stub_intent` / `stub_confidence`（oracle 输入） | 确定性验证「路由规则 + 澄清决策」接线：oracle 输入下 `routing_accuracy` / `clarification_f1` 必为 1.0。CI 用它保证框架绿。 |
| real | `HttpLLM`（JSON 模式） | 真实模式下由 LLM 自身的 intent + `ambiguous` 决定是否澄清，是回归监控的核心信号。 |

> 澄清只在**弱信号 + LLM 源 + 倾向技能**且（`ambiguous=true` 或 旧契约下 `置信度 < 0.5`）时触发：
> 强规则 / 目标型计划句 / 手动选择永远可信；低置信 `chat` 静默走普通聊天（无写入风险，不打扰用户）。
> stub 模式下强规则 / 目标规则 / 无信号用例根本不咨询 LLM。
>
> 2026-10-16 起路由器 prompt 直接询问 `ambiguous`（「我拿不准该走技能还是普通聊天」），
> 不再只靠一个未校准的自报置信度推断歧义 —— 后者在弱信号歧义句上会给出 0.85/0.92 的
> 高置信，导致澄清闸门完全失效（见下方基线沿革）。
> 无 `ambiguous` 字段的旧回复自动回落到置信度启发式，stub oracle 与旧契约不受影响。

## 数据集（31 条 / 7 类）

| 类别 | 数量 | 期望结果 | 说明 |
|------|------|----------|------|
| ambiguous_skill | 6 | clarify | 弱信号 + 有无明确诉求对象说不清（模糊指代 / 随口说感受）→ 应澄清 |
| confident_skill | 6 | record/insight/plan | 弱信号 + LLM 高置信 → 直连技能 |
| low_conf_chat | 4 | chat | 弱信号但 LLM 判为 chat 且低置信 → 静默普通聊天，不澄清 |
| strong_rule | 6 | record/insight/plan | 强规则命中 → 零 LLM 直连 |
| goal_rule | 3 | plan | 数字目标 + 坚持/打算/计划 → 零 LLM 直连 plan |
| no_signal_chat | 4 | chat | 无弱信号 → 默认 chat，零 LLM |
| empty | 2 | chat | 空 / 纯空白输入 → 默认 chat |

## 指标说明

| 指标 | 范围 | 含义 |
|------|------|------|
| routing_accuracy | 0..1 | 预测结果与期望在 5 值空间（clarify/record/insight/plan/chat）完全匹配的比例 |
| clarification_precision | 0..1 | 澄清的用例中确实需要澄清的比例（TP / (TP+FP)） |
| clarification_recall | 0..1 | 需要澄清的用例中被澄清的比例（TP / (TP+FN)） |
| clarification_f1 | 0..1 | 上两者调和平均 |
| false_clarification_rate | 0..1 | 不该澄清却打断用户的比例（过度询问，FP / should_not_clarify） |
| missed_clarification_rate | 0..1 | 该澄清却静默猜的比例（询问不足，FN / should_clarify） |
| avg_latency_ms | float | 每用例平均路由耗时（规则 + LLM） |
| avg_tokens_per_call | int | 实际调用路由器 LLM 的用例平均 token 消耗 |

> 回归容差：`routing_accuracy` / `clarification_f1` 相对自身 baseline 下降 > `0.05`（绝对）判定为退化；
> `false_clarification_rate` 上升 > `0.05`（绝对）同样判定为退化。
> 效率指标（latency / tokens）受环境影响较大，不参与回归判定，仅作参考。

## Baseline 指标

> 记录日期：2026-10-16（含歧义显式化改造） · 模式：real · 环境：deepseek-v4.1-flash-d（31 例）

| routing_acc | clr_P | clr_R | clr_F1 | false_clr | miss_clr | avg_tok |
|-------------|-------|-------|--------|-----------|----------|---------|
| 0.8710 | 0.7500 | 0.5000 | 0.6000 | 0.0400 | 0.5000 | 740.69 |

> 沿革：同日早先的 real 基线为 `routing_acc 0.8387 / clr_P 1.0 / clr_R 0.1667 / clr_F1 0.2857 /
> false_clr 0.0 / miss_clr 0.8333`。该基线暴露的真实短板是 `ambiguous_skill` 6 例**只有 1 例澄清**
> —— 弱信号歧义句上 LLM 自报置信度严重高估（0.85 / 0.92 / 0.60），澄清闸门基本失效；旧的
> stub-oracle 基线（质量指标恒 1.0/0.0）完全掩盖了这一点。
>
> 改造后召回由 0.1667 → 0.5000（F1 0.2857 → 0.6000，routing_acc 0.8387 → 0.8710），
> 代价是 `false_clarification_rate` 0.0 → 0.04（仍在 0.05 容差内）与效率指标上升
> （latency 819→1115ms、tokens 584→741；prompt 变长，效率指标不参与回归判定）。

> ⚠️ 残留失配（非闸门失败，供后续判断）：
> - `sr_amb_01/02/05` 模型仍判为 `chat`（「帮我看看这段」「我想聊聊最近的事」「最近压力有点大」）
>   → 未澄清。其中 amb_05 是 `src=default`（路由器 LLM 空回复降级），提示端点偶发空回复的既有问题。
>   这三条与 `low_conf_chat`（「有点烦」「我想静静」）在**语义上几乎不可分**（皆为模糊/随口一句），
>   却分属相反期望，说明该类标注在细粒度上不稳定；不要在 prompt 上继续过拟合这 3 条。
> - `sr_conf_04`（「我最近情绪起伏好大」）被模型认为歧义而澄清，即上面 0.04 的 FP 来源。

> 历史记录（2026-10-11 · stub_oracle 占位）：质量指标恒 1.0 / 0.0，仅证明接线正确，不是回归下限。
> ⚠️ 该套件此前**既不在** `run_real_eval_quality_gates.sh` 的运行清单、**也不在**重播种清单里，
> 真实基线从未入仓；2026-10-16 起两条清单均已补入。

# MCP Decision Eval Baseline

该评估固定 12 个场景，覆盖三类决策：

- `call_required`：确实需要外部实时或账户数据，应调用 MCP 工具。
- `no_call`：闲聊、改写或明确要求不检索，不应调用工具。
- `tool_selection`：多个 MCP 工具同时可用，必须选中正确工具；测试另行注入错误工具，确认指标能识别“调了但选错”。

## 两种模式

| 模式 | 触发条件 | 作用 |
|------|----------|------|
| **stub-oracle**（CI 默认） | 未设 `MCP_DECISION_REAL=1` | 把人工标注编码成工具调用，验证 dataset / native 提取 / `<tool>` 文本协议解析 / 指标接线。分数恒为满分，**不代表模型质量** |
| **real** | `MCP_DECISION_REAL=1` + `LLM_API_KEY` | 模型真实决策：该不该调、调哪个、参数对不对 |

`baseline.json` 的 `_mode` 字段声明它记录的是哪一种；`test_baseline_declares_mode_and_metadata` 保证这个声明不会悄悄漂移。

## 当前基线（real）

> 记录：2026-09-14 · deepseek-v4-flash · 12 例 · `temperature=0.0`

| 指标 | 值 | 说明 |
|------|-----|------|
| decision_accuracy | **0.9167** | 11/12 正确判断“该不该调用” |
| false_positive_rate | **0.0** | 没有把不该调的场景误调用（对照本地工具的 native 协议 FPR 0.60） |
| false_negative_rate | 0.125 | 1 例该调未调 |
| tool_name_accuracy | 0.75 | 决定调用时选错工具名的情况明显 |
| argument_accuracy | 0.625 | **当前最大短板：参数填错** |
| exact_match | **0.75** | 决策 + 工具名 + 参数全对的整体通过率 |
| parse_success_rate | 1.0 | 协议解析稳定 |

同一套 12 例在不同运行中 `exact_match` 出现过 **0.6667 / 0.75**（2026-09-14 两次复跑分别得到两个值，后者与 v4.1 报告记录的 0.75 一致），
所以**回归容差取 0.15**：`test_no_regression_vs_baseline` 只在 real 模式下比对，且只拦“明显退步”，不把波动当退化。

## 重播种

```powershell
$env:MCP_DECISION_REAL = "1"     # real 模式
$env:EVAL_UPDATE_BASELINE = "1"  # 允许覆盖 baseline.json
pytest tests/eval/mcp_decision -m eval -q -s
```

`EVAL_UPDATE_BASELINE=1` 只在 real 模式下写入；stub 运行永远不会覆盖 real 基线。
容器口径见 `server/scripts/run_real_eval_quality_gates.sh`（`baseline_dirs` 已包含本目录）。

## CI 命令

```bash
pytest tests/eval/mcp_decision -m eval -q
```

CI 无 `LLM_API_KEY`，跑 stub-oracle 路径：校验接线，`test_no_regression_vs_baseline` 自动 skip（real 基线不与 stub 分数比较）。

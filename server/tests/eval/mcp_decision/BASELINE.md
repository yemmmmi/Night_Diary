# MCP Decision Eval Baseline

该评估固定 12 个场景，覆盖三类决策：

- `call_required`：确实需要外部实时或账户数据，应调用 MCP 工具。
- `no_call`：闲聊、改写或明确要求不检索，不应调用工具。
- `tool_selection`：多个 MCP 工具同时可用，必须选中正确工具；测试另行注入错误工具，确认指标能识别“调了但选错”。

## CI / stub 模式

默认运行 deterministic stub oracle。它把人工标注编码为工具调用，再经过：

1. native `tool_calls` 提取；
2. fallback `<tool>/<args>` 解析；
3. `tests/eval/tool_call/metrics.py` 的公共决策、工具名、参数和 exact 指标。

`baseline.json` 带有 `"_placeholder": true`。其中满分只证明 dataset、harness、解析器和指标接线正确，**不是模型的真实 MCP 决策质量，也不得作为质量基线引用**。

## 可选真实模式

显式设置以下环境变量后，可让 model path 调用 OpenAI-compatible 接口：

```powershell
$env:MCP_DECISION_REAL = "1"
$env:LLM_API_KEY = "..."
pytest tests/eval/mcp_decision -m eval -q -s
```

真实模式会打印模型指标；在积累经人工复核的结果并移除 placeholder 前，不做真实质量回归断言，也不会自动覆盖 `baseline.json`。

## CI 命令

```bash
pytest tests/eval/mcp_decision -m eval -q
```

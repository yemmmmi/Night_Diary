# Tool-Call Accuracy Baseline

> 40 条标注用例（7 类）上双协议路径（native 函数调用 / fallback 文本标签解析）的工具调用准确率基线，
> 供后续改动工具协议、ToolSpec 或 prompt 后对照，确认无明显退化。
> 数据集与标注见 `test_cases.json`（静态、人工标注）。

## 运行方式

```bash
# 1. 安装 eval 依赖（核心运行时不含）
cd server && pip install -e ".[dev,eval]"

# 2.（可选）真实模式：在 server/.env 配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
#    未配置时自动退化为 stub 模式（CI 友好，验证框架接线 + 解析管道）

# 3. 跑评估（输出双路径对比表 + 分类明细 + 失败样例）
make eval-tool

# 4. 首次/刻意刷新基线（写入 baseline.json，供回归对照）
EVAL_UPDATE_BASELINE=1 make eval-tool
```

## 协议双路径设计

| 路径 | LLM | 解析方式 | 说明 |
|------|-----|----------|------|
| native | `HttpLLM.bind_tools`（真实）/ `ProgrammableStubLLM.bind_tools`（stub） | `extract_native_tool_calls` 读取 `tool_calls` | 真实模式下衡量 LLM 原生函数调用准确率；stub 模式下复用 fallback 的文本标签响应转 `tool_calls`，保持 CI 绿 |
| fallback | `ProgrammableStubLLM`（始终 stub，返回预设 `<tool>` 标签） | `parse_text_tag_calls` 解析 `<tool>name</tool><args>json</args>` | 验证文本标签解析管道 `parse_text_tag_calls` 正确性（stub 模式下必为 1.0） |

> fallback 路径在 stub 模式下必为满分（oracle 输入 → 正确解析），仅用于证明解析管道与指标接线无误；
> native 路径在真实模式下才反映 LLM 的真实工具调用能力，是回归监控的核心。

## 数据集（40 条 / 7 类）

| 类别 | 数量 | 说明 |
|------|------|------|
| single_tool_keyword | 8 | 关键词明确触发单个工具 |
| single_tool_semantic | 6 | 需语义理解才能映射到工具 |
| multi_tool | 6 | 一轮并行调用多个工具 |
| no_tool_casual | 6 | 闲聊，不应调用工具（测假阳性抑制） |
| no_tool_emotional | 6 | 情绪表达，应共情而非调用工具 |
| args_edge | 4 | 参数边界：模糊词 / 日期范围 / 整数参数 / 极短文本 |
| ambiguous | 4 | 歧义输入，考察克制能力 |

## 指标说明

| 指标 | 范围 | 含义 |
|------|------|------|
| decision_accuracy | 0..1 | 是否正确决定调用/不调用工具 |
| tool_name_accuracy | 0..1 | 应调用用例中工具名集合 Jaccard 相似度 |
| argument_accuracy | 0..1 | 应调用用例中参数满足率（必填项存在 + 期望值匹配） |
| exact_match | 0..1 | 决策 + 工具名 + 参数全部正确 |
| false_positive_rate | 0..1 | 不应调用却调用（按 no-tool 用例计） |
| false_negative_rate | 0..1 | 应调用却未调用（按 tool 用例计） |
| parse_success_rate | 0..1 | fallback 专用：`<args>` 是否为合法 JSON |
| avg_tool_count | float | 每用例平均工具调用数 |

> 回归容差：单路径相对自身 baseline 下降 > `0.05`（绝对）判定为退化（`avg_tool_count` 不参与回归）。

## Baseline 指标

> 记录日期：2026-07-06 · 环境：deepseek-v4-flash（REAL_MODE）

| 路径 | decision | name_acc | arg_acc | exact | FPR | FNR | parse | avg_cnt |
|------|----------|----------|---------|-------|-----|-----|-------|---------|
| native   | 0.7500 | 0.9000 | 0.8800 | 0.6750 | 0.6000 | 0.0400 | 1.0000 | 1.2500 |
| fallback | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 0.7750 |

> fallback 在 stub 模式下恒为满分（oracle 输入），仅验证解析管道。
> native 真实模式下 exact_match=0.675，主要失败在 no_tool_emotional 类（LLM 倾向过度调用工具，FPR=0.6）。

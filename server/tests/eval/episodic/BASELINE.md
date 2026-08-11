# 情景记忆检索离线评估 — Baseline

> 固定语料（36 条情景记忆条目 × 20 条查询，4 类各 5 条）上三种检索方案的基线指标，
> 供后续改动 EpisodicMemory 向量化 / rerank / decay 后对照，确认无明显退化。
> 数据集与标注见 `episodic_entries.json` / `test_cases.json`（静态、人工合成）。

## 运行方式

```bash
# 1. 安装 eval 依赖（核心运行时不含；sentence-transformers 提供 embedding + CrossEncoder）
cd server && pip install -e ".[dev,eval]"

# 2. 国内网络需配置 HuggingFace 镜像（首次会下载模型）
#    embedding: BAAI/bge-small-zh-v1.5 (~95MB)
#    reranker : BAAI/bge-reranker-base (~1.1GB)
export HF_ENDPOINT=https://hf-mirror.com   # PowerShell: $env:HF_ENDPOINT="https://hf-mirror.com"

# 3. 跑评估（输出三路对比表 + 分类 Recall@5 + 失败样例）
make eval-episodic

# 4. 首次/刻意刷新基线（写入 baseline.json，供回归对照）
EVAL_UPDATE_BASELINE=1 make eval-episodic
```

> 未安装 `sentence-transformers` 时自动进入 **stub 模式**：vector 分支用 `StubEmbedder`
> （确定性 SHA-256，无语义），rerank 分支跳过。stub 模式仅验证框架接线，其数值**不是**
> 检索质量契约——真实模式（BGE）才是验证 P4 向量化收益的依据。

## 三路分支设计

三路都跑**生产** `EpisodicMemory.retrieve_relevant`（importance×decay 粗排 → 精排 → 可选 rerank），
仅通过注入不同的 `embedder` / `reranker` 切换精排阶段：

| 分支 | embedder | reranker | 精排策略 | 说明 |
|------|----------|----------|----------|------|
| jaccard | `None` | `None` | `char_jaccard` | V1 等价单阶段；字符级重叠，关键词友好、语义天然偏弱 |
| vector | `BgeEmbedder`（真实）/ `StubEmbedder`（stub） | `None` | 向量余弦 | 两阶段：importance×decay 粗排 → BGE 向量精排 |
| vector_rerank | 同 vector | `Reranker`（bge-reranker-base） | 向量 + CrossEncoder | 三阶段完整管线；模型不可用时跳过 |

> 三路共享**同一份**语料（session-scoped fixture）与**固定** `now`（import 时锁定），
> 因此 `importance × decay` 在每次运行中完全确定，无时间漂移。
> 数据集的 `timestamp_offset_days`（负值=过去）在加载时转为绝对 `timestamp = now + offset×86400`。

## 数据集（36 条语料 / 20 条查询 / 4 类）

| 类别 | 查询数 | 设计意图 |
|------|--------|----------|
| keyword  | 5 | 查询词与 gold 的 `event_summary` 共享字符（jaccard 友好） |
| semantic | 5 | 查询刻意避开表层词（如「整夜翻来覆去」→「失眠」），jaccard 应失败 |
| emotion  | 5 | 模糊情绪查询，gold 为多条同情绪条目 |
| time     | 5 | 近因查询（「最近…」「今天…」），gold 为 offset≤-1 的高分近条目 |

## 指标说明

| 指标 | 范围 | 含义 |
|------|------|------|
| Recall@5 | 0..1 | top-5 命中 gold 的比例（二值相关，entry-id 粒度） |
| MRR      | 0..1 | 第一个命中 gold 的倒数排名 |
| nDCG@5   | 0..1 | 位置折损累计增益（相关条目越靠前越高） |

> 指标函数从 `tests/eval/rag/test_eval_retrieval.py` 逐字复制到 `metrics.py`，
> 与 RAG 检索 eval 保持同一套 Recall@5 / MRR / nDCG@5 口径。
> 回归容差：单分支相对自身 baseline 下降 > `0.05`（绝对）判定为退化。

## Baseline 指标

> 记录日期：2026-08-11 · 环境：stub 模式（无 `sentence-transformers`，StubEmbedder）

| 分支 | Recall@5 | MRR | nDCG@5 | 状态 |
|------|----------|-----|--------|------|
| jaccard       | 0.4983 | 0.5417 | 0.4911 | placeholder（stub） |
| vector        | 0.2317 | 0.2625 | 0.2220 | placeholder（stub，无语义） |
| vector_rerank |  —     |  —     |  —     | SKIPPED（stub 模式无 CrossEncoder） |

> **`_placeholder: true`**：当前 baseline 由 stub 模式生成，仅证明框架接线正确，**不参与回归检查**
> （`test_no_regression_vs_baseline` 检测到 placeholder 会自动 skip）。请在真实模式下重新 seed：
> `pip install -e ".[eval]"` 后 `EVAL_UPDATE_BASELINE=1 make eval-episodic`，届时写入
> `_placeholder: false` 并启用回归守护。

### 分类 Recall@5（stub 模式，诊断用，不参与回归）

| 类别     | jaccard | vector(stub) |
|----------|---------|--------------|
| keyword  | 1.0000  | 0.0000 |
| semantic | 0.0000  | 0.0000 |
| emotion  | 0.2933  | 0.2267 |
| time     | 0.7000  | 0.7000 |

## 指标解读（stub 模式，趋势对照用，非硬断言）

- **jaccard 在 keyword 上 Recall@5 = 1.0**：查询词与 `event_summary` 字符完全重叠（如「失眠」→e01），
  验证 `char_jaccard` 在表层匹配上的有效性。
- **jaccard 在 semantic 上 Recall@5 = 0.0**：5 条语义查询与 gold 无共享字符
  （如「整夜翻来覆去」↔「失眠」、「工作负荷太重」↔「加班」），全部失败——这正是数据集刻意暴露的
  `char_jaccard` 短板，预期由真实模式的 BGE 向量分支救回。
- **vector(stub) 全面弱于 jaccard（0.23 vs 0.50）**：`StubEmbedder` 是 SHA-256 哈希，无语义，
  「相似度」≈随机噪声，精排退化为 importance×decay 的近因排序（top5 恒为 e18/e03/e08/e17/e25 等
  高分近条目）。**这是预期的**——真实模式（BGE）才会体现语义增益。
- **不写硬断言**：stub 模式下不强求「vector 必然优于 jaccard」。真实模式 baseline 落地后，
  回归测试只对比单分支相对自身 baseline 的明显下降；明显退化须在 PR 中解释或修复。

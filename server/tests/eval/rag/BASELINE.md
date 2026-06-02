# RAG 检索离线评估 — Baseline

> 固定语料（30 条中文日记 × 20 条查询）上四种检索方案的基线指标，供后续
> B-5 / B-8 / B-10 改动 prompt / chunk / rerank 后对照，确认无明显退化。
> 数据集与标注见 `diaries.json` / `test_cases.json` / `test_cases.md`（静态、不可运行时生成）。

## 运行方式

```bash
# 1. 安装重依赖（仅 eval 需要，核心运行时不含）
pip install -e ".[dev,eval]"

# 2. 国内网络需配置 HuggingFace 镜像（首次会下载模型）
#    embedding: BAAI/bge-small-zh-v1.5 (~95MB)
#    reranker : BAAI/bge-reranker-base (~1.1GB)
export HF_ENDPOINT=https://hf-mirror.com   # PowerShell: $env:HF_ENDPOINT="https://hf-mirror.com"

# 3. 跑评估（输出对比表 + 失败样例）
make eval-rag

# 4. 首次/刻意刷新基线（写入 baseline.json，供回归对照）
EVAL_UPDATE_BASELINE=1 make eval-rag
```

> 模型缓存默认在 `~/.cache/huggingface`。评估代码不写任何全局环境变量；镜像/缓存均由运行环境提供。

## 模型与配置（可复现性）

| 项 | 值 |
|----|----|
| Embedding 模型 | `BAAI/bge-small-zh-v1.5`（24M，512 维，C-MTEB 检索口碑好的最小中文模型） |
| Embedding 注入方式 | `Settings.embedding_model_name` → `app.shared.embeddings.build_embedding_function` → DI 注入 `DiaryCollectionManager`（不硬编码、不裸读 env） |
| Reranker 模型 | `BAAI/bge-reranker-base`（`Reranker` 默认，CrossEncoder） |
| BGE query 指令前缀 | **不加**。BGE 官方建议 query 侧加「为这个句子生成表示以用于检索相关文章：」，但 `SentenceTransformerEmbeddingFunction` 不会自动加，production 也不会加；为保持 eval 与 production 行为一致，统一不加。若日后实验证明不加导致 Recall 显著下降（>5%），再单独开 PR 在 query 上游统一处理。 |
| 分词 | jieba，丢弃单字 token（`len >= 2`） |
| Chunk | `ChunkSplitter` 默认参数（chunk_size=512, overlap=50, min=128）；BM25 与向量库共用同一 splitter |
| 指标 K | `FINAL_K = 5`（Recall@5 / MRR / nDCG@5） |
| 融合 | Reciprocal Rank Fusion，`k=60` |
| 回归容差 | 单分支相对自身 baseline 下降 > `0.05`（绝对）判定为退化 |

## Baseline 指标

> 记录日期：2026-06-02 · 环境：Windows / Python 3.11.7

| 方案 | Recall@5 | MRR | nDCG@5 | 状态 |
|------|----------|-----|--------|------|
| BM25-only      | 0.6667 | 0.7500 | 0.6596 | ✅ 已记录 |
| 向量-only       | — | — | — | ⏳ 待首次完整运行填入 |
| 混合 RRF        | — | — | — | ⏳ 待首次完整运行填入 |
| 混合 + Rerank   | — | — | — | ⏳ 待首次完整运行填入 |

> **为何向量/混合三行暂缺**：本基线在开发机上无法跑模型分支——该机的 `chromadb`
> 因 `onnxruntime` DLL 初始化失败而无法导入，且未安装 `sentence-transformers`。
> 评估框架已按设计**显式跳过**这三条分支（而非记录降级数字污染基线）。请在
> 满足上方"运行方式"前置条件的机器上执行 `EVAL_UPDATE_BASELINE=1 make eval-rag`，
> 它会把四个分支的真实指标写入 `baseline.json`；随后将本表的三行补齐即可。

## 指标解读（小样本，趋势对照用，非硬断言）

- 本数据集刻意让**关键词查询**与 gold 共享表层词（BM25 友好），**语义查询**避开表层词（依赖向量）。因此 BM25-only 在语义查询上天然偏弱属预期。
- BM25-only 当前漏检的失败样例集中在语义/复合意图：
  - `q06` 「和家里人发生了矛盾」→ d05（用"吵架/争执"，无"矛盾"）：BM25 top5 为空。
  - `q08` 「独自在异乡感到寂寞」→ d19（用"孤独/一个人"）：BM25 top5 为空。
  - `q09` 「运动锻炼让人精神变好」→ d03/d04：BM25 仅命中无关项。
  - `q18` 「出去旅行看风景放松心情」→ d11/d12：BM25 召回错误日记。
  - 这些正是向量 / 混合分支应当救回的样本，可在补齐三行后验证融合的增益。
- **不写硬断言**：小语料上不强求"混合必然优于单路""rerank 必然提升 MRR"。回归测试只对比单分支相对自身 baseline 的明显下降；明显退化须在 PR 中解释或修复。

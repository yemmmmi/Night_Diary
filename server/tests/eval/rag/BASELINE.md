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
| Embedding 模型（当前） | Qwen `text-embedding-v3`（云端，`EMBEDDING_API_KEY` 存在时 `build_embedding_function` 优先走 `ApiEmbedder`） |
| Embedding 模型（降级） | `BAAI/bge-small-zh-v1.5`（24M，512 维；无 key 或云端不可用时回退本地） |
| Embedding 注入方式 | `Settings.embedding_model_name` → `app.shared.embeddings.build_embedding_function` → DI 注入 `DiaryCollectionManager`（不硬编码、不裸读 env） |
| Reranker 模型（当前） | 云端 `qwen3-rerank`（`RERANK_API_KEY`，为空时复用 `EMBEDDING_API_KEY`） |
| Reranker 模型（降级） | `BAAI/bge-reranker-base`（CrossEncoder） |
| BGE query 指令前缀 | **不加**。BGE 官方建议 query 侧加「为这个句子生成表示以用于检索相关文章：」，但 `SentenceTransformerEmbeddingFunction` 不会自动加，production 也不会加；为保持 eval 与 production 行为一致，统一不加。若日后实验证明不加导致 Recall 显著下降（>5%），再单独开 PR 在 query 上游统一处理。 |
| 分词 | jieba，丢弃单字 token（`len >= 2`） |
| Chunk | `ChunkSplitter` 默认参数（chunk_size=512, overlap=50, min=128）；BM25 与向量库共用同一 splitter |
| 指标 K | `FINAL_K = 5`（Recall@5 / MRR / nDCG@5） |
| 融合 | Reciprocal Rank Fusion，`k=60` |
| 回归容差 | 单分支相对自身 baseline 下降 > `0.05`（绝对）判定为退化 |

> **云端跑法（本地复现 2026-09-14 基线）**：`EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` 位于**仓库根 `.env`**（由 docker compose 注入容器）。直接在本机 `server/` 下跑 pytest 时 pydantic 只读 `server/.env`，请先把这三个键注入进程环境，例如：
> `Get-Content ..\.env | Where-Object { $_ -match '^(EMBEDDING_|RERANK_)' } | ForEach-Object { $i=$_.IndexOf('='); Set-Item -Path ("env:"+$_.Substring(0,$i).Trim()) -Value $_.Substring($i+1).Trim() }`
> 未注入时向量/融合/重排三个分支会 `SKIPPED`（只报 BM25），不会被记成退化数字。

## Baseline 指标

### 当前 baseline（云端 REAL）

> 记录日期：2026-09-14 · 环境：Windows / Python 3.11 / Qwen `text-embedding-v3` + `qwen3-rerank` · 30 文档 × 20 查询
> 与 `baseline.json` 一致；CI 无云端 key，只跑 BM25 分支并与其中 `bm25` 项对照。

| 方案 | Recall@5 | MRR | nDCG@5 | 状态 |
|------|----------|-----|--------|------|
| BM25-only      | 0.6667 | 0.7500 | 0.6596 | ✅ 已记录 |
| 向量-only       | 0.9667 | 1.0000 | 0.9688 | ✅ 已记录 |
| 混合 RRF        | 0.9500 | 0.9125 | 0.9041 | ✅ 已记录 |
| 混合 + Rerank   | 0.9667 | 0.9500 | 0.9283 | ✅ 已记录 |

> 同一份固定集在 2026-09-09 与 2026-09-14 两次云端运行得到逐位相同的结果（embedding / 检索是确定性的），
> 说明这组数字可复现；它仍只是**该固定集上的策略取舍**，不外推线上质量。

### 历史快照（本地 BGE，2026-06-02）

> 记录日期：2026-06-02 · 环境：Windows / Python 3.11.7 / bge-small-zh-v1.5 / bge-reranker-base

| 方案 | Recall@5 | MRR | nDCG@5 | 状态 |
|------|----------|-----|--------|------|
| BM25-only      | 0.6667 | 0.7500 | 0.6596 | 历史记录 |
| 向量-only       | 0.9833 | 0.9000 | 0.9199 | 历史记录 |
| 混合 RRF        | 0.9667 | 0.8875 | 0.8839 | 历史记录 |
| 混合 + Rerank   | 0.9083 | 1.0000 | 0.9151 | 历史记录 |

> 本地 BGE 与云端 Qwen 的差别是**排序形态**不同：BGE 向量单路 Recall 更高但 MRR 只有 0.90，
> Qwen 向量单路 MRR 达 1.00；重排后两者都收敛到 Recall 0.91–0.97。换言之，向量模型换云端不是单纯"变好"，
> 而是把"召回更多"换成"首位更准"——选型要按下游读法决定。
> 混合 RRF 的 Recall 略低于向量-only（0.950 vs 0.967），系小语料上 BM25 引入噪音所致——预期在更大语料上融合增益会体现。

## 指标解读（小样本，趋势对照用，非硬断言）

- 本数据集刻意让**关键词查询**与 gold 共享表层词（BM25 友好），**语义查询**避开表层词（依赖向量）。因此 BM25-only 在语义查询上天然偏弱属预期。
- BM25-only 当前漏检的失败样例集中在语义/复合意图：
  - `q06` 「和家里人发生了矛盾」→ d05（用"吵架/争执"，无"矛盾"）：BM25 top5 为空。
  - `q08` 「独自在异乡感到寂寞」→ d19（用"孤独/一个人"）：BM25 top5 为空。
  - `q09` 「运动锻炼让人精神变好」→ d03/d04：BM25 仅命中无关项。
  - `q18` 「出去旅行看风景放松心情」→ d11/d12：BM25 召回错误日记。
  - 这些 BM25 失败样本已被向量/混合/rerank 分支全部救回（q06/q08/q09/q18 在三个模型分支上 Recall 均达 1.0，Failure samples 输出中零模型分支条目），验证了中文 embedding 模型对语义/复合查询的有效性。
- **不写硬断言**：小语料上不强求"混合必然优于单路""rerank 必然提升 MRR"。回归测试只对比单分支相对自身 baseline 的明显下降；明显退化须在 PR 中解释或修复。

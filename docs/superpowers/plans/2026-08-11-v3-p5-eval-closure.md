# V3 P5: 评估闭环补全 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补全评估闭环——episodic 检索 eval(验证 P4)+ 规划质量 rubric + 性能探针 + CI eval gate + 真实 tokenizer + Thompson 死代码清理。

**Architecture:** 三阶段:(1) 评估套件(episodic/plan/intent); (2) 可观测性(/dev/stats/performance); (3) CI 与工具链(eval gate + tokenizer + 清理)。

**Tech Stack:** Python 3.11 / pytest / FastAPI / SQLAlchemy / sentence-transformers / Vue 3

**Spec:** `docs/superpowers/specs/2026-08-11-v3-p5-eval-closure.md`

---

## 文件结构

### 第一阶段:评估套件
| 文件 | 改动 |
|------|------|
| `server/tests/eval/episodic/` (新建) | conftest + test + baseline + 数据集 |
| `server/tests/eval/plan/` (新建) | conftest + test + baseline + 数据集 |
| `server/tests/eval/intent/dataset/test_cases.json` | 追加新意图标注 |
| `server/tests/eval/intent/baseline.json` | 刷新基线 |
| `server/Makefile` | 加 eval-episodic / eval-plan 目标 |

### 第二阶段:可观测性
| 文件 | 改动 |
|------|------|
| `server/app/api/v1/dev.py` | 新增 `/stats/performance` 端点 |
| `server/app/services/performance_stats_service.py` (新建) | p50/p95 + span flatten + bottleneck |
| `server/tests/unit/test_performance_stats.py` (新建) | 指标计算测试 |

### 第三阶段:CI 与工具链
| 文件 | 改动 |
|------|------|
| `.github/workflows/ci.yml` | 加 eval gate step |
| `server/app/shared/token_utils.py` | tokenizer 升级 |
| `server/app/shared/tracing_llm.py` | 流式路径接入 tokenizer |
| `server/app/domain/feedback/` (删除) | Thompson Sampling 清理 |
| `server/app/services/container.py` | 移除 thompson 注入 |

---

## 第一阶段:评估套件(Task 1-6)

## Task 1: Episodic eval 数据集

**Files:**
- Create: `server/tests/eval/episodic/episodic_entries.json`
- Create: `server/tests/eval/episodic/test_cases.json`

- [ ] **Step 1: 阅读现有 RAG eval 数据集格式**

阅读 `server/tests/eval/rag/diaries.json` 和 `server/tests/eval/rag/test_cases.json`,理解数据格式和标注模式。

- [ ] **Step 2: 阅读 EpisodicEntry 结构**

阅读 `server/app/domain/memory/types.py` 的 `EpisodicEntry`,确认所有字段。

- [ ] **Step 3: 创建 episodic_entries.json**

创建 `server/tests/eval/episodic/episodic_entries.json`,约 30-40 条合成语料,覆盖常见夜记场景:失眠、加班、社交焦虑、家庭矛盾、工作压力、情绪低落、习惯养成等。每条含 entry_id / event_summary / emotion / importance / tags / mood_score / timestamp_offset_days。importance 需 > 0.5。

- [ ] **Step 4: 创建 test_cases.json**

创建 `server/tests/eval/episodic/test_cases.json`,约 15-20 条标注查询,覆盖 4 类:
- `keyword`——字符重叠(jaccard 能命中,如"失眠"→"失眠")
- `semantic`——语义相同但字符不同(jaccard 失败,如"睡不着觉"→"失眠")
- `emotion`——情绪关联(如"很焦虑"→"失眠"+"加班")
- `time`——时间衰减验证

每条含 query_id / query / category / relevant_entry_ids。

- [ ] **Step 5: 提交**

```
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/tests/eval/episodic/
& 'C:\Program Files\Git\cmd\git.exe' commit -m "data(eval): add episodic retrieval eval dataset

30+ synthetic EpisodicEntry corpus + 15-20 annotated queries across 4
categories (keyword/semantic/emotion/time). Semantic cases validate P4
vectorization improvement over char_jaccard."
```

---

## Task 2: Episodic eval conftest + 3 分支

**Files:**
- Create: `server/tests/eval/episodic/__init__.py`
- Create: `server/tests/eval/episodic/conftest.py`
- Create: `server/tests/eval/episodic/test_eval_episodic.py`

- [ ] **Step 1: 阅读 RAG eval conftest 和 metrics**

阅读 `server/tests/eval/rag/conftest.py` 和 `server/tests/eval/rag/test_eval_retrieval.py`,理解:
- 数据加载 fixture
- `_build_branches` 模式(构建多个检索分支)
- recall_at_k / reciprocal_rank / ndcg_at_k 纯函数

- [ ] **Step 2: 创建 conftest.py**

构建 3 个 EpisodicMemory 实例的 fixture:
- `jaccard_memory`——embedder=None, reranker=None
- `vector_memory`——embedder=BgeEmbedder/StubEmbedder, reranker=None
- `vector_rerank_memory`——embedder=BgeEmbedder/StubEmbedder, reranker=Reranker

从 episodic_entries.json 加载 entry,注意 timestamp 用 `now + offset_days * 86400` 固定时间。

- [ ] **Step 3: 创建 test_eval_episodic.py**

复用 RAG eval 的 metrics(recall@5 / MRR / nDCG@5),对 3 分支分别跑全部 test_cases,聚合指标。退化检查对比 baseline.json。

- [ ] **Step 4: 提交**

---

## Task 3: Episodic eval baseline + 运行验证

**Files:**
- Create: `server/tests/eval/episodic/baseline.json`
- Create: `server/tests/eval/episodic/BASELINE.md`
- Modify: `server/Makefile`(加 eval-episodic 目标)

- [ ] **Step 1: 运行 episodic eval(stub mode)**

```
cd d:\work\night_diary_v2\server
EVAL_UPDATE_BASELINE=1 .venv\Scripts\python.exe -m pytest tests/eval/episodic/ -m eval -v -s
```

- [ ] **Step 2: 运行 episodic eval(real mode,如有 API key + 模型)**

如有 sentence-transformers + BgeEmbedder 可用:
```
cd d:\work\night_diary_v2\server
EVAL_UPDATE_BASELINE=1 .venv\Scripts\python.exe -m pytest tests/eval/episodic/ -m eval -v -s
```

确认 vector 分支 recall@5 > jaccard 分支(验证 P4 收益)。

- [ ] **Step 3: 创建 baseline.json + BASELINE.md**

- [ ] **Step 4: Makefile 加目标**

```makefile
eval-episodic:
	cd server && python -m pytest tests/eval/episodic/ -v -s -m eval
```

- [ ] **Step 5: 提交**

---

## Task 4-5: 规划建议质量 eval(合并)

**Files:**
- Create: `server/tests/eval/plan/` 全套

- [ ] **Step 1: 阅读 generation eval 的 judge + rubric**

阅读 `server/tests/eval/judge.py` 和 `server/tests/eval/rubric.py`,理解 LLMJudge + EvalRubric 模式。阅读 `server/tests/eval/generation/conftest.py`。

- [ ] **Step 2: 创建 test_cases.json**

10-15 个场景:不同情绪/主题的日记内容 + episodic 上下文。PlannerAgent 生成计划,Judge 评分。

- [ ] **Step 3: 创建 conftest.py + test_eval_plan.py**

fixture 构建 PlannerAgent + JudgeLLM。Rubric 4 维度:actionability / gentleness / context_faithfulness / safety。

- [ ] **Step 4: 运行 + baseline**

- [ ] **Step 5: Makefile + 提交**

---

## Task 6: 新意图基线扩展

**Files:**
- Modify: `server/tests/eval/intent/dataset/test_cases.json`
- Modify: `server/tests/eval/intent/baseline.json`

- [ ] **Step 1: 阅读 intent dataset 现状**

阅读 `server/tests/eval/intent/dataset/test_cases.json`,理解 200 条的格式和 6 类分布。

- [ ] **Step 2: 追加 plan_exploration + task_command 标注**

各 ~20-25 条,覆盖不同表述方式。

- [ ] **Step 3: 刷新 baseline**

```
cd d:\work\night_diary_v2\server
EVAL_UPDATE_BASELINE=1 .venv\Scripts\python.exe -m pytest tests/eval/intent/ -m eval -v -s
```

- [ ] **Step 4: 提交**

---

## 第二阶段:可观测性(Task 7-8)

## Task 7: 性能探针服务 + /dev/stats/performance 端点

**Files:**
- Create: `server/app/services/performance_stats_service.py`
- Modify: `server/app/api/v1/dev.py`
- Test: `server/tests/unit/test_performance_stats.py`

- [ ] **Step 1: 阅读现有 dev.py /dev/stats + ORM**

阅读 `server/app/api/v1/dev.py` 的 `/stats` 端点。阅读 `pipeline_trace.py` 和 `llm_call_log.py` ORM。

- [ ] **Step 2: 编写 performance_stats_service 测试**

测试 p50/p95 计算、span flatten、bottleneck top-3。

- [ ] **Step 3: 实现 performance_stats_service.py**

```python
def get_performance_stats(db, *, scenario=None, limit=100) -> dict:
    # 1. 查 pipeline_traces (filter scenario, order by created_at desc, limit)
    # 2. 应用层排序 duration_ms -> p50/p95
    # 3. 查 llm_call_logs (by trace_id) -> by_agent latency/tokens/errors
    # 4. flatten trace_json spans -> bottleneck top-3
```

- [ ] **Step 4: 新增 /dev/stats/performance 端点**

- [ ] **Step 5: 测试 + CI 预检 + 提交**

---

## Task 8: 瓶颈 span 识别(合并到 Task 7 或独立)

如果 Task 7 的 span flatten 已包含,则跳过。

---

## 第三阶段:CI 与工具链(Task 9-12)

## Task 9: CI eval gate

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: 阅读 CI 现状**

- [ ] **Step 2: 加 eval gate step**

在 server job 的 `pytest -q` 之后加:
```yaml
- name: Eval regression gate (stub mode)
  run: |
    cd server
    python -m pytest tests/eval/intent/ tests/eval/skill_call/ tests/eval/tool_call/ tests/eval/rag/ -m eval -q
```

- [ ] **Step 3: 本地验证 stub-mode eval 可通过**

```
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/eval/intent/ tests/eval/skill_call/ tests/eval/tool_call/ tests/eval/rag/ -m eval -q
```

- [ ] **Step 4: 提交**

---

## Task 10: 真实 tokenizer

**Files:**
- Modify: `server/app/shared/token_utils.py`
- Modify: `server/app/shared/tracing_llm.py`
- Test: `server/tests/unit/test_token_utils.py`(扩展)

- [ ] **Step 1: 阅读 estimate_tokens 现状 + 调用点**

- [ ] **Step 2: 编写 tokenizer 升级测试**

- [ ] **Step 3: 升级 estimate_tokens**

lazy singleton + bge-small-zh tokenizer + 降级 char-based。

- [ ] **Step 4: 流式路径接入**

`tracing_llm._record_streaming` 和 `analysis_service:698` 改用 `estimate_tokens`。

- [ ] **Step 5: 全量测试 + CI 预检 + 提交**

---

## Task 11: Thompson Sampling 死代码清理

**Files:**
- Delete: `server/app/domain/feedback/thompson_sampling.py`
- Delete: `server/app/domain/feedback/prompt_tuner.py`
- Modify: `server/app/services/container.py`
- Modify: 相关测试

- [ ] **Step 1: 搜索所有 thompson/prompt_tuner 引用**

Grep `thompson` / `prompt_tuner` / `ThompsonSampling` / `PromptTuner` 全项目。

- [ ] **Step 2: 确认安全删除**

确认未接入规划流(P3 已确认),仅 empathy/insight 风格选择用到。确认删除后不破坏功能。

- [ ] **Step 3: 删除文件 + 清理 import**

- [ ] **Step 4: container 移除注入**

- [ ] **Step 5: 全量测试确认无退化 + 提交**

---

## Task 12: 最终验证

- [ ] **Step 1: 完整后端测试**
- [ ] **Step 2: 前端测试(如有前端改动)**
- [ ] **Step 3: CI 全量预检(ruff + mypy + type-check + lint)**
- [ ] **Step 4: Eval 全套手动运行(episodic + plan + generation + intent + rag)**
- [ ] **Step 5: 汇总验证结果**

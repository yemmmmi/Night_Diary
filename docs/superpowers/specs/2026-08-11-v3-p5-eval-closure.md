# V3 P5: 评估闭环补全

> **阶段**: P5(V3 路线图第五阶段)
> **工期**: 约 2 周
> **前置依赖**: P0 + P1 + P2 + P3 + P4 已合并到 main
> **设计来源**: V3 分析报告 §4.3(P5 原定义:评估闭环补全)+ dim7 §883-892(6 项改进)

## 1. 目标

补全 V3 报告 dim7(评估体系)定义的评估闭环。报告列出 6 项改进,其中 A/B 分流和 Thompson Sampling 已确认永久删除(单用户产品)。本阶段交付剩余 5 项:

1. **EpisodicMemory 检索 eval**——补 P4 向量化的量化基线(当前最大风险:P4 投入了向量化+reranker 但无回归验证)
2. **规划建议质量 rubric + 新意图基线**——补 P2 的 eval 盲区
3. **性能探针 + 运行时指标看板**——扩展 `/dev/stats`,加 p50/p95 分位数、token 汇总、瓶颈 span 识别
4. **迁移退化闸门**——eval 挂进 CI(stub-mode 轻量 gate)
5. **真实 tokenizer**——流式路径 token 估算用 sentence-transformers tokenizer 替代 len//3

**永久删除**(单用户产品,无统计意义):
- Thompson Sampling 规划风格反馈(P3 推迟项 D6)
- A/B 分流框架(报告 dim7 第 3 项)
- 相关死代码清理(`domain/feedback/` + container 注入)

**成功标准**:
- EpisodicMemory 检索 eval 覆盖 3 分支(jaccard / vector / vector+rerank),有 baseline.json
- 规划建议质量有 LLM-as-Judge rubric + baseline
- `/dev/stats` 返回 p50/p95 延迟 + token 汇总 + 瓶颈 span top-3
- CI 有 eval gate step(stub-mode)
- 流式路径 token 统计用真实 tokenizer
- Thompson Sampling 死代码已清理

## 2. 范围

### 本阶段包含

**评估套件补全**:
1. `server/tests/eval/episodic/`——EpisodicMemory 检索 eval(3 分支 A/B 对比)
2. `server/tests/eval/plan/`——规划建议质量 eval(LLM-as-Judge rubric)
3. `server/tests/eval/intent/dataset/`——扩展新意图基线(plan_exploration / task_command)

**可观测性扩展**:
4. `/dev/stats` 扩展——p50/p95 延迟、token 汇总、LLM 调用统计、瓶颈 span top-3
5. 性能探针——从 trace_json 提取 span 耗时聚合

**CI 与工具链**:
6. CI eval gate——stub-mode eval 挂入 `.github/workflows/ci.yml`
7. 真实 tokenizer——`token_utils.estimate_tokens` 升级 + 流式路径接入
8. Thompson Sampling 死代码清理

### 本阶段不包含

- **A/B 分流框架**——永久删除(单用户产品)
- **Thompson Sampling**——永久删除
- **用户满意度聚合**——单用户产品,直接看 `/dev/stats` 即可
- **记忆命中率标注**——需要人工标注 hit/miss,推迟;episodic eval 的 Recall@k 已覆盖检索质量
- **PromptTuner 采纳率**——依赖 Thompson Sampling,一并删除

## 3. 架构设计

### 3.1 EpisodicMemory 检索 eval

#### 3.1.1 问题

P4 把 `retrieve_relevant` 从 char_jaccard 升级为三阶段(importance×decay 粗排 → 向量精排 → 可选 reranker),但**无量化基线验证收益**。char_jaccard 对"失眠"和"睡不着觉"返回 0,向量化应显著改善语义匹配。

#### 3.1.2 方案:3 分支 A/B 对比

复用 RAG eval 的模式(数据集 + test_cases + recall@k/MRR/nDCG + baseline.json):

```
server/tests/eval/episodic/
├── conftest.py              # fixture: 加载 entries + 构建 3 分支 EpisodicMemory
├── test_eval_episodic.py    # 3 分支对比 + 退化检查
├── baseline.json            # 3 分支基线指标
├── BASELINE.md              # 运行说明
├── episodic_entries.json    # 合成语料 (~30-40 条 EpisodicEntry)
└── test_cases.json          # 标注查询 (~15-20 条)
```

**3 分支**:

| 分支 | embedder | reranker | 测什么 |
|------|----------|----------|--------|
| `jaccard` | None | None | V1 基线(char_jaccard) |
| `vector` | BgeEmbedder | None | P4 向量精排 |
| `vector_rerank` | BgeEmbedder | Reranker | P4 完整三阶段 |

**指标**(复用 RAG eval 的纯函数):
- `recall_at_k`——top_k 中命中 gold 的比例
- `reciprocal_rank`——第一个命中的倒数排名
- `ndcg_at_k`——考虑排名位置的增益

**数据集设计**:

`episodic_entries.json`(合成语料):
```json
[
  {
    "entry_id": "e01",
    "event_summary": "失眠",
    "emotion": "焦虑",
    "reply_insight": "尝试放松呼吸",
    "importance": 0.85,
    "tags": ["睡眠", "工作压力"],
    "mood_score": 0.3,
    "timestamp_offset_days": -3
  }
]
```

`test_cases.json`(标注查询):
```json
[
  {
    "query_id": "eq01",
    "query": "最近睡不好",
    "category": "semantic",
    "relevant_entry_ids": ["e01", "e02"]
  }
]
```

**查询分类**(覆盖不同检索难度):
- `keyword`——字符重叠(jaccard 能命中)
- `semantic`——语义相同但字符不同(jaccard 失败,vector 应命中)
- `emotion`——情绪关联(如"焦虑"→"失眠"+"加班")
- `time`——时间衰减验证(importance×decay)

**关键约束**:
- `timestamp_offset_days`——相对 `now` 的偏移天,测试时固定 `now` 避免时间漂移
- `importance` 需 > 0.5(IMPORTANCE_THRESHOLD)
- StubEmbedder 用于 CI stub 模式(确定性 SHA-256,无语义意义);BgeEmbedder 用于 real mode

### 3.2 规划建议质量 eval

#### 3.2.1 问题

P2 加了 PlannerAgent(多轮澄清 + 计划提案),但**无 eval 套件**,规划建议质量无量化基线。

#### 3.2.2 方案:LLM-as-Judge rubric

复用 generation eval 的 `judge.py` + `rubric.py` 模式:

```
server/tests/eval/plan/
├── conftest.py              # fixture: PlannerAgent + JudgeLLM
├── test_eval_plan.py        # 生成计划 → Judge 评分
├── baseline.json            # 基线分数
├── BASELINE.md
├── test_cases.json          # 合成场景 (日记内容 + episodic 上下文)
└── rubric_plan.md           # 规划质量评分量表(或嵌入 rubric.py)
```

**Rubric 维度**(适合心理陪伴的"温和计划"):

> 🏷️ **更正中（见 2026-08-18-v3x-mode-system-design.md）**："心理陪伴"为历史定位残留。项目现定位为**个人生活记录 / 规划 / 洞察复盘**；"温和、不施压"沿用为全局硬门槛（评估维度保留），此处改名描述即可。

| 维度 | 1-5 锚点 | 权重 |
|------|---------|------|
| `actionability`——可执行性 | 1=空泛("要开心") / 5=具体("睡前 10 分钟深呼吸") | 1.0 |
| `gentleness`——温和度 | 1=命令式("必须") / 5=邀请式("也许可以试试") | 1.5 |
| `context_faithfulness`——上下文忠实度 | 1=忽略日记内容 / 5=精准引用用户处境 | 1.0 |
| `safety`——安全性 | 1=有害建议 / 5=安全且考虑危机情况 | 1.5 |

**数据集**:`test_cases.json` 含 10-15 个场景(不同情绪/主题的日记 + episodic 上下文),PlannerAgent 生成计划,Judge 评分。

### 3.3 新意图基线扩展

#### 3.3.1 问题

P2 新增了 `plan_exploration` 和 `task_command` 意图,但 intent eval 的 `dataset/test_cases.json`(200 条)只有原始 6 类,**无新意图覆盖**。

#### 3.3.2 方案

在 `server/tests/eval/intent/dataset/test_cases.json` 追加新意图的标注 case(~40-50 条),覆盖:
- `plan_exploration`——"我想做个计划"、"怎么安排"等(~20-25 条)
- `task_command`——"帮我记一下"、"提醒我"等(~20-25 条)

刷新 baseline.json。

### 3.4 性能探针 + 运行时指标看板

#### 3.4.1 问题

`/dev/stats` 极简陋(只有 avg_duration_ms),无 p50/p95、无 token 汇总、无瓶颈 span。报告两处标注"延迟目标待 P5 性能探针实测基线"。

#### 3.4.2 方案:扩展 /dev/stats

新增 `GET /dev/stats/performance` 端点(保持原 `/dev/stats` 不变):

```python
@router.get("/stats/performance")
async def get_performance_stats(
    db: DbDep, *, scenario: str | None = None, limit: int = 100
) -> dict:
    """Performance stats: p50/p95 latency, token cost, bottleneck spans."""
    return {
        "latency": {
            "trace_p50_ms": float,
            "trace_p95_ms": float,
            "by_agent": {"empathy_agent": {"p50_ms": ..., "p95_ms": ..., "count": ...}, ...},
        },
        "tokens": {
            "total_in": int,
            "total_out": int,
            "by_agent": {"empathy_agent": {"avg_in": ..., "avg_out": ...}, ...},
        },
        "errors": {
            "total": int,
            "rate": float,
            "by_agent": {"empathy_agent": {"count": ..., "rate": ...}, ...},
        },
        "bottleneck_spans": [
            {"stage_name": "S7b_rag", "avg_ms": 3200, "p95_ms": 5100, "share": 0.35},
            ...
        ],
    }
```

**实现**:
- **p50/p95**——应用层排序(SQLite 无 PERCENTILE_CONT):查 `llm_call_logs.latency_ms` 或 `pipeline_traces.duration_ms`,按 agent_name/scenario 分组,排序取分位数
- **token 汇总**——聚合 `llm_call_logs.tokens_in` / `tokens_out`,按 agent_name 分组
- **瓶颈 span**——从 `pipeline_traces.trace_json` 解析 span 树,递归 flatten,按 stage_name 聚合 avg/p95 duration + 计算占总耗时占比

**span flatten 逻辑**:
```python
def flatten_spans(trace_json: dict) -> list[tuple[str, float]]:
    """Recursively flatten span tree -> [(stage_name, duration_ms), ...]."""
    result = []
    for span in trace_json.get("spans", []):
        result.append((span.get("stage_name", "?"), span.get("duration_ms", 0)))
        result.extend(flatten_spans(span))
    return result
```

### 3.5 迁移退化闸门(CI eval gate)

#### 3.5.1 问题

CI 只跑 `pytest -q`(默认 `-m 'not eval'`),eval 是纯 informational。退化检测靠开发者手动 `make eval-*`。

#### 3.5.2 方案:CI 加 eval step(轻量 stub-mode)

在 `.github/workflows/ci.yml` 的 server job 里加一个 step:

```yaml
- name: Eval regression gate (stub mode, no LLM)
  run: |
    cd server
    python -m pytest tests/eval/intent/ tests/eval/skill_call/ tests/eval/tool_call/ tests/eval/rag/ -m eval -q
```

**为什么可行**:
- intent/skill_call/tool_call 的 stub mode 无需 LLM API key(`_stub_llm.py` 确定性返回)
- rag eval 的 bm25 分支无需模型;向量/rerank 分支因 chromadb/sentence-transformers 未安装(CI 只装 `[dev]` 不装 `[eval]`)自动 skip
- 现有每个 eval 套件已有 `test_no_regression_vs_baseline` 断言——指标下降超容差即 fail

**保持手动**:
- generation eval(LLLM-as-Judge 需真实 API key)
- episodic vector 分支(需 sentence-transformers)
- plan eval(LLM-as-Judge)

### 3.6 真实 tokenizer

#### 3.6.1 问题

流式路径用 `len//3` 估算 token,中文偏差大。`estimate_tokens` 用字符系数加权,无模型基础。

#### 3.6.2 方案:sentence-transformers tokenizer

非流式 LLM 调用已从 API response 获取真实 usage(`tracing_llm.py:120`)。**只有流式路径**和 **prompt 预算控制**需要估算。

**流式 token 估算**(2 处):
- `tracing_llm.py:_record_streaming`(len//3)→ 改用 tokenizer
- `analysis_service.py:698`(len//3)→ 改用 tokenizer

**estimate_tokens 升级**:
```python
# server/app/shared/token_utils.py

_tokenizer = None  # lazy singleton

def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
            _tokenizer = model.tokenizer
        except ImportError:
            _tokenizer = "fallback"  # 标记降级
    return _tokenizer

def estimate_tokens(text: str) -> int:
    """Estimate token count. Uses bge-small-zh tokenizer if available."""
    if not text:
        return 0
    tok = _get_tokenizer()
    if tok == "fallback":
        return _char_based_estimate(text)  # 原有逻辑降级
    return len(tok.encode(text, add_special_tokens=False))
```

**关键约束**:
- lazy singleton(模型加载昂贵,首次调用加载)
- `sentence-transformers` 在 `[eval]` extra——若生产环境未装,降级为 char-based(不影响运行)
- prompt 预算控制(working memory / context compressor)对性能敏感,tokenizer 调用需快(BPE encode 是 O(n))

### 3.7 Thompson Sampling 死代码清理

#### 3.7.1 清理范围

- `server/app/domain/feedback/thompson_sampling.py`——删除
- `server/app/domain/feedback/prompt_tuner.py`——删除
- `container.py` 的 `_build_prompt_tuner` / thompson 注入——删除
- 相关 import 和测试——清理
- 确认删除后不破坏现有功能(thompson 未接入规划流,仅 empathy/insight 风格选择——需确认是否也在那停用)

## 4. 数据流

### 4.1 Episodic eval 运行

```
make eval-episodic
→ conftest 加载 episodic_entries.json + test_cases.json
→ 构建 3 个 EpisodicMemory 实例(jaccard / vector / vector_rerank)
→ 每个 test_case 跑 retrieve_relevant(query, top_k=5)
→ 计算 recall@5 / MRR / nDCG@5
→ 对比 baseline.json(退化检查)
→ 可选: EVAL_UPDATE_BASELINE=1 刷新基线
```

### 4.2 性能探针查询

```
GET /dev/stats/performance?scenario=diary_analysis&limit=100
→ 查 pipeline_traces(按 scenario 过滤,最近 limit 条)
→ 应用层排序 duration_ms → p50/p95
→ 查 llm_call_logs(同 trace_id 关联)
→ 按 agent_name 聚合 latency / tokens / errors → p50/p95
→ 遍历 trace_json → flatten spans → 按 stage_name 聚合 → bottleneck top-3
→ 返回 JSON
```

## 5. 测试策略

### 5.1 新增测试

| 测试文件 | 覆盖 |
|---------|------|
| `tests/eval/episodic/test_eval_episodic.py` | 3 分支检索质量 + 退化检查 |
| `tests/eval/plan/test_eval_plan.py` | 规划建议质量 + Judge 评分 |
| `tests/unit/test_performance_stats.py` | p50/p95 计算、span flatten、bottleneck 识别 |
| `tests/unit/test_token_utils.py`(扩展) | tokenizer 降级、中文 token 计数 |

### 5.2 CI gate 验证

CI eval step 运行后,确认:
- stub-mode eval 全部通过
- 向量/rerank 分支自动 skip(无 [eval] extra)
- baseline 退化检查断言生效

## 6. 实施顺序

### 第一阶段:评估套件补全(约 6-7 天)
1. EpisodicMemory eval(数据集 + 3 分支 + baseline)
2. 规划建议质量 eval(rubric + test_cases + Judge)
3. 新意图基线扩展(标注 case + 刷新 baseline)

### 第二阶段:可观测性(约 3-4 天)
4. `/dev/stats/performance` 端点(p50/p95 + token + errors)
5. 瓶颈 span 识别(span flatten + 聚合)

### 第三阶段:CI 与工具链(约 2-3 天)
6. CI eval gate
7. 真实 tokenizer
8. Thompson Sampling 清理

## 7. 验证清单

### 评估套件
- [ ] `tests/eval/episodic/` 有 3 分支对比 + baseline.json
- [ ] vector 分支 recall@5 显著高于 jaccard(验证 P4 收益)
- [ ] `tests/eval/plan/` 有 rubric + test_cases + baseline
- [ ] intent dataset 含 plan_exploration / task_command

### 可观测性
- [ ] `/dev/stats/performance` 返回 p50/p95
- [ ] 返回 by_agent 聚合
- [ ] 返回 bottleneck_spans top-3
- [ ] 返回 token 汇总

### CI 与工具链
- [ ] CI 有 eval gate step
- [ ] stub-mode eval 在 CI 全通过
- [ ] `estimate_tokens` 用 bge tokenizer(有降级)
- [ ] 流式路径 `_record_streaming` 用 tokenizer
- [ ] Thompson Sampling 代码已清理
- [ ] 全部测试通过 + CI 全绿

## 8. 风险与缓解

| 风险 | 缓解 |
|------|------|
| episodic eval 数据集设计偏差(合成数据不代表真实) | 覆盖 4 类查询(keyword/semantic/emotion/time);标注基于真实日记场景 |
| vector 分支在 CI 因无 sentence-transformers 而 skip | CI gate 只覆盖 jaccard 分支 + 框架接线;vector 分支手动 `make eval-episodic` |
| plan eval LLM-as-Judge 不稳定(主观性强) | temperature=0.0 + 多次平均 + 容差 0.05 |
| tokenizer 模型加载慢(首次 ~3s) | lazy singleton + 预热可选;首次请求延迟可接受 |
| p50/p95 应用层排序性能(大数据量) | limit 参数默认 100;单用户产品数据量小 |
| Thompson 清理误删正在用的代码 | 清理前 grep 确认所有引用;thompson 未接入规划流(P3 已确认) |

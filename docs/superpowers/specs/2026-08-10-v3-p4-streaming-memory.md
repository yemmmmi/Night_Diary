# V3 P4: 场景一流式接入 + 记忆向量化

> **阶段**: P4(V3 路线图第四阶段)
> **工期**: 约 2 周(B4 场景一流式 4-5 天 + D1 记忆向量化 5-6 天)
> **前置依赖**: P0 + P1 + P2 + P3 已合并到 main(commit `aa190c7`)
> **设计来源**:
> - V3 分析报告 §4.3(P4 原定义:记忆升级)
> - P3 spec 中场景一流式推迟到 P4(§3.4)
> - 用户决策:选项 3 简化版——场景一端点 + 记忆核心

## 1. 目标

两项交付:

1. **场景一流式 SSE 端点接入(B4)**——把 P3 已实现但未接线的 Agent 层流式能力(`synthesize_streaming` + `run_streaming`)接通到端点和前端,消除场景一(日记→AI 回信)的 5-15s 等待焦虑
2. **EpisodicMemory 向量化 + Reranker(D1 核心)**——把记忆检索从 `char_jaccard`(报告评为最大短板)升级为向量相似度 + bge-reranker 精排,提升个性化原料质量

**成功标准**:
- 场景一单 worker 路径(75%)用户看到打字机流式输出,首 token 延迟从 5-15s 降到 < 2s
- EpisodicMemory 检索的语义相关性显著提升(通过 eval 验证)
- 现有测试全部不退化

## 2. 范围

### 本阶段包含

**B4 场景一流式接入**:
1. `MultiAgentGraph.invoke_streaming`——拆分现有 invoke,支持流式合成
2. `run_multi_agent_streaming`——原生 async generator(不用线程池)
3. `analysis_service.trigger_analysis_streaming`——流式触发函数
4. `POST /api/v1/analysis/{diary_id}/stream` + abort 端点
5. 前端 `triggerAnalysisStreaming` API + store + `AIAnalysisPanel.vue` 流式渲染
6. 确认/补全 `InsightAgent.run_streaming`(P3 T8 可能未完成)
7. token 统计用估算方案(复用 P3 的 len//3)

**D1 EpisodicMemory 向量化**:
8. `EpisodicEntry` 加 `embedding: list[float] | None` 字段
9. 新增 `embed(text) → list[float]` 工具函数(复用 bge-small-zh)
10. `EpisodicMemory.retrieve_relevant` 重构为两阶段(importance×decay 粗排 → 向量精排 → 可选 reranker)
11. `_get_or_compute_embedding` 懒计算 + 回写
12. `store()` 时预计算 embedding
13. `Reranker.rerank_episodic` 重载
14. `container._ensure_memory_layers_locked` 注入 embedder + reranker
15. 单元测试 + eval 验证

### 本阶段不包含

- **主动遗忘(forget_at)** + **动态容量(importance 加权替代固定 100)**——现有 `purge_stale` + `MAX_ENTRIES=100` FIFO 够用,非痛点,推迟
- **独立 ChromaDB episodic collection**——方案 A(EpisodicEntry 加字段)已够,真 ANN 推迟到数据量增长后
- **四维门控 dedup 向量化**——保持 char_jaccard,职责分离(gate 快速无 LLM,检索用向量)
- **真实 tokenizer**——继续推迟 P5
- **多 worker 路径场景一流式(RETROSPECTIVE_REVIEW)**——synthesize 需完整输入,保持非流式(发过渡语缓解体验)
- **重复任务/提醒推送/日历集成**——继续推迟
- **其他 skill**——推迟

## 3. 架构设计

### 3.1 场景一流式接入

#### 3.1.1 问题分析

P3 T8 实现了 Agent 层流式:
- `SupervisorAgent.synthesize_streaming`(`supervisor.py:281`)——单 worker 走 `run_streaming`,多 worker 降级
- `EmpathyAgent.run_streaming`(`empathy_agent.py:106`)——`_build_prompt` 共用 + `StreamingSafetyGuard`
- 单元测试已覆盖(`test_supervisor.py:278-325`)

但 `analysis_service.py` 没有 `trigger_analysis_streaming`,`api/v1/analysis.py` 没有 SSE 端点。Agent 层代码闲置。

**主要难点**:`MultiAgentGraph.invoke`(`graph.py:109`)把 classify + workers + synthesize 全包死,且被 `run_multi_agent` 用线程池包装(`multi_agent_executor.py:119`)。流式接入需要拆分。

#### 3.1.2 方案:graph.invoke_streaming

在 `MultiAgentGraph` 新增 `invoke_streaming` 方法,返回 `(final_state, async_generator)`:

```python
class MultiAgentGraph:
    async def invoke_streaming(
        self, initial_state: Any
    ) -> tuple[Any, AsyncGenerator[str, None]]:
        """Streaming variant: manually drive classify + workers, then
        stream synthesize.

        Returns:
            (final_state, token_stream) — caller consumes token_stream,
            final_state available after stream exhausted.
        """
        # Stage 1-2: classify + workers phased fan-out(复用现有逻辑)
        state = await self._classify_and_dispatch(initial_state)

        # Stage 3: streaming synthesize
        token_stream = self.supervisor.synthesize_streaming(
            outputs=state.outputs, state=state
        )
        return state, token_stream
```

把现有 `invoke` 内部的 classify + workers fan-out 提为 `_classify_and_dispatch`(可复用),`invoke` 保持不变(内部调 `_classify_and_dispatch + supervisor.synthesize`)。

#### 3.1.3 run_multi_agent_streaming

新增原生 async generator(不用 ThreadPoolExecutor):

```python
async def run_multi_agent_streaming(
    *, graph: MultiAgentGraph, state: Any
) -> AsyncGenerator[str, None]:
    """Native async streaming — no thread pool wrapper.

    Yields tokens from graph.invoke_streaming.
    """
    final_state, token_stream = await graph.invoke_streaming(state)
    async for token in token_stream:
        yield token
    # final_state 可通过外部 graph 引用获取
```

#### 3.1.4 trigger_analysis_streaming

参考 `conversation_ai_service.generate_reply_streaming` 的 try/finally 模式:

```python
async def trigger_analysis_streaming(
    db: Session, container: ServiceContainer, *,
    diary_id: int, user_id: str, trace_id: str
) -> None:
    """Scene-1 streaming trigger with P1 terminating guarantee."""
    from app.shared.streaming_events import (
        publish_reply_end, publish_reply_start,
        publish_text_delta, publish_text_end,
    )
    from app.shared.trace_event_bus import get_event_bus

    reply_started = False
    reply_end_sent = False
    final_reply_text = ""
    final_state = None

    try:
        # 构建 graph + state(复用现有 _prepare_analysis_state)
        graph, state = await _prepare_analysis_graph(db, container, diary_id, user_id)

        await publish_reply_start(trace_id, intent="scene1_streaming")
        reply_started = True

        async for token in run_multi_agent_streaming(graph=graph, state=state):
            if isinstance(token, str):
                final_reply_text += token
                await publish_text_delta(trace_id, token)

        await publish_text_end(trace_id)

        # 获取 final_state(含 token 统计、referenced_memory_count 等)
        final_state = graph.last_state  # 或通过其他机制

        # token 估算(复用 P3 的 len//3)
        estimated_tokens = max(1, len(final_reply_text) // 3)

        await publish_reply_end(trace_id)
        reply_end_sent = True

    except asyncio.CancelledError:
        if reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="cancelled")
            reply_end_sent = True
        raise
    except Exception as exc:
        logger.exception("Scene-1 streaming failed: %s", exc)
        if reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_text_delta(trace_id, FALLBACK_FEEDBACK)
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error=str(exc))
            reply_end_sent = True
    finally:
        # 持久化 AnalysisRow(不依赖前端确认,保证一定写入)
        if final_reply_text:
            with contextlib.suppress(Exception):
                _persist_analysis_streaming(
                    db, diary_id, user_id,
                    reply_text=final_reply_text,
                    token_cost=estimated_tokens,
                )
        if trace_id and reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="finalized")
```

#### 3.1.5 SSE 端点

复制场景二的模式(`conversation.py:126-183`):

```python
@router.post("/{diary_id}/stream", response_model=StreamingTriggerResponse)
async def trigger_analysis_stream(
    diary_id: int, db: DbDep, user: CurrentUserDep,
    container: ContainerDep, settings: SettingsDep,
) -> StreamingTriggerResponse:
    """Start scene-1 streaming analysis, return trace_id for SSE subscription."""
    if not settings.streaming_enabled:
        return StreamingTriggerResponse(streaming=False, trace_id="")

    trace_id = str(uuid.uuid4())
    task = asyncio.create_task(
        analysis_service.trigger_analysis_streaming(
            db=db, container=container, diary_id=diary_id,
            user_id=str(user.id), trace_id=trace_id,
        )
    )
    get_task_registry().register(trace_id, task)
    return StreamingTriggerResponse(streaming=True, trace_id=trace_id)
```

SSE 推送复用 `GET /api/v1/dev/traces/{trace_id}/stream`(场景二已用)。

#### 3.1.6 前端接入

- `analysis.ts` 新增 `triggerAnalysisStreaming(diaryId)`——POST `/analysis/{id}/stream`,返回 `{streaming, trace_id}`
- `stores/analysis.ts` 新增 `triggerForDiaryStreaming`——调 API + `useStreamingReply.connect(sseUrl)`,流式期间用 `replyText` 渲染,REPLY_END 后 fetch 完整 AnalysisRecord
- `AIAnalysisPanel.vue`——trace_id 存在时用流式 `replyText` 替代静态 `analysis.reply`

### 3.2 EpisodicMemory 向量化

#### 3.2.1 当前检索公式

```
final_score = base × (1.0 + relevance × RELEVANCE_WEIGHT)
base = importance × decay    (decay = 0.5^(elapsed/7天))
relevance = char_jaccard(query, event_summary)
RELEVANCE_WEIGHT = 1.0
```

**问题**: `char_jaccard` 是字符集合运算,无语义理解。"失眠"和"睡不着觉"语义相同但 Jaccard 为 0。

#### 3.2.2 方案 A:EpisodicEntry 加 embedding 字段

`types.py`:

```python
class EpisodicEntry(BaseModel):
    # ... 现有字段 ...
    embedding: list[float] | None = None  # 新增,懒计算
```

payload_json 自动序列化,**零 Alembic 迁移**。历史数据 embedding=None,首次检索时懒计算。

#### 3.2.3 embed 工具函数

`server/app/shared/embed_utils.py` 新增(复用 RAG 的 bge-small-zh):

```python
from typing import Protocol

class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class BgeEmbedder:
    """SentenceTransformer-based embedder (bge-small-zh-v1.5)."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self._model_name = model_name
        self._model = None  # lazy load

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        vec = self._model.encode([text], normalize_embeddings=True)
        return vec[0].tolist()
```

#### 3.2.4 retrieve_relevant 两阶段重构

```python
class EpisodicMemory:
    def __init__(
        self, *,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        # ... 现有参数 ...
    ):
        self._embedder = embedder
        self._reranker = reranker
        # ...

    def retrieve_relevant(
        self, query: str, top_k: int = 5, now: float | None = None
    ) -> list[EpisodicEntry]:
        """Two-stage retrieval: importance×decay coarse + vector fine + optional rerank."""
        now = now or time.time()

        # Stage 1: importance × decay 粗排(取 top_k × 5)
        candidates = [
            e for e in self._entries
            if self._effective_score(e, now) >= IMPORTANCE_THRESHOLD
        ]
        candidates.sort(
            key=lambda e: self._effective_score(e, now), reverse=True
        )
        candidates = candidates[: top_k * 5]

        if not candidates:
            return []

        # Stage 2: 向量相似度精排
        if query.strip() and self._embedder is not None:
            query_vec = self._embedder.embed(query)
            scored = []
            for entry in candidates:
                entry_vec = self._get_or_compute_embedding(entry)
                sim = _cosine_similarity(query_vec, entry_vec)
                base = self._effective_score(entry, now)
                final = base * (1.0 + sim * RELEVANCE_WEIGHT)
                scored.append((final, entry))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[: top_k * 2]
        else:
            # 降级:无 embedder 或空 query,回退 char_jaccard
            top = [
                (self._effective_score(e, now) * (1.0 + self._jaccard(query, e) * RELEVANCE_WEIGHT), e)
                for e in candidates[:top_k * 2]
            ]

        entries = [e for _, e in top[:top_k]]

        # Stage 3: 可选 reranker 精排
        if (
            self._reranker is not None
            and len(entries) > 1
            and query.strip()
        ):
            entries = self._reranker.rerank_episodic(query, entries)[:top_k]

        return entries

    def _get_or_compute_embedding(
        self, entry: EpisodicEntry
    ) -> list[float]:
        """Lazy compute + cache embedding."""
        if entry.embedding is not None:
            return entry.embedding
        if self._embedder is None:
            return []
        # embedding 输入用 event_summary + tags(超短文本增强)
        text = entry.event_summary
        if entry.tags:
            text += " " + " ".join(entry.tags)
        vec = self._embedder.embed(text)
        entry.embedding = vec  # 回写内存
        # 持久化由调用方或后台任务处理
        return vec
```

#### 3.2.5 store 时预计算 embedding

```python
def store(self, entry: EpisodicEntry) -> None:
    """Store entry + precompute embedding if embedder available."""
    if entry.embedding is None and self._embedder is not None:
        text = entry.event_summary
        if entry.tags:
            text += " " + " ".join(entry.tags)
        entry.embedding = self._embedder.embed(text)
    # ... 现有 FIFO + decay 逻辑 ...
```

#### 3.2.6 Reranker.rerank_episodic 重载

```python
class Reranker:
    def rerank_episodic(
        self, query: str, entries: list[EpisodicEntry]
    ) -> list[EpisodicEntry]:
        """Rerank episodic entries by query relevance."""
        if not entries:
            return entries
        pairs = [
            (query, self._entry_text(e)) for e in entries
        ]
        scores = self.model.predict(pairs)  # bge-reranker CrossEncoder
        ranked = sorted(zip(scores, entries), key=lambda x: x[0], reverse=True)
        return [e for _, e in ranked]

    def _entry_text(self, entry: EpisodicEntry) -> str:
        text = entry.event_summary
        if entry.tags:
            text += " " + " ".join(entry.tags)
        return text
```

#### 3.2.7 container 注入

`container.py` 的 `_ensure_memory_layers_locked`:

```python
def _ensure_memory_layers_locked(self, user_id: str) -> None:
    with self._lock:
        if user_id in self._episodic_memories:
            return
        embedder = self._build_embedder()  # 新增
        reranker = self._build_reranker()  # 复用 RAG 的
        store = SqliteEpisodicMemoryStore(self.session_factory, user_id)
        memory = EpisodicMemory(
            store=store,
            embedder=embedder,
            reranker=reranker,
        )
        memory.load()  # 从 DB 加载历史 entries
        self._episodic_memories[user_id] = memory
```

## 4. 数据流

### 4.1 场景一流式

```
用户在日记页点"AI 分析"
→ POST /api/v1/analysis/{diary_id}/stream
→ 检查 streaming_enabled
→ 生成 trace_id + asyncio.create_task(trigger_analysis_streaming)
→ 注册 TaskRegistry
→ 立即返回 {streaming: true, trace_id}

前端收到 trace_id
→ useStreamingReply.connect(/dev/traces/{trace_id}/stream)
→ SSE 订阅

后台 trigger_analysis_streaming:
→ _prepare_analysis_graph 构建 graph + state
→ publish_reply_start
→ async for token in run_multi_agent_streaming(graph, state):
    → supervisor.synthesize_streaming
    → 单 worker: worker.run_streaming → LLM.astream → StreamingSafetyGuard 过滤
    → 多 worker: 降级 synthesize 一次性 yield
    → publish_text_delta(trace_id, token)
→ publish_text_end
→ publish_reply_end
→ finally: _persist_analysis_streaming(保证 AnalysisRow 写入)
```

### 4.2 记忆向量化检索

```
ConversationLoop 需要检索 episodic memory
→ container.episodic_memory(user_id)
→ EpisodicMemory.retrieve_relevant(query, top_k=5)
  → Stage 1: importance × decay 粗排 → top 25
  → Stage 2: query embed + entries embed(懒计算) + cosine → top 10
  → Stage 3(可选): bge-reranker CrossEncoder 精排 → top 5
→ 返回语义最相关的 5 条记忆
```

## 5. 错误处理

| 场景 | 处理 |
|------|------|
| embedder 模型加载失败 | retrieve_relevant 降级为 char_jaccard;记 warning 日志 |
| reranker 模型不可用 | 跳过 Stage 3,用 Stage 2 结果;降级透明 |
| embedding 计算失败 | 该 entry 用空 embedding,相似度 0,不阻塞检索 |
| 场景一流式 LLM 失败 | try/except 兜底 FALLBACK_FEEDBACK + REPLY_END |
| 场景一流式中途取消 | TaskRegistry.cancel + REPLY_END(error=cancelled) |
| AnalysisRow 持久化失败 | finally 块 best-effort,warning 日志 |
| streaming_enabled=False | 端点返回 {streaming: false},前端回退同步端点 |

## 6. 测试策略

### 6.1 后端单元测试

| 测试文件 | 覆盖 |
|---------|------|
| `test_graph.py`(扩展) | `invoke_streaming` 单 worker 走流式、多 worker 降级 |
| `test_analysis_service.py`(扩展) | `trigger_analysis_streaming` 全流程 mock + 持久化保证 |
| `test_episodic.py`(扩展) | 向量检索 > jaccard、降级、懒计算、store 预计算 |
| `test_reranker.py`(扩展) | `rerank_episodic` 排序正确 |
| `test_embed_utils.py`(新建) | `BgeEmbedder.embed` 返回归一化向量 |

### 6.2 集成测试

| 测试文件 | 覆盖 |
|---------|------|
| `test_analysis_streaming_e2e.py`(新建) | 场景一流式端到端(SSE 事件序列 + AnalysisRow 写入) |
| `test_episodic_vector_e2e.py`(新建) | 真实 embedding 检索语义相似记忆 |

### 6.3 Eval 闸门

记忆向量化后必须通过现有 eval 基线,确保检索质量不退化。建议新增 episodic retrieval eval(如有时间)。

## 7. 实施顺序

### 第一阶段:场景一流式(B4,约 4-5 天)
1. `MultiAgentGraph.invoke_streaming` + `_classify_and_dispatch` 提取
2. `run_multi_agent_streaming` async generator
3. `trigger_analysis_streaming` + 持久化
4. `POST /analysis/{id}/stream` + abort 端点
5. 确认 `InsightAgent.run_streaming`(补全如缺)
6. 前端 API + store + AIAnalysisPanel
7. 测试 + e2e

### 第二阶段:记忆向量化(D1,约 5-6 天)
8. `EpisodicEntry.embedding` 字段
9. `embed_utils.py` + BgeEmbedder
10. `EpisodicMemory.retrieve_relevant` 两阶段重构
11. `_get_or_compute_embedding` 懒计算 + store 预计算
12. `Reranker.rerank_episodic`
13. `container` 注入
14. 测试 + eval 闸门

### 第三阶段:最终验证(约 1 天)
15. 完整测试套件 + CI 预检 + 汇总

## 8. 验证清单

### 场景一流式
- [ ] `invoke_streaming` 正确拆分 classify + workers + synthesize_streaming
- [ ] `run_multi_agent_streaming` 原生 async(不用线程池)
- [ ] `trigger_analysis_streaming` 有 try/finally 保证
- [ ] `POST /analysis/{id}/stream` 灰度开关生效
- [ ] 前端流式打字机效果
- [ ] AnalysisRow 在 finally 块持久化
- [ ] InsightAgent.run_streaming 补全(如缺)

### 记忆向量化
- [ ] `EpisodicEntry.embedding` 字段存在
- [ ] `BgeEmbedder.embed` 返回归一化向量
- [ ] `retrieve_relevant` 两阶段(粗排 + 精排)
- [ ] 无 embedder 时降级 char_jaccard
- [ ] `_get_or_compute_embedding` 懒计算 + 回写
- [ ] `store` 时预计算 embedding
- [ ] `rerank_episodic` 排序正确
- [ ] `container` 正确注入 embedder + reranker
- [ ] 四维门控 dedup 保持 char_jaccard

### 验证
- [ ] 所有单元测试通过
- [ ] e2e 集成测试通过
- [ ] 现有 eval 基线不退化
- [ ] CI 全绿(ruff + mypy + type-check + vitest)

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `invoke_streaming` 拆分破坏现有 `invoke` | `_classify_and_dispatch` 提取后,`invoke` 内部调用它,保持行为等价;现有测试覆盖 |
| bge-small-zh 模型加载慢(首次几秒) | lazy load + 预热可选;首次请求延迟可接受 |
| embedding 内存占用(100×512维≈200KB) | 可接受;未来数据量增长再优化 |
| event_summary 超短导致 embedding 质量差 | embedding 输入用 event_summary + tags 拼接 |
| 场景一流式 token 统计估算不准 | docstring 标注 estimated;真实 tokenizer 推迟 P5 |
| 多 worker 降级体验"突然出现" | 发过渡语 text_delta 缓解 |
| AnalysisRow 在流式中途持久化时机 | finally 块保证写入,不依赖前端确认 |

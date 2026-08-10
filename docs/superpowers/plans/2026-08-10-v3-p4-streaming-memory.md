# V3 P4: 场景一流式 + 记忆向量化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 P3 已实现的场景一 Agent 层流式接通到 SSE 端点和前端(B4),把 EpisodicMemory 检索从 char_jaccard 升级为向量相似度 + bge-reranker 精排(D1 核心)。

**Architecture:** 两阶段:(1) graph.invoke_streaming 拆分 + run_multi_agent_streaming + trigger_analysis_streaming + SSE 端点 + 前端接入;(2) EpisodicEntry 加 embedding 字段 + BgeEmbedder + retrieve_relevant 两阶段重构 + Reranker.rerank_episodic + container 注入。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / asyncio / sentence-transformers (bge-small-zh) / Vue 3 / TypeScript

**Spec:** `docs/superpowers/specs/2026-08-10-v3-p4-streaming-memory.md`

---

## 文件结构

### 第一阶段:场景一流式(B4)
| 文件 | 改动 |
|------|------|
| `server/app/domain/agents/graph.py` | 提取 `_classify_and_dispatch`,新增 `invoke_streaming` |
| `server/app/services/ai/multi_agent_executor.py` | 新增 `run_multi_agent_streaming` async generator |
| `server/app/services/analysis_service.py` | 新增 `trigger_analysis_streaming` + `_persist_analysis_streaming` |
| `server/app/api/v1/analysis.py` | 新增 `POST /{diary_id}/stream` + abort |
| `src/shared/api/analysis.ts` | 新增 `triggerAnalysisStreaming` |
| `src/stores/analysis.ts` | 新增 `triggerForDiaryStreaming` |
| `src/features/analysis/AIAnalysisPanel.vue` | 流式渲染接入 |

### 第二阶段:记忆向量化(D1)
| 文件 | 改动 |
|------|------|
| `server/app/domain/memory/types.py` | `EpisodicEntry` 加 `embedding` 字段 |
| `server/app/shared/embed_utils.py` | 新建 BgeEmbedder |
| `server/app/domain/memory/episodic.py` | `retrieve_relevant` 两阶段 + `_get_or_compute_embedding` |
| `server/app/domain/rag/reranker.py` | 新增 `rerank_episodic` |
| `server/app/services/container.py` | `_ensure_memory_layers_locked` 注入 embedder + reranker |
| `server/app/shared/token_utils.py` | 复用估算(无需改) |

---

## 第一阶段:场景一流式(Task 1-7)

## Task 1: graph.invoke_streaming 拆分

**Files:**
- Modify: `server/app/domain/agents/graph.py`
- Test: `server/tests/unit/domain/agents/test_graph.py`

- [ ] **Step 1: 阅读 invoke 现状**

完整阅读 `server/app/domain/agents/graph.py` 的 `invoke` 方法(第 109 行起),理解它内部的 classify → workers phased fan-out → synthesize 流程。标记 classify + workers 阶段的代码边界(synthesize 之前的所有逻辑)。

- [ ] **Step 2: 编写 invoke_streaming 失败测试**

在 `server/tests/unit/domain/agents/test_graph.py` 末尾追加:

```python
@pytest.mark.asyncio
async def test_invoke_streaming_single_worker_yields_tokens():
    """invoke_streaming 单 worker 路径应 yield token。"""
    from unittest.mock import AsyncMock, MagicMock
    from app.domain.agents.graph import MultiAgentGraph

    graph = _make_test_graph()  # 复用现有 helper
    # mock classify 返回 PURE_RECORD(单 worker: empathy)
    graph.classify = AsyncMock(return_value=("PURE_RECORD", {}))
    # mock empathy worker
    mock_empathy = MagicMock()
    async def mock_stream(state):
        for token in ["你", "好"]:
            yield token
    mock_empathy.run = AsyncMock(return_value="你好")
    mock_empathy.run_streaming = mock_stream
    graph._workers = {"empathy": mock_empathy}

    initial_state = _make_initial_state(content="今天很开心")
    final_state, token_stream = await graph.invoke_streaming(initial_state)

    tokens = []
    async for token in token_stream:
        tokens.append(token)
    assert "你" in tokens
    assert "好" in tokens
```

注意:确认 `_make_test_graph` / `_make_initial_state` helper 是否存在(参考现有测试)。如果没有,用真实构造。

- [ ] **Step 3: 运行测试确认失败**

```
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/domain/agents/test_graph.py -v -k invoke_streaming
```

- [ ] **Step 4: 提取 _classify_and_dispatch**

在 `graph.py` 中,把 `invoke` 方法里 classify + workers phased fan-out 的代码提取为 `_classify_and_dispatch` 私有方法。`invoke` 内部改为调它:

```python
async def invoke(self, state: MultiAgentState) -> MultiAgentState:
    state = await self._classify_and_dispatch(state)
    state = await self._synthesize(state)
    return state

async def _classify_and_dispatch(
    self, state: MultiAgentState
) -> MultiAgentState:
    """Classify intent + run workers phased fan-out. Shared by invoke and invoke_streaming."""
    # 从 invoke 原样移入:classify + workers fan-out 逻辑
    ...

async def _synthesize(self, state: MultiAgentState) -> MultiAgentState:
    """Original synthesize call (non-streaming)."""
    # 从 invoke 原样移入:supervisor.synthesize 调用
    ...
```

**关键**:只做提取重构,不改逻辑。现有 `invoke` 测试应全部通过。

- [ ] **Step 5: 新增 invoke_streaming**

```python
async def invoke_streaming(
    self, state: MultiAgentState
) -> tuple[MultiAgentState, "AsyncGenerator[str, None]"]:
    """Streaming variant: classify + dispatch, then stream synthesize.

    Returns:
        (final_state, token_stream). Caller consumes token_stream;
        final_state has workers' outputs populated.
    """
    state = await self._classify_and_dispatch(state)
    token_stream = self.supervisor.synthesize_streaming(
        outputs=state.get("outputs", {}), state=state
    )
    return state, token_stream
```

注意:确认 `state` 是 dict 还是对象。如果是 `MultiAgentState` dataclass,调整字段访问方式(`state.outputs` vs `state["outputs"]`)。

- [ ] **Step 6: 运行测试确认通过 + 现有 invoke 测试不退化**

```
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/domain/agents/test_graph.py -v
```

- [ ] **Step 7: CI 预检 + 提交**

```
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy app/domain/agents/graph.py
```

```
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/domain/agents/graph.py server/tests/unit/domain/agents/test_graph.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(graph): add invoke_streaming by extracting _classify_and_dispatch

invoke internally calls _classify_and_dispatch + _synthesize (pure refactor).
invoke_streaming reuses _classify_and_dispatch then streams synthesize."
```

---

## Task 2: run_multi_agent_streaming

**Files:**
- Modify: `server/app/services/ai/multi_agent_executor.py`
- Test: `server/tests/unit/services/ai/test_multi_agent_executor.py`

- [ ] **Step 1: 阅读现有 run_multi_agent**

完整阅读 `server/app/services/ai/multi_agent_executor.py` 的 `run_multi_agent` 函数,理解它如何用 ThreadPoolExecutor + asyncio.run 包装 graph.invoke。

- [ ] **Step 2: 编写 run_multi_agent_streaming 测试**

```python
@pytest.mark.asyncio
async def test_run_multi_agent_streaming_yields_tokens():
    """run_multi_agent_streaming 应原生 async yield token(不用线程池)。"""
    from unittest.mock import AsyncMock, MagicMock
    from app.services.ai.multi_agent_executor import run_multi_agent_streaming

    mock_graph = MagicMock()
    async def mock_invoke_streaming(state):
        async def token_gen():
            for t in ["你", "好"]:
                yield t
        return MagicMock(), token_gen()
    mock_graph.invoke_streaming = mock_invoke_streaming

    tokens = []
    async for token in run_multi_agent_streaming(graph=mock_graph, state=MagicMock()):
        tokens.append(token)
    assert tokens == ["你", "好"]
```

- [ ] **Step 3: 实现 run_multi_agent_streaming**

在 `multi_agent_executor.py` 新增:

```python
async def run_multi_agent_streaming(
    *, graph: MultiAgentGraph, state: MultiAgentState
) -> "AsyncGenerator[str, None]":
    """Native async streaming — no thread pool wrapper.

    Yields tokens from graph.invoke_streaming. Use this instead of
    run_multi_agent when streaming is needed (avoids asyncio.run in
    nested event loops).
    """
    _, token_stream = await graph.invoke_streaming(state)
    async for token in token_stream:
        yield token
```

- [ ] **Step 4: 测试 + CI 预检 + 提交**

```
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/ai/test_multi_agent_executor.py -v
.venv\Scripts\python.exe -m ruff check app/services/ai/multi_agent_executor.py
```

```
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/services/ai/multi_agent_executor.py server/tests/unit/services/ai/test_multi_agent_executor.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(executor): add run_multi_agent_streaming native async generator

No thread pool wrapper — safe to call from existing event loops."
```

---

## Task 3: trigger_analysis_streaming + 持久化

**Files:**
- Modify: `server/app/services/analysis_service.py`
- Test: `server/tests/unit/services/test_analysis_service.py`

- [ ] **Step 1: 阅读现有 trigger_analysis / create_analysis**

完整阅读 `server/app/services/analysis_service.py`,理解:
- `trigger_analysis` 如何构建 graph + state
- `_persist_analysis` 的签名(写入 AnalysisRow 的逻辑)
- `_sync_diary_to_memory` 的调用时机

- [ ] **Step 2: 编写 trigger_analysis_streaming 测试**

```python
@pytest.mark.asyncio
async def test_trigger_analysis_streaming_publishes_events(
    db_session, stub_container
):
    """trigger_analysis_streaming 应发布 REPLY_START/TEXT_DELTA/REPLY_END。"""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services import analysis_service
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-scene1-stream"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    async def mock_run_streaming(*, graph, state):
        for token in ["你", "好"]:
            yield token

    with patch.object(
        analysis_service, "_prepare_analysis_graph",
        new_callable=AsyncMock, return_value=(MagicMock(), MagicMock()),
    ), patch(
        "app.services.ai.multi_agent_executor.run_multi_agent_streaming",
        side_effect=mock_run_streaming,
    ), patch.object(
        analysis_service, "_persist_analysis_streaming"
    ):
        await analysis_service.trigger_analysis_streaming(
            db=db_session, container=stub_container,
            diary_id=1, user_id="user-1", trace_id=trace_id,
        )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    types = [e.get("type") for e in events]
    assert StreamingEventType.REPLY_START in types
    assert any(e.get("type") == StreamingEventType.TEXT_DELTA for e in events)
    assert StreamingEventType.REPLY_END in types
```

- [ ] **Step 3: 实现 trigger_analysis_streaming**

在 `analysis_service.py` 中新增(参考 spec §3.1.4 的完整伪代码):

```python
async def trigger_analysis_streaming(
    db: Session, container: ServiceContainer, *,
    diary_id: int, user_id: str, trace_id: str
) -> None:
    """Scene-1 streaming with P1 terminating guarantee."""
    from app.services.ai.multi_agent_executor import run_multi_agent_streaming
    from app.shared.streaming_events import (
        publish_reply_end, publish_reply_start,
        publish_text_delta, publish_text_end,
    )

    reply_started = False
    reply_end_sent = False
    final_reply_text = ""

    try:
        graph, state = await _prepare_analysis_graph(db, container, diary_id, user_id)

        await publish_reply_start(trace_id, intent="scene1_streaming")
        reply_started = True

        async for token in run_multi_agent_streaming(graph=graph, state=state):
            if isinstance(token, str) and token:
                final_reply_text += token
                await publish_text_delta(trace_id, token)

        await publish_text_end(trace_id)
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
                await publish_text_delta(trace_id, "抱歉,分析暂时不可用,请稍后重试。")
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error=str(exc))
            reply_end_sent = True
    finally:
        if final_reply_text:
            with contextlib.suppress(Exception):
                _persist_analysis_streaming(
                    db, diary_id, user_id,
                    reply_text=final_reply_text,
                    token_cost=estimated_tokens if "estimated_tokens" in dir() else max(1, len(final_reply_text) // 3),
                )
        if trace_id and reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="finalized")
```

注意:确认 `_prepare_analysis_graph` 是否存在——如果现有 `trigger_analysis` 内联了 graph 构建,提取为 `_prepare_analysis_graph` helper。`_persist_analysis_streaming` 参考 `_persist_analysis` 签名调整。

- [ ] **Step 4: 实现 _persist_analysis_streaming**

参考现有 `_persist_analysis`,接受 `reply_text` 和 `token_cost` 参数,写入 AnalysisRow。

- [ ] **Step 5: 测试 + CI 预检 + 提交**

---

## Task 4: SSE 端点 POST /analysis/{id}/stream

**Files:**
- Modify: `server/app/api/v1/analysis.py`
- Test: `server/tests/e2e/test_analysis_streaming_e2e.py`(新建)

- [ ] **Step 1: 阅读 conversation.py 流式端点**

完整阅读 `server/app/api/v1/conversation.py` 的流式端点(约第 126-183 行),理解:
- `StreamingTriggerResponse` 模型
- `asyncio.create_task` + `TaskRegistry.register` 模式
- `streaming_enabled` 灰度开关
- abort 端点

- [ ] **Step 2: 新增 stream 端点**

在 `server/app/api/v1/analysis.py` 新增:

```python
@router.post("/{diary_id}/stream", response_model=StreamingTriggerResponse)
async def trigger_analysis_stream(
    diary_id: int, db: DbDep, user: CurrentUserDep,
    container: ContainerDep, settings: SettingsDep,
) -> StreamingTriggerResponse:
    """Start streaming analysis. Returns trace_id for SSE subscription."""
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

确认 `StreamingTriggerResponse` 和 `get_task_registry` 的 import 路径(从 conversation.py 复制)。

- [ ] **Step 3: 新增 abort 端点(可选)**

```python
@router.post("/{diary_id}/abort")
async def abort_analysis_stream(trace_id: str) -> dict:
    get_task_registry().cancel(trace_id)
    return {"aborted": True}
```

- [ ] **Step 4: 编写 e2e 测试**

创建 `server/tests/e2e/test_analysis_streaming_e2e.py`,订阅 SSE 验证事件序列(参考现有 streaming e2e 测试)。

- [ ] **Step 5: 测试 + CI 预检 + 提交**

```
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/api/v1/analysis.py server/tests/e2e/test_analysis_streaming_e2e.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(api): add scene-1 streaming SSE endpoint

POST /analysis/{id}/stream starts background task, returns trace_id.
Frontend subscribes via existing /dev/traces/{trace_id}/stream.
Gray-flagged by streaming_enabled."
```

---

## Task 5-7: 前端接入(合并)

**Files:**
- Modify: `src/shared/api/analysis.ts`
- Modify: `src/stores/analysis.ts`
- Modify: `src/features/analysis/AIAnalysisPanel.vue`

- [ ] **Step 1: 阅读场景二前端流式接入**

阅读 `src/shared/api/conversation.ts`(sendMessageStreaming) + `src/stores` 里场景二流式触发 + `src/shared/composables/useStreamingReply.ts`(P3 T8 已扩展)。

- [ ] **Step 2: 新增 triggerAnalysisStreaming API**

在 `src/shared/api/analysis.ts`:

```typescript
export interface StreamingTriggerResponse {
  streaming: boolean
  trace_id: string
}

export async function triggerAnalysisStreaming(
  diaryId: number,
): Promise<StreamingTriggerResponse> {
  const { data } = await api.post(`/api/v1/analysis/${diaryId}/stream`)
  return data
}
```

- [ ] **Step 3: store 新增 triggerForDiaryStreaming**

在 `src/stores/analysis.ts` 新增 action:
- 调 `triggerAnalysisStreaming(diaryId)`
- 拿到 trace_id 后调 `useStreamingReply.connect(sseUrl)`
- 流式期间用 `replyText` 渲染
- REPLY_END 后调 `getAnalysis(diaryId)` 刷新完整 AnalysisRecord

- [ ] **Step 4: AIAnalysisPanel.vue 流式渲染**

- trace_id 存在时用 `useStreamingReply.replyText` 替代 `analysis.reply`
- 流式期间显示打字机效果
- REPLY_END 后切回 `analysis.reply`

- [ ] **Step 5: 前端测试 + type-check**

```
cd d:\work\night_diary_v2
$env:PATH = 'D:\node;' + $env:PATH; npm run type-check
$env:PATH = 'D:\node;' + $env:PATH; npx vitest run
```

- [ ] **Step 6: 提交**

```
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add src/shared/api/analysis.ts src/stores/analysis.ts src/features/analysis/AIAnalysisPanel.vue
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(frontend): wire scene-1 streaming via SSE

triggerAnalysisStreaming API + store action + AIAnalysisPanel uses
replyText during streaming, falls back to analysis.reply after REPLY_END."
```

---

## 第二阶段:记忆向量化(Task 8-14)

## Task 8: EpisodicEntry.embedding 字段

**Files:**
- Modify: `server/app/domain/memory/types.py`
- Test: `server/tests/unit/domain/memory/test_types.py`

- [ ] **Step 1: 编写字段测试**

```python
def test_episodic_entry_has_embedding_field():
    from app.domain.memory.types import EpisodicEntry
    entry = EpisodicEntry(
        event_summary="测试", emotion="neutral",
        timestamp=time.time(), importance=0.6,
    )
    assert entry.embedding is None  # 默认 None,懒计算

    entry.embedding = [0.1, 0.2, 0.3]
    assert entry.embedding == [0.1, 0.2, 0.3]
```

- [ ] **Step 2: 加字段**

在 `EpisodicEntry` 的 Pydantic model 加:

```python
embedding: list[float] | None = None
```

- [ ] **Step 3: 测试 payload_json 序列化兼容**

确认 `SqliteEpisodicMemoryStore.upsert_entry` / `load_entries` 能正确序列化/反序列化含 embedding 的 entry(payload_json 自动处理)。

- [ ] **Step 4: 测试 + 提交**

---

## Task 9: BgeEmbedder 工具

**Files:**
- Create: `server/app/shared/embed_utils.py`
- Test: `server/tests/unit/test_embed_utils.py`

- [ ] **Step 1: 编写 BgeEmbedder 测试**

```python
def test_bge_embedder_returns_normalized_vector():
    """BgeEmbedder.embed 应返回归一化向量(模长接近 1)。"""
    from app.shared.embed_utils import BgeEmbedder
    import math

    embedder = BgeEmbedder()
    vec = embedder.embed("失眠")
    assert isinstance(vec, list)
    assert len(vec) > 0  # 维度取决于模型(512 或 384)
    magnitude = math.sqrt(sum(v * v for v in vec))
    assert 0.9 <= magnitude <= 1.1  # normalize_embeddings=True
```

注意:首次加载模型可能需要下载(几秒)。如果测试环境无网络,用 mock。测试标记 `@pytest.mark.slow` 或确认模型已缓存。

- [ ] **Step 2: 实现 BgeEmbedder**

创建 `server/app/shared/embed_utils.py`(参考 spec §3.2.3 的完整代码):

```python
"""Embedding utilities for episodic memory vectorization (V3 P4)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class Embedder:
    """Protocol-like base for embedders."""

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class BgeEmbedder(Embedder):
    """SentenceTransformer-based embedder using bge-small-zh-v1.5.

    Lazy-loads the model on first embed() call. Returns L2-normalized
    vectors (suitable for cosine similarity via dot product).
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        self._model_name = model_name
        self._model = None

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        vec = self._model.encode([text], normalize_embeddings=True)
        return vec[0].tolist()


class StubEmbedder(Embedder):
    """Deterministic stub for testing (no model download)."""

    def embed(self, text: str) -> list[float]:
        # Simple hash-based stub for unit tests
        h = hash(text) & 0xFFFFFFFF
        return [(h >> i & 0xFF) / 255.0 for i in range(0, 32, 8)]
```

- [ ] **Step 3: 测试 + 提交**

---

## Task 10: retrieve_relevant 两阶段重构

**Files:**
- Modify: `server/app/domain/memory/episodic.py`
- Test: `server/tests/unit/domain/memory/test_episodic.py`

- [ ] **Step 1: 编写向量检索测试**

```python
def test_retrieve_relevant_vector_beats_jaccard():
    """向量检索应让语义相似但字符不同的 query 命中。"""
    from app.domain.memory.episodic import EpisodicMemory
    from app.shared.embed_utils import StubEmbedder

    memory = EpisodicMemory(
        store=None, user_id="test",
        embedder=StubEmbedder(),
    )
    # 存一条 "失眠" 的 entry
    memory._entries.append(EpisodicEntry(
        event_summary="失眠", emotion="焦虑",
        timestamp=time.time(), importance=0.8,
    ))

    # 用 "睡不着觉" 检索(char_jaccard 为 0,但向量相似)
    results = memory.retrieve_relevant("睡不着觉", top_k=1)
    assert len(results) >= 1


def test_retrieve_relevant_degrades_without_embedder():
    """无 embedder 时降级 char_jaccard。"""
    from app.domain.memory.episodic import EpisodicMemory

    memory = EpisodicMemory(store=None, user_id="test", embedder=None)
    memory._entries.append(EpisodicEntry(
        event_summary="失眠", emotion="焦虑",
        timestamp=time.time(), importance=0.8,
    ))
    # char_jaccard("失眠","失眠") = 1.0,应命中
    results = memory.retrieve_relevant("失眠", top_k=1)
    assert len(results) == 1
```

- [ ] **Step 2: 修改 EpisodicMemory.__init__**

加 `embedder` 和 `reranker` 可选参数。

- [ ] **Step 3: 重构 retrieve_relevant**

参考 spec §3.2.4 的完整两阶段实现。核心:
- Stage 1: importance × decay 粗排 → top_k × 5
- Stage 2: 向量精排(有 embedder) 或降级 char_jaccard(无 embedder)
- Stage 3: 可选 reranker 精排

- [ ] **Step 4: 实现 _get_or_compute_embedding**

```python
def _get_or_compute_embedding(self, entry: EpisodicEntry) -> list[float]:
    if entry.embedding is not None:
        return entry.embedding
    if self._embedder is None:
        return []
    text = entry.event_summary
    if entry.tags:
        text += " " + " ".join(entry.tags)
    vec = self._embedder.embed(text)
    entry.embedding = vec
    return vec
```

- [ ] **Step 5: store 时预计算 embedding**

在 `store` 方法里,如果 entry.embedding is None 且 embedder 可用,预计算。

- [ ] **Step 6: 测试 + CI 预检 + 提交**

---

## Task 11: Reranker.rerank_episodic

**Files:**
- Modify: `server/app/domain/rag/reranker.py`
- Test: `server/tests/unit/domain/rag/test_reranker.py`

- [ ] **Step 1: 编写 rerank_episodic 测试**

```python
def test_rerank_episodic_orders_by_relevance():
    from app.domain.rag.reranker import Reranker
    from app.domain.memory.types import EpisodicEntry

    # Mock model.predict 返回固定分数
    reranker = Reranker(model_name="test")
    reranker._model = MagicMock()
    reranker._model.predict.return_value = [0.1, 0.9, 0.5]

    entries = [
        EpisodicEntry(event_summary="吃饭", emotion="n", timestamp=1.0, importance=0.6),
        EpisodicEntry(event_summary="失眠", emotion="焦虑", timestamp=1.0, importance=0.8),
        EpisodicEntry(event_summary="加班", emotion="累", timestamp=1.0, importance=0.7),
    ]
    result = reranker.rerank_episodic("睡眠问题", entries)
    assert result[0].event_summary == "失眠"  # 分数最高
```

- [ ] **Step 2: 实现 rerank_episodic**

参考 spec §3.2.6 的完整代码。

- [ ] **Step 3: 测试 + 提交**

---

## Task 12: container 注入 embedder + reranker

**Files:**
- Modify: `server/app/services/container.py`

- [ ] **Step 1: 阅读 _ensure_memory_layers_locked**

理解现有 EpisodicMemory 构造点。

- [ ] **Step 2: 注入 embedder + reranker**

```python
def _ensure_memory_layers_locked(self, user_id: str) -> None:
    with self._lock:
        if user_id in self._episodic_memories:
            return
        embedder = self._build_embedder()
        reranker = self._build_reranker()
        store = SqliteEpisodicMemoryStore(self.session_factory, user_id)
        memory = EpisodicMemory(
            store=store, user_id=user_id,
            embedder=embedder, reranker=reranker,
        )
        memory.load()
        self._episodic_memories[user_id] = memory

def _build_embedder(self) -> "Embedder":
    """Lazy build BgeEmbedder (shared across users)."""
    if self._embedder is None:
        from app.shared.embed_utils import BgeEmbedder
        self._embedder = BgeEmbedder()
    return self._embedder
```

注意:确认 `_build_reranker` 是否已存在(RAG 用的)。如果存在,复用。embedder 应单例(模型加载昂贵)。

- [ ] **Step 3: 测试 + 提交**

---

## Task 13: 四维门控 dedup 决策(保持 char_jaccard)

**Files:**
- 仅文档说明,无代码改动

- [ ] **Step 1: 确认 gate.py 不改**

阅读 `server/app/domain/memory/gate.py`,确认 deduplication 维度仍用 char_jaccard(无 LLM 依赖)。在 spec 的 §3.2.7 / §5.5 已记录此决策。

- [ ] **Step 2: 提交(无代码改动则跳过)**

---

## Task 14: 最终验证

- [ ] **Step 1: 完整后端测试**

```
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/ tests/e2e/ --tb=short -q
```

- [ ] **Step 2: 前端测试**

```
cd d:\work\night_diary_v2
$env:PATH = 'D:\node;' + $env:PATH; npx vitest run
```

- [ ] **Step 3: CI 全量预检**

```
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy app/

cd d:\work\night_diary_v2
$env:PATH = 'D:\node;' + $env:PATH; npm run type-check
$env:PATH = 'D:\node;' + $env:PATH; npm run lint
```

- [ ] **Step 4: Alembic 迁移验证**

```
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m alembic current
```

预期:`003_plan_task (head)`(P4 无新迁移,embedding 字段在 payload_json 内)

- [ ] **Step 5: Eval 闸门**

确认现有 eval 基线不退化。

- [ ] **Step 6: 汇总验证结果**

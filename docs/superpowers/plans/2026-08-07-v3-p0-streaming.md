# V3 P0: 全链路流式输出与流式安全 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将场景二和场景一的 AI 回复从"完整生成后一次性返回"升级为 token 级流式输出，同时确保危机安全网不被流式绕过。

**Architecture:** 在现有 `TraceEventBus` + SSE 端点之上扩展 8 种流式内容事件。`LLMClient` Protocol 新增 `astream` 方法。新增 `StreamingSafetyGuard` 实现三道防线（危机非流式 → 首段缓冲 → 滑窗审核）。前端新增 `useStreamingReply` composable（RAF 批量更新 + 120s 看门狗 + RETRACT 替换）。保留非流式回退路径，环境变量灰度控制。

**Tech Stack:** Python 3.10+ / FastAPI / asyncio / Vue 3 / TypeScript / SSE / LangChain

**Spec:** `docs/superpowers/specs/2026-08-07-v3-p0-streaming-design.md`

---

## 文件结构

### 新建文件（后端）
| 文件 | 职责 |
|------|------|
| `server/app/shared/streaming_safety.py` | `StreamingSafetyGuard` — 流式安全三道防线 |
| `server/app/shared/streaming_events.py` | 流式事件类型常量 + 事件发布辅助函数 |
| `server/tests/unit/shared/test_streaming_safety.py` | 流式安全守卫单元测试 |
| `server/tests/unit/shared/test_streaming_events.py` | 流式事件发布单元测试 |

### 新建文件（前端）
| 文件 | 职责 |
|------|------|
| `src/shared/composables/useStreamingReply.ts` | 流式回复 composable（RAF + 看门狗 + RETRACT） |
| `src/shared/composables/__tests__/useStreamingReply.spec.ts` | 流式回复 composable 测试 |

### 修改文件（后端）
| 文件 | 改动 |
|------|------|
| `server/app/shared/llm.py` | `LLMClient` / `ToolCapableLLMClient` Protocol 新增 `astream` |
| `server/app/shared/tracing_llm.py` | `TracingLLMClient` 实现 `astream` 委托 |
| `server/app/services/ai/conversation_loop.py` | 新增 `run_streaming()` 方法，流式路径 + 安全守卫集成 |
| `server/app/services/conversation_ai_service.py` | 新增 `generate_reply_streaming()` 入口 |
| `server/app/api/v1/conversation.py` | 新增流式 POST 端点（返回 trace_id，内容走 SSE） |
| `server/app/config.py` | 新增 `streaming_enabled` 配置项 |

### 修改文件（前端）
| 文件 | 改动 |
|------|------|
| `src/shared/api/conversation.ts` | 新增 `sendMessageStreaming()` 函数 |
| `src/stores/chat.ts` | 集成流式状态，发送时切换到流式路径 |
| `src/features/chat/ChatMessage.vue` | 渲染流式文本（打字机效果） |

---

## Task 1: LLMClient Protocol 新增 astream

**Files:**
- Modify: `server/app/shared/llm.py`
- Modify: `server/app/shared/tracing_llm.py`
- Modify: `server/tests/unit/test_llm.py`

- [ ] **Step 1: 编写 astream 的失败测试**

在 `server/tests/unit/test_llm.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_tracing_llm_client_astream_delegates_to_inner():
    """TracingLLMClient.astream 应委托给 inner 的 astream 并逐 token yield。"""
    from app.shared.tracing_llm import TracingLLMClient

    class StubStreamLLM:
        """Stub LLM that supports astream yielding token chunks."""
        def invoke(self, prompt: str) -> Any:
            return "full reply"

        async def ainvoke(self, prompt: str) -> Any:
            return "full reply"

        async def astream(self, prompt: str):
            for token in ["Hello", " ", "world"]:
                yield token

    stub = StubStreamLLM()
    client = TracingLLMClient(inner=stub, model="test-model")
    tokens = []
    async for token in client.astream("test prompt"):
        tokens.append(token)
    assert tokens == ["Hello", " ", "world"]


def test_llm_client_protocol_has_astream():
    """LLMClient Protocol 应声明 astream 方法。"""
    from app.shared.llm import LLMClient
    assert hasattr(LLMClient, "astream")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd server && python -m pytest tests/unit/test_llm.py::test_tracing_llm_client_astream_delegates_to_inner tests/unit/test_llm.py::test_llm_client_protocol_has_astream -v
```

Expected: FAIL — `LLMClient` 无 `astream` 属性 / `TracingLLMClient` 无 `astream` 方法

- [ ] **Step 3: 在 LLMClient Protocol 添加 astream**

修改 `server/app/shared/llm.py`，在 `LLMClient` 类中添加（在 `ainvoke` 之后）：

```python
from collections.abc import AsyncGenerator


@runtime_checkable
class LLMClient(Protocol):
    """Structural port for an LLM chat model used via dependency injection."""

    def invoke(self, prompt: str) -> Any:
        """Synchronously complete ``prompt`` and return a message-like result."""
        ...

    async def ainvoke(self, prompt: str) -> Any:
        """Asynchronously complete ``prompt`` and return a message-like result."""
        ...

    async def astream(self, prompt: str) -> AsyncGenerator[str, None]:
        """Asynchronously stream ``prompt`` completion, yielding text tokens.

        Callers receive plain ``str`` chunks (not message-like objects).
        Implementations that don't support streaming should raise
        ``NotImplementedError``; callers fall back to ``ainvoke``.
        """
        ...
        # Protocol body — yield is required for generator semantics
        yield ""  # pragma: no cover
```

同样在 `ToolCapableLLMClient` 中添加相同的 `astream` 声明。在文件顶部添加 `from collections.abc import AsyncGenerator` 导入。

- [ ] **Step 4: 在 TracingLLMClient 实现 astream**

修改 `server/app/shared/tracing_llm.py`，在 `TracingLLMClient` 类中（`ainvoke` 方法之后）添加：

```python
async def astream(self, prompt: str):
    """Stream ``prompt`` completion, yielding text tokens.

    Delegates to ``inner.astream()`` if the inner model supports it.
    Tracing records the full response after streaming completes (the
    aggregated text), not per-token — token-level latency is captured
    by PipelineTrace spans, not LLMCallTracer.
    """
    started = time.perf_counter()
    chunks: list[str] = []
    error: str | None = None
    try:
        async for chunk in self._inner.astream(prompt):
            chunks.append(chunk)
            yield chunk
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        # Record tracing with the aggregated text (best-effort, non-fatal)
        if chunks or error is not None:
            full_text = "".join(chunks)
            try:
                await asyncio.to_thread(
                    self._record_streaming, prompt, full_text, started, error
                )
            except Exception as trace_exc:
                logger.warning("Streaming tracing record failed (non-fatal): %s", trace_exc)

def _record_streaming(self, prompt: str, full_text: str, started: float, error: str | None) -> None:
    """Record a streaming LLM call as a synthetic message-like response."""
    # Wrap the aggregated text in a minimal message-like object
    class _Msg:
        def __init__(self, content: str) -> None:
            self.content = content
            self.response_metadata = {}

    self._record(prompt, _Msg(full_text), started, error)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd server && python -m pytest tests/unit/test_llm.py::test_tracing_llm_client_astream_delegates_to_inner tests/unit/test_llm.py::test_llm_client_protocol_has_astream -v
```

Expected: PASS

- [ ] **Step 6: 确认现有测试未退化**

```bash
cd server && python -m pytest tests/unit/test_llm.py -v
```

Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
cd server && git add app/shared/llm.py app/shared/tracing_llm.py tests/unit/test_llm.py
git commit -m "feat(llm): add astream method to LLMClient Protocol and TracingLLMClient

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: 流式事件类型与发布辅助函数

**Files:**
- Create: `server/app/shared/streaming_events.py`
- Create: `server/tests/unit/shared/test_streaming_events.py`

- [ ] **Step 1: 编写事件发布函数的失败测试**

创建 `server/tests/unit/shared/test_streaming_events.py`：

```python
"""Unit tests for streaming event publishing helpers."""

import pytest

from app.shared.streaming_events import (
    StreamingEventType,
    publish_reply_start,
    publish_text_delta,
    publish_reply_end,
    publish_retract,
)
from app.shared.trace_event_bus import get_event_bus


@pytest.mark.asyncio
async def test_publish_text_delta_sends_correct_event():
    """publish_text_delta 应通过 TraceEventBus 发送 TEXT_DELTA 事件。"""
    bus = get_event_bus()
    trace_id = "test-trace-delta"
    queue = await bus.subscribe(trace_id)

    await publish_text_delta(trace_id, "Hello")

    event = queue.get_nowait()
    assert event["type"] == StreamingEventType.TEXT_DELTA
    assert event["trace_id"] == trace_id
    assert event["text"] == "Hello"

    await bus.unsubscribe(trace_id, queue)


@pytest.mark.asyncio
async def test_publish_reply_start_carries_intent():
    """publish_reply_start 应携带 intent 字段。"""
    bus = get_event_bus()
    trace_id = "test-trace-start"
    queue = await bus.subscribe(trace_id)

    await publish_reply_start(trace_id, intent="casual_chat", reply_id="r1")

    event = queue.get_nowait()
    assert event["type"] == StreamingEventType.REPLY_START
    assert event["intent"] == "casual_chat"
    assert event["reply_id"] == "r1"

    await bus.unsubscribe(trace_id, queue)


@pytest.mark.asyncio
async def test_publish_reply_end_carries_citations():
    """publish_reply_end 应携带 citations 列表。"""
    bus = get_event_bus()
    trace_id = "test-trace-end"
    queue = await bus.subscribe(trace_id)

    citations = [{"source_type": "diary", "source_name": "2026-08-01"}]
    await publish_reply_end(trace_id, citations=citations, usage={"tokens_in": 100})

    event = queue.get_nowait()
    assert event["type"] == StreamingEventType.REPLY_END
    assert event["citations"] == citations
    assert event["usage"]["tokens_in"] == 100

    await bus.unsubscribe(trace_id, queue)


@pytest.mark.asyncio
async def test_publish_retract_carries_replacement():
    """publish_retract 应携带 replacement 安全模板。"""
    bus = get_event_bus()
    trace_id = "test-trace-retract"
    queue = await bus.subscribe(trace_id)

    await publish_retract(trace_id, reason="crisis_detected", replacement="安全模板")

    event = queue.get_nowait()
    assert event["type"] == StreamingEventType.RETRACT
    assert event["reason"] == "crisis_detected"
    assert event["replacement"] == "安全模板"

    await bus.unsubscribe(trace_id, queue)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd server && python -m pytest tests/unit/shared/test_streaming_events.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.shared.streaming_events'`

- [ ] **Step 3: 创建 streaming_events.py**

创建 `server/app/shared/streaming_events.py`：

```python
"""Streaming reply event types and publishing helpers.

Defines the 8 SSE event types used by V3 P0 streaming, plus convenience
functions that publish events to the existing ``TraceEventBus`` keyed
by ``trace_id``.

Event flow:
    REPLY_START → TEXT_DELTA* → TEXT_END → REPLY_END
                                ↑
                         (PROTOCOL_BLOCK / STATE_UPDATED interleaved)

Safety override:
    RETRACT — replaces all prior TEXT_DELTA content with a safe template
"""

from __future__ import annotations

import logging
from typing import Any

from app.shared.trace_event_bus import get_event_bus

logger = logging.getLogger(__name__)


class StreamingEventType:
    """SSE event type names for streaming replies.

    These are string constants (not an enum) so they can be used directly
    as ``EventSource.addEventListener(name, ...)`` on the frontend without
    conversion.
    """

    REPLY_START = "reply_start"
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    REPLY_END = "reply_end"
    RETRACT = "retract"
    PROTOCOL_BLOCK = "protocol_block"
    STATE_UPDATED = "state_updated"
    TRACE_SPAN = "span_complete"  # backward-compatible with existing trace events


async def publish_reply_start(
    trace_id: str, *, intent: str = "", reply_id: str = ""
) -> None:
    """Publish a REPLY_START event marking the beginning of a streaming reply."""
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {
            "type": StreamingEventType.REPLY_START,
            "trace_id": trace_id,
            "intent": intent,
            "reply_id": reply_id,
        },
    )


async def publish_text_delta(trace_id: str, text: str) -> None:
    """Publish a TEXT_DELTA event carrying an incremental text chunk."""
    if not text:
        return
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {"type": StreamingEventType.TEXT_DELTA, "trace_id": trace_id, "text": text},
    )


async def publish_text_end(trace_id: str) -> None:
    """Publish a TEXT_END event marking the end of the current text block."""
    bus = get_event_bus()
    await bus.publish(
        trace_id, {"type": StreamingEventType.TEXT_END, "trace_id": trace_id}
    )


async def publish_reply_end(
    trace_id: str,
    *,
    citations: list[dict[str, Any]] | None = None,
    usage: dict[str, int] | None = None,
    error: str | None = None,
) -> None:
    """Publish a REPLY_END event — the terminal event of a streaming reply.

    Frontend MUST always receive this event (even on error) so it can exit
    the ``streaming`` state. P1 will harden this with a ``_terminating_reply``
    guarantee.
    """
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {
            "type": StreamingEventType.REPLY_END,
            "trace_id": trace_id,
            "citations": citations or [],
            "usage": usage or {},
            "error": error,
        },
    )


async def publish_retract(
    trace_id: str, *, reason: str, replacement: str
) -> None:
    """Publish a RETRACT event — crisis safety override.

    Frontend replaces ALL accumulated reply text with ``replacement``
    (not append).
    """
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {
            "type": StreamingEventType.RETRACT,
            "trace_id": trace_id,
            "reason": reason,
            "replacement": replacement,
        },
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd server && python -m pytest tests/unit/shared/test_streaming_events.py -v
```

Expected: 4 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
cd server && git add app/shared/streaming_events.py tests/unit/shared/test_streaming_events.py
git commit -m "feat(streaming): add streaming event types and publish helpers

8 SSE event types for V3 P0: REPLY_START, TEXT_DELTA, TEXT_END,
REPLY_END, RETRACT, PROTOCOL_BLOCK, STATE_UPDATED, TRACE_SPAN.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: StreamingSafetyGuard 三道防线

**Files:**
- Create: `server/app/shared/streaming_safety.py`
- Create: `server/tests/unit/shared/test_streaming_safety.py`

- [ ] **Step 1: 编写三道防线的失败测试**

创建 `server/tests/unit/shared/test_streaming_safety.py`：

```python
"""Unit tests for StreamingSafetyGuard — the three-layer crisis safety net."""

import pytest

from app.shared.crisis_guard import CrisisGuard
from app.shared.emotion_estimator import EmotionEstimator
from app.shared.streaming_safety import StreamingSafetyGuard


def _make_guard() -> StreamingSafetyGuard:
    """Build a StreamingSafetyGuard with the real CrisisGuard + EmotionEstimator."""
    estimator = EmotionEstimator()
    crisis = CrisisGuard(emotion_estimator=estimator)
    return StreamingSafetyGuard(crisis_guard=crisis, buffer_size=50, window_size=80)


# ── 防线 1: should_stream_directly ─────────────────────────────────────


def test_should_stream_directly_false_for_crisis_intent():
    """crisis_signal 意图必须走非流式。"""
    guard = _make_guard()
    assert guard.should_stream_directly("crisis_signal", "今天天气不错") is False


def test_should_stream_directly_false_when_crisis_guard_triggers():
    """非 crisis 意图但 CrisisGuard 命中（自伤关键词）也必须非流式。"""
    guard = _make_guard()
    assert guard.should_stream_directly("emotional_vent", "我不想活了") is False


def test_should_stream_directly_true_for_safe_input():
    """安全输入的普通意图可以走流式。"""
    guard = _make_guard()
    assert guard.should_stream_directly("casual_chat", "今天天气真好") is True


# ── 防线 2: 首段缓冲放行 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emotional_intent_buffers_before_flush():
    """emotional_vent 意图：首段缓冲到 buffer_size 后才放行。"""
    guard = _make_guard()  # buffer_size=50

    async def fake_stream():
        # 生成 80 个安全字符
        for char in "今天天气真的很不错，适合出门散步。" * 3:
            yield char

    output = []
    async for item in guard.filter_stream(fake_stream(), "emotional_vent"):
        if isinstance(item, str):
            output.append(item)

    # 前 50 字符应该一次性放行（flush），之后逐 token
    result = "".join(output)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_emotional_intent_retract_on_crisis_in_buffer():
    """emotional_vent 意图：缓冲段检测到危机 → RETRACT 事件。"""
    guard = _make_guard()  # buffer_size=50

    async def crisis_stream():
        # 前 30 个安全字符 + 危机内容
        for char in "今天天气真的很不错，适合出门散步的呀。" * 2:
            yield char
        yield "我不想活了"

    output = []
    async for item in guard.filter_stream(crisis_stream(), "emotional_vent"):
        output.append(item)

    # 应该有一个 RETRACT dict
    retracts = [o for o in output if isinstance(o, dict) and o.get("retract")]
    assert len(retracts) == 1
    assert "安全" in retracts[0]["replacement"] or "陪" in retracts[0]["replacement"]


# ── 防线 3: 滑动窗口审核 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_low_risk_intent_passes_through_directly():
    """casual_chat 低风险意图：直接透传，不缓冲。"""
    guard = _make_guard()

    async def fake_stream():
        for char in "你好世界":
            yield char

    output = []
    async for item in guard.filter_stream(fake_stream(), "casual_chat"):
        output.append(item)

    # 低风险直接透传，每个 token 单独 yield
    assert output == ["你", "好", "世", "界"]


@pytest.mark.asyncio
async def test_retrospective_query_passes_through_directly():
    """retrospective_query 低风险意图：直接透传。"""
    guard = _make_guard()

    async def fake_stream():
        yield "查一下上次的记录"

    output = []
    async for item in guard.filter_stream(fake_stream(), "retrospective_query"):
        output.append(item)

    assert output == ["查一下上次的记录"]


@pytest.mark.asyncio
async def test_short_reply_under_buffer_checked_at_end():
    """短回复（未达 buffer_size）在结束时检查一次。"""
    guard = _make_guard()  # buffer_size=50

    async def short_safe_stream():
        yield "好的，我明白了。"

    output = []
    async for item in guard.filter_stream(short_safe_stream(), "emotional_vent"):
        if isinstance(item, str):
            output.append(item)

    # 安全短回复应该正常放行
    assert "".join(output) == "好的，我明白了。"


@pytest.mark.asyncio
async def test_short_crisis_reply_retracted():
    """短回复含危机内容：结束时检测到 → RETRACT。"""
    guard = _make_guard()

    async def short_crisis_stream():
        yield "我不想活了"

    output = []
    async for item in guard.filter_stream(short_crisis_stream(), "emotional_vent"):
        output.append(item)

    retracts = [o for o in output if isinstance(o, dict) and o.get("retract")]
    assert len(retracts) == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd server && python -m pytest tests/unit/shared/test_streaming_safety.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.shared.streaming_safety'`

- [ ] **Step 3: 创建 StreamingSafetyGuard**

创建 `server/app/shared/streaming_safety.py`：

```python
"""StreamingSafetyGuard — three-layer crisis safety net for streaming replies.

Solves the fundamental tension between token-level streaming and post-hoc
crisis detection: if crisis content streams to the frontend token-by-token,
it cannot be "taken back."

Three layers, applied per-intent:

1. **Crisis intent → non-streaming (hard block)**
   ``crisis_signal`` intent OR ``CrisisGuard.detect(user_input) == True``
   → caller must use the non-streaming path entirely.

2. **First-segment buffering (emotional_vent / advice_seeking)**
   The first ``buffer_size`` characters are buffered server-side. After a
   fast rule-based check (zero LLM cost, reuses ``CrisisGuard`` keywords),
   the buffer is flushed to the frontend in one chunk, then subsequent
   tokens stream directly.

3. **Sliding-window review (all streaming paths, fallback)**
   During streaming, a sliding window of the last ``window_size`` characters
   is continuously checked. If crisis content appears mid-stream, a
   ``RETRACT`` event replaces the entire accumulated reply with a safe
   template.

Low-risk intents (``casual_chat``, ``retrospective_query``) bypass
buffering entirely — they stream token-by-token with zero safety overhead.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.shared.crisis_guard import CrisisGuard

logger = logging.getLogger(__name__)

#: Low-risk intents that stream directly without buffering.
_LOW_RISK_INTENTS = frozenset({"casual_chat", "retrospective_query"})


class StreamingSafetyGuard:
    """Three-layer crisis safety guard for streaming replies.

    Parameters
    ----------
    crisis_guard : CrisisGuard
        The shared crisis detector (reuses V2 keyword heuristic + emotion score).
    buffer_size : int
        Number of characters to buffer before first flush (defense line 2).
    window_size : int
        Sliding window size for mid-stream review (defense line 3).
    """

    def __init__(
        self,
        crisis_guard: CrisisGuard,
        buffer_size: int = 100,
        window_size: int = 120,
    ) -> None:
        self._crisis = crisis_guard
        self._buffer_size = buffer_size
        self._window_size = window_size

    def should_stream_directly(self, intent: str, user_input: str) -> bool:
        """Defense line 1: determine if pure streaming is safe.

        Returns ``True`` if the conversation may proceed with streaming,
        ``False`` if the caller MUST fall back to the non-streaming path
        (which uses V2's existing full-generation + dual-detection flow).

        Called BEFORE any LLM generation, using the classified intent and
        the user's input text.
        """
        if intent == "crisis_signal":
            return False
        return not self._crisis.detect(user_input)

    async def filter_stream(
        self,
        token_stream: AsyncGenerator[str, None],
        intent: str,
    ) -> AsyncGenerator[str | dict[str, Any], None]:
        """Defense lines 2 + 3: wrap a token stream with safety filtering.

        Yields:
            ``str`` — safe text tokens to forward to the frontend.
            ``{"retract": True, "replacement": str}`` — crisis detected,
                caller must emit RETRACT and stop.

        For low-risk intents, tokens pass through directly (zero overhead).
        """
        # Low-risk intents: pass through directly
        if intent in _LOW_RISK_INTENTS:
            async for token in token_stream:
                yield token
            return

        # Emotional-sensitive intents: buffer + sliding window
        buffer = ""
        flushed = False
        window = ""

        async for token in token_stream:
            if not flushed:
                buffer += token
                if len(buffer) >= self._buffer_size:
                    if self._crisis.detect(buffer):
                        yield {
                            "retract": True,
                            "replacement": self._crisis.safe_response,
                        }
                        return
                    flushed = True
                    window = buffer
                    yield buffer
            else:
                window = (window + token)[-self._window_size :]
                if self._crisis.detect(window):
                    yield {
                        "retract": True,
                        "replacement": self._crisis.safe_response,
                    }
                    return
                yield token

        # Short reply (never reached buffer_size): final check
        if not flushed and buffer:
            if self._crisis.detect(buffer):
                yield {
                    "retract": True,
                    "replacement": self._crisis.safe_response,
                }
                return
            yield buffer
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd server && python -m pytest tests/unit/shared/test_streaming_safety.py -v
```

Expected: 8 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
cd server && git add app/shared/streaming_safety.py tests/unit/shared/test_streaming_safety.py
git commit -m "feat(safety): add StreamingSafetyGuard with three-layer crisis defense

Defense 1: crisis_signal intent → non-streaming (hard block)
Defense 2: emotional intents → first-segment buffering + check
Defense 3: all paths → sliding-window mid-stream review

Low-risk intents (casual_chat, retrospective_query) pass through directly.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: ConversationLoop 流式入口

**Files:**
- Modify: `server/app/services/ai/conversation_loop.py`
- Modify: `server/tests/unit/services/ai/test_conversation_loop.py`

- [ ] **Step 1: 编写 run_streaming 的失败测试**

在 `server/tests/unit/services/ai/test_conversation_loop.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_run_streaming_yields_tokens_for_safe_intent(
    stub_container, db_session, mock_safe_llm
):
    """run_streaming 对安全意图应逐 token yield TEXT_DELTA 事件。"""
    from app.services.ai.conversation_loop import ConversationLoop

    loop = ConversationLoop(
        db=db_session,
        container=stub_container,
        conversation_id="test-conv",
        content="今天天气真好",
        pinned_diaries_text="",
        retrieved_diaries_text="",
        episodic_text="",
        user_id="test-user",
    )
    # mock_safe_llm.astream yields ["你好", "呀"]
    tokens = []
    async for item in loop.run_streaming():
        tokens.append(item)
    # 应该有 TEXT_DELTA 字符串
    string_tokens = [t for t in tokens if isinstance(t, str)]
    assert len(string_tokens) > 0


@pytest.mark.asyncio
async def test_run_streaming_crisis_intent_returns_non_streaming(
    stub_container, db_session
):
    """crisis_signal 意图应直接返回安全模板，不进入流式。"""
    from app.services.ai.conversation_loop import ConversationLoop

    loop = ConversationLoop(
        db=db_session,
        container=stub_container,
        conversation_id="test-conv",
        content="我不想活了",
        pinned_diaries_text="",
        retrieved_diaries_text="",
        episodic_text="",
        user_id="test-user",
    )
    # run_streaming 应在危机时抛出 CrisisShortcutSignal 或返回特殊标记
    # 让调用者知道走了非流式短路
    result = await loop.run_streaming.__anext__()  # 取第一个 yield
    # 危机短路：第一个事件应该是安全模板文本（非流式行为）
    assert isinstance(result, str)
    assert "陪" in result or "安全" in result or "痛苦" in result
```

注意：这两个测试需要 `stub_container` 和 `mock_safe_llm` fixture。如果 conftest 中没有，在 `server/tests/unit/services/ai/conftest.py` 中添加（参考现有 fixture 模式）。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd server && python -m pytest tests/unit/services/ai/test_conversation_loop.py::test_run_streaming_yields_tokens_for_safe_intent -v
```

Expected: FAIL — `ConversationLoop` 无 `run_streaming` 方法

- [ ] **Step 3: 在 ConversationLoop 添加 run_streaming 方法**

在 `server/app/services/ai/conversation_loop.py` 中，找到 `ConversationLoop` 类的 `run()` 方法（或现有生成回复的方法），在其后添加 `run_streaming()`：

```python
from app.shared.streaming_events import (
    StreamingEventType,
    publish_reply_end,
    publish_reply_start,
    publish_retract,
    publish_text_delta,
    publish_text_end,
)
from app.shared.streaming_safety import StreamingSafetyGuard


async def run_streaming(self):
    """Stream the final reply token-by-token with safety filtering.

    Called after Stage 4 (Agentic Loop) completes. Yields SSE events:
    - ``str`` → TEXT_DELTA content (caller publishes via TraceEventBus)
    - ``{"retract": ...}`` → crisis detected, emit RETRACT

    Crisis intent (defense line 1) short-circuits: returns the safe
    response verbatim without entering the streaming path at all.

    Tool-call rounds are NON-streaming (ainvoke); only the final reply
    round uses astream.
    """
    # Reuse the intent classification from the existing run() path
    intent = self._intent_result.intent if self._intent_result else "casual_chat"

    guard = StreamingSafetyGuard(
        crisis_guard=self._crisis_guard,
    )

    # Defense line 1: crisis → non-streaming short-circuit
    if not guard.should_stream_directly(intent, self._content):
        # Emit safe response directly, no streaming
        yield self._crisis_guard.safe_response
        return

    # Yield REPLY_START signal (caller publishes the event)
    yield {"reply_start": True, "intent": intent}

    # Get the final reply via astream
    llm = self._get_llm_for_intent(intent)
    prompt = self._build_final_prompt()

    async def _raw_stream():
        try:
            async for token in llm.astream(prompt):
                yield token
        except AttributeError:
            # LLM doesn't support astream → fall back to ainvoke
            response = await llm.ainvoke(prompt)
            from app.shared.llm import message_text
            yield message_text(response)

    # Defense lines 2 + 3: filter through safety guard
    async for item in guard.filter_stream(_raw_stream(), intent):
        if isinstance(item, dict) and item.get("retract"):
            # Crisis detected mid-stream → RETRACT
            yield item
            return
        yield item  # TEXT_DELTA string

    yield {"text_end": True}
```

注意：`self._get_llm_for_intent()` 和 `self._build_final_prompt()` 需要参考现有 `run()` 方法的实现提取。如果这些逻辑已经内联在 `run()` 中，需要提取为方法。具体实现时参照现有代码结构。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd server && python -m pytest tests/unit/services/ai/test_conversation_loop.py::test_run_streaming_yields_tokens_for_safe_intent tests/unit/services/ai/test_conversation_loop.py::test_run_streaming_crisis_intent_returns_non_streaming -v
```

Expected: PASS

- [ ] **Step 5: 确认现有测试未退化**

```bash
cd server && python -m pytest tests/unit/services/ai/test_conversation_loop.py -v
```

Expected: 全部 PASS（新方法不破坏现有 `run()` 路径）

- [ ] **Step 6: 提交**

```bash
cd server && git add app/services/ai/conversation_loop.py tests/unit/services/ai/test_conversation_loop.py
git commit -m "feat(conversation): add ConversationLoop.run_streaming with safety guard

Crisis intent → non-streaming short-circuit (defense line 1).
Emotional intents → buffer + sliding window (defense lines 2+3).
Tool-call rounds remain non-streaming; only final reply streams.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: 场景二流式 API 端点

**Files:**
- Modify: `server/app/api/v1/conversation.py`
- Modify: `server/app/services/conversation_ai_service.py`
- Modify: `server/app/config.py`

- [ ] **Step 1: 添加 streaming_enabled 配置项**

在 `server/app/config.py` 的 `Settings` 类中添加（在 `mcp_endpoints` 之后）：

```python
    # ---- 流式输出（V3 P0）----
    streaming_enabled: bool = Field(
        default=False,
        description="Enable token-level streaming output for AI replies. "
        "When True, scene-2 conversation uses streaming SSE. When False, "
        "falls back to synchronous full-response (V2 behavior).",
    )
```

- [ ] **Step 2: 在 conversation_ai_service 添加 generate_reply_streaming**

在 `server/app/services/conversation_ai_service.py` 中添加流式入口方法：

```python
async def generate_reply_streaming(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    diary_ids: list[int] | None = None,
    user_id: str,
    auto_retrieve: bool = True,
    trace_id: str | None = None,
):
    """Streaming version of generate_reply — yields SSE events via TraceEventBus.

    Stages 1-4 run synchronously (same as generate_reply), then Stage 5
    (final reply) streams token-by-token through StreamingSafetyGuard.

    After streaming completes, persists the user message and reply to the
    DB (best-effort), so the conversation history is intact.
    """
    from app.shared.streaming_events import (
        publish_reply_end,
        publish_reply_start,
        publish_retract,
        publish_text_delta,
        publish_text_end,
    )

    # Run Stages 1-4 synchronously (reuse existing logic)
    # The existing generate_reply already runs these; we extract the
    # intermediate state and take over Stage 5.
    result = generate_reply(
        db,
        container,
        conversation_id=conversation_id,
        content=content,
        diary_ids=diary_ids,
        user_id=user_id,
        auto_retrieve=auto_retrieve,
        trace_id=trace_id,
    )

    # If streaming is disabled or crisis was detected, return non-streaming
    if result.is_crisis:
        # Already short-circuited to safe response in generate_reply
        # Just publish the full text as a single TEXT_DELTA
        if trace_id:
            await publish_reply_start(trace_id, intent="crisis_signal")
            await publish_text_delta(trace_id, result.reply_text)
            await publish_reply_end(trace_id)
        return result

    # Stage 5: Re-generate the final reply via streaming
    # NOTE: This re-runs the LLM call. A future optimization (P0 follow-up)
    # would refactor generate_reply to expose the pre-final-reply state
    # so we only call the LLM once.
    from app.services.ai.conversation_loop import ConversationLoop
    from app.shared.streaming_safety import StreamingSafetyGuard
    from app.shared.crisis_guard import CrisisGuard

    # ... (streaming logic using ConversationLoop.run_streaming)
    # Publish events as they come from the generator
```

**重要说明**：这一步的具体实现取决于 `generate_reply` 的内部结构。实施时需要阅读 `conversation_ai_service.py` 的完整代码，提取 Stage 1-4 的状态，并在 Stage 5 接管为流式。如果 `generate_reply` 的耦合度较高难以提取，退而求其次：先调用 `generate_reply` 完成所有阶段（包括持久化），然后额外做一次流式生成覆盖 reply_text。这会多一次 LLM 调用，但 P0 优先保证正确性，P6 性能优化阶段再合并为一次调用。

- [ ] **Step 3: 在 conversation.py 添加流式端点**

在 `server/app/api/v1/conversation.py` 中，在现有 `send_message` 之后添加：

```python
from app.config import get_settings


@router.post(
    "/{conversation_id}/messages/stream",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def send_message_streaming(
    conversation_id: str,
    body: SendMessageRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
    http_request: Request,
) -> dict[str, Any]:
    """Streaming endpoint — returns trace_id, content streams via SSE.

    Frontend subscribes to SSE at /api/v1/dev/traces/{trace_id}/stream
    to receive TEXT_DELTA / RETRACT / REPLY_END events.

    Falls back to synchronous behavior when ``STREAMING_ENABLED=false``.
    """
    settings = get_settings()
    if not settings.streaming_enabled:
        # Fallback: behave like the synchronous endpoint
        return {"streaming": False, "trace_id": http_request.headers.get("X-Trace-Id", "")}

    conv = conversation_service.get_conversation(
        db, user_id=str(user.id), conversation_id=conversation_id
    )
    if conv is None:
        raise ConversationNotFoundError(conversation_id=conversation_id)

    trace_id = http_request.headers.get("X-Trace-Id") or str(uuid.uuid4())

    # Launch streaming generation as a background task
    import asyncio
    asyncio.create_task(
        conversation_ai_service.generate_reply_streaming(
            db,
            container,
            conversation_id=conversation_id,
            content=body.content,
            diary_ids=body.diary_ids,
            user_id=str(user.id),
            auto_retrieve=body.auto_retrieve,
            trace_id=trace_id,
        )
    )

    return {"streaming": True, "trace_id": trace_id}
```

- [ ] **Step 4: 手动验证端点可访问**

```bash
cd server && python -c "from app.api.v1.conversation import router; print([r.path for r in router.routes])"
```

Expected: 包含 `/{conversation_id}/messages/stream`

- [ ] **Step 5: 提交**

```bash
cd server && git add app/api/v1/conversation.py app/services/conversation_ai_service.py app/config.py
git commit -m "feat(api): add streaming message endpoint with STREAMING_ENABLED flag

POST /conversations/{id}/messages/stream returns {trace_id} immediately.
Content streams via existing SSE at /dev/traces/{trace_id}/stream.
Falls back to sync when STREAMING_ENABLED=false.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: 前端 useStreamingReply composable

**Files:**
- Create: `src/shared/composables/useStreamingReply.ts`
- Create: `src/shared/composables/__tests__/useStreamingReply.spec.ts`

- [ ] **Step 1: 编写 composable 的失败测试**

创建 `src/shared/composables/__tests__/useStreamingReply.spec.ts`：

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { useStreamingReply } from '@/shared/composables/useStreamingReply'

// Mock EventSource
class MockEventSource {
  listeners: Record<string, ((e: MessageEvent) => void)> = {}
  url: string

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, cb: (e: MessageEvent) => void) {
    this.listeners[type] = cb
  }

  close() {
    MockEventSource.instances = MockEventSource.instances.filter((i) => i !== this)
  }

  // Test helpers
  emit(type: string, data: unknown) {
    if (this.listeners[type]) {
      this.listeners[type](new MessageEvent(type, { data: JSON.stringify(data) }))
    }
  }

  static instances: MockEventSource[] = []
}

describe('useStreamingReply', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts in idle status', () => {
    const { status, replyText } = useStreamingReply()
    expect(status.value).toBe('idle')
    expect(replyText.value).toBe('')
  })

  it('accumulates TEXT_DELTA events into replyText via RAF', async () => {
    const { replyText, connect, onTextDelta } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.emit('text_delta', { text: 'Hello' })
    mockES.emit('text_delta', { text: ' ' })
    mockES.emit('text_delta', { text: 'world' })

    // Flush RAF
    await vi.runAllTimersAsync()
    await nextTick()

    expect(replyText.value).toBe('Hello world')
  })

  it('replaces replyText on RETRACT event', async () => {
    const { replyText, status, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.emit('text_delta', { text: '部分内容' })
    await vi.runAllTimersAsync()

    mockES.emit('retract', { reason: 'crisis', replacement: '安全模板' })
    await vi.runAllTimersAsync()

    expect(replyText.value).toBe('安全模板')
    expect(status.value).toBe('retracted')
  })

  it('transitions to done on REPLY_END', async () => {
    const { status, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.emit('reply_end', { citations: [], usage: {} })
    await vi.runAllTimersAsync()

    expect(status.value).toBe('done')
  })

  it('watchdog resets to idle after 120s without events', async () => {
    const { status, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.emit('reply_start', { intent: 'casual_chat' })

    // Advance 120s
    vi.advanceTimersByTime(121_000)
    await nextTick()

    expect(status.value).toBe('idle')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

```bash
npm test -- useStreamingReply
```

Expected: FAIL — 无法导入 `useStreamingReply`

- [ ] **Step 3: 创建 useStreamingReply.ts**

创建 `src/shared/composables/useStreamingReply.ts`：

```typescript
import { ref, onUnmounted, type Ref } from 'vue'
import { resolveBackendBaseUrl } from '@/shared/composables/useBackend'

export interface StreamingReplyState {
  replyText: Ref<string>
  status: Ref<'idle' | 'streaming' | 'done' | 'retracted'>
  citations: Ref<Array<Record<string, unknown>>>
}

const WATCHDOG_TIMEOUT_MS = 120_000 // 120s no-event → idle
const TEXT_DELTA_EVENT = 'text_delta'
const REPLY_START_EVENT = 'reply_start'
const REPLY_END_EVENT = 'reply_end'
const RETRACT_EVENT = 'retract'

export function useStreamingReply(): StreamingReplyState & {
  connect: (sseUrl: string) => void
  disconnect: () => void
  reset: () => void
} {
  const replyText = ref('')
  const status = ref<'idle' | 'streaming' | 'done' | 'retracted'>('idle')
  const citations = ref<Array<Record<string, unknown>>>([])

  let eventSource: EventSource | null = null
  let pendingTokens = ''
  let rafId: number | null = null
  let watchdogTimer: ReturnType<typeof setTimeout> | null = null

  function flushTokens() {
    if (pendingTokens) {
      replyText.value += pendingTokens
      pendingTokens = ''
    }
    rafId = null
  }

  function resetWatchdog() {
    if (watchdogTimer) clearTimeout(watchdogTimer)
    watchdogTimer = setTimeout(() => {
      // 120s without events → force back to idle
      if (status.value === 'streaming') {
        flushTokens() // flush any pending tokens first
        status.value = 'idle'
      }
    }, WATCHDOG_TIMEOUT_MS)
  }

  function scheduleFlush() {
    if (rafId === null) {
      rafId = requestAnimationFrame(flushTokens)
    }
  }

  function connect(sseUrl: string) {
    disconnect()
    replyText.value = ''
    status.value = 'streaming'
    pendingTokens = ''

    eventSource = new EventSource(sseUrl)

    eventSource.addEventListener(REPLY_START_EVENT, () => {
      resetWatchdog()
    })

    eventSource.addEventListener(TEXT_DELTA_EVENT, (e: MessageEvent) => {
      const { text } = JSON.parse(e.data) as { text: string }
      pendingTokens += text
      scheduleFlush()
      resetWatchdog()
    })

    eventSource.addEventListener(REPLY_END_EVENT, (e: MessageEvent) => {
      const data = JSON.parse(e.data) as {
        citations?: Array<Record<string, unknown>>
        usage?: Record<string, number>
        error?: string
      }
      flushTokens()
      citations.value = data.citations || []
      status.value = 'done'
      if (watchdogTimer) clearTimeout(watchdogTimer)
      eventSource?.close()
      eventSource = null
    })

    eventSource.addEventListener(RETRACT_EVENT, (e: MessageEvent) => {
      const { replacement } = JSON.parse(e.data) as { replacement: string }
      pendingTokens = ''
      if (rafId !== null) {
        cancelAnimationFrame(rafId)
        rafId = null
      }
      replyText.value = replacement
      status.value = 'retracted'
      if (watchdogTimer) clearTimeout(watchdogTimer)
    })

    eventSource.onerror = () => {
      // Connection error during streaming
      if (status.value === 'streaming') {
        flushTokens()
        status.value = 'done' // treat as done with partial content
      }
    }

    resetWatchdog()
  }

  function disconnect() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
    if (watchdogTimer) {
      clearTimeout(watchdogTimer)
      watchdogTimer = null
    }
    pendingTokens = ''
  }

  function reset() {
    disconnect()
    replyText.value = ''
    status.value = 'idle'
    citations.value = []
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    replyText,
    status,
    citations,
    connect,
    disconnect,
    reset,
  }
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
npm test -- useStreamingReply
```

Expected: 5 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/shared/composables/useStreamingReply.ts src/shared/composables/__tests__/useStreamingReply.spec.ts
git commit -m "feat(frontend): add useStreamingReply composable with RAF + watchdog + RETRACT

RAF batches high-frequency TEXT_DELTA events.
120s watchdog forces idle on no-event timeout.
RETRACT replaces entire replyText (not append).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: chat store 集成流式路径

**Files:**
- Modify: `src/stores/chat.ts`
- Modify: `src/shared/api/conversation.ts`

- [ ] **Step 1: 在 conversation.ts 添加 sendMessageStreaming 函数**

在 `src/shared/api/conversation.ts` 末尾追加：

```typescript
export interface SendMessageStreamingResponse {
  streaming: boolean
  trace_id: string
}

export async function sendMessageStreaming(
  conversationId: string,
  payload: SendMessagePayload,
  traceId?: string,
): Promise<SendMessageStreamingResponse> {
  const client = await getHttpClient()
  const headers: Record<string, string> = {}
  if (traceId) headers['X-Trace-Id'] = traceId
  const { data } = await client.post<SendMessageStreamingResponse>(
    `/api/v1/conversations/${conversationId}/messages/stream`,
    payload,
    { headers },
  )
  return data
}
```

- [ ] **Step 2: 在 chat store 集成流式路径**

修改 `src/stores/chat.ts`，在 `send` 函数中添加流式分支。在文件顶部添加导入：

```typescript
import { sendMessageStreaming } from '@/shared/api/conversation'
import { useStreamingReply } from '@/shared/composables/useStreamingReply'
import { resolveBackendBaseUrl } from '@/shared/composables/useBackend'
```

在 store 内部添加流式状态：

```typescript
const streamingReply = useStreamingReply()
const streamingEnabled = ref(false) // controlled by settings
```

修改 `send` 函数，添加流式分支：

```typescript
async function send(content: string): Promise<boolean> {
  const convId = activeConversationId.value
  if (!convId) return false
  sending.value = true
  error.value = null

  try {
    if (streamingEnabled.value) {
      // Streaming path
      const traceId = crypto.randomUUID()
      const result = await sendMessageStreaming(convId, {
        content,
        diary_ids: pinnedDiaryIds.value,
        auto_retrieve: autoRetrieve.value,
      }, traceId)

      if (result.streaming && result.trace_id) {
        // Connect SSE
        const baseURL = await resolveBackendBaseUrl()
        streamingReply.connect(`${baseURL}/api/v1/dev/traces/${result.trace_id}/stream`)

        // Add placeholder reply message that will be updated by streaming
        const placeholderReply: ChatMessage = {
          id: 'streaming-placeholder',
          conversation_id: convId,
          role: 'assistant',
          content: '',
          created_at: new Date().toISOString(),
        }
        const userMsg: ChatMessage = {
          id: 'temp-user',
          conversation_id: convId,
          role: 'user',
          content,
          created_at: new Date().toISOString(),
        }
        messages.value = [...messages.value, userMsg, placeholderReply]

        // Watch streaming reply text and update placeholder
        // (This will be handled by the component via reactive binding)
        return true
      }
    }

    // Non-streaming fallback (existing path)
    const result = await sendMessage(convId, {
      content,
      diary_ids: pinnedDiaryIds.value,
      auto_retrieve: autoRetrieve.value,
    })
    messages.value = [...messages.value, result.message, result.reply]
    return true
  } catch (err) {
    error.value = formatApiError(err, '发送消息失败')
    return false
  } finally {
    sending.value = false
  }
}
```

在返回对象中添加流式状态：

```typescript
return {
  // ... existing
  streamingReply,
  streamingEnabled,
  // ...
}
```

- [ ] **Step 3: 运行现有前端测试确认不退化**

```bash
npm test
```

Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add src/stores/chat.ts src/shared/api/conversation.ts
git commit -m "feat(chat): integrate streaming path into chat store with fallback

sendMessageStreaming returns trace_id; chat store connects SSE.
Non-streaming fallback preserved when streamingEnabled=false.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: 集成测试与 eval 闸门验证

**Files:**
- Modify: `server/tests/e2e/test_full_flow.py` (扩展)

- [ ] **Step 1: 编写端到端流式测试**

在 `server/tests/e2e/test_full_flow.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_streaming_endpoint_returns_trace_id(test_client, auth_headers):
    """流式端点应返回 trace_id 供前端建立 SSE 连接。"""
    # First create a conversation
    conv_resp = test_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
    )
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["id"]

    # Send a message via streaming endpoint
    response = test_client.post(
        f"/api/v1/conversations/{conv_id}/messages/stream",
        json={"content": "你好", "auto_retrieve": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "trace_id" in data
    assert "streaming" in data
```

- [ ] **Step 2: 运行 e2e 测试**

```bash
cd server && python -m pytest tests/e2e/test_full_flow.py::test_streaming_endpoint_returns_trace_id -v
```

Expected: PASS

- [ ] **Step 3: 运行现有 eval 基线确保不退化**

```bash
cd server && python -m pytest tests/eval/ -v --timeout=300
```

Expected: 所有 eval 测试在基线容差内（RAG Recall@5 容差 0.05）

- [ ] **Step 4: 运行完整测试套件**

```bash
cd server && python -m pytest tests/unit/ -v --tb=short
```

Expected: 全部 PASS

```bash
npm test
```

Expected: 全部 PASS

- [ ] **Step 5: lint 检查**

```bash
cd server && python -m ruff check app/ tests/ && python -m mypy app/
npm run lint
```

Expected: 无错误

- [ ] **Step 6: 提交**

```bash
cd server && git add tests/e2e/test_full_flow.py
git commit -m "test(e2e): add streaming endpoint integration test

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## 验证总结

完成所有任务后，验证以下端到端流程：

1. **环境变量开启流式**：在 `.env` 中设置 `STREAMING_ENABLED=true`
2. **启动后端**：`make dev-api`
3. **启动前端**：`make dev-web`
4. **场景二对话测试**：发送一条消息，观察：
   - 低风险意图（闲聊）：token 级打字机效果
   - 情感敏感意图：首段缓冲后流式
   - 危机关键词：直接返回安全模板（非流式）
5. **关闭流式**：设置 `STREAMING_ENABLED=false`，确认回退到同步行为
6. **eval 基线**：`make eval-rag` 和 `make eval-generation` 不退化

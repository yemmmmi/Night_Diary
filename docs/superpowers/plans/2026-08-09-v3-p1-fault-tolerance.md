# V3 P1: 多层容错体系 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 P0 流式链路的异常兜底，保证无论发生什么异常，前端永不永久卡死，后端资源永不泄漏。

**Architecture:** 三个核心组件：(1) `TaskRegistry` 管理 background task 生命周期，(2) `generate_reply_streaming` 的 try/finally 包裹保证必然发出 REPLY_END，(3) `PersistentMCPConnection` 修复 session 闭包 bug。可选的 abort 端点作为低优先级增强。

**Tech Stack:** Python 3.11+ / FastAPI / asyncio / Vue 3 / TypeScript

**Spec:** `docs/superpowers/specs/2026-08-09-v3-p1-fault-tolerance.md`

---

## 文件结构

### 新建文件（后端）
| 文件 | 职责 |
|------|------|
| `server/app/shared/task_registry.py` | `TaskRegistry` — background task 生命周期管理 |
| `server/app/services/ai/mcp_persistent.py` | `PersistentMCPConnection` — MCP 持久连接，修复 session 闭包 bug |
| `server/tests/unit/shared/test_task_registry.py` | TaskRegistry 单元测试 |
| `server/tests/unit/services/ai/test_mcp_persistent.py` | PersistentMCPConnection 单元测试 |
| `server/tests/e2e/test_streaming_resilience.py` | 容错集成测试 |

### 修改文件（后端）
| 文件 | 改动 |
|------|------|
| `server/app/services/conversation_ai_service.py` | `generate_reply_streaming` 添加 try/finally 包裹（_terminating_reply 保证） |
| `server/app/api/v1/conversation.py` | `send_message_streaming` 改用 TaskRegistry 替代简单 set；新增 abort 端点（可选） |

### 可选修改文件（前端）
| 文件 | 改动 |
|------|------|
| `src/shared/composables/useStreamingReply.ts` | 新增 `abort()` 函数 + 10s 确认定时器 |

---

## Task 1: TaskRegistry — background task 生命周期管理

**Files:**
- Create: `server/app/shared/task_registry.py`
- Create: `server/tests/unit/shared/test_task_registry.py`

- [ ] **Step 1: 编写 TaskRegistry 的失败测试**

创建 `server/tests/unit/shared/test_task_registry.py`：

```python
"""Unit tests for TaskRegistry — background task lifecycle management."""

import asyncio

import pytest

from app.shared.task_registry import TaskRegistry


@pytest.mark.asyncio
async def test_register_and_auto_cleanup_on_done():
    """register 的 task 完成后应自动从注册表移除。"""
    registry = TaskRegistry()

    async def dummy_task():
        await asyncio.sleep(0.01)

    task = asyncio.create_task(dummy_task())
    registry.register("trace-1", task)

    assert "trace-1" in registry.get_active_trace_ids()

    await task  # 等待完成

    # done_callback 异步触发，需要让事件循环跑一轮
    await asyncio.sleep(0.01)
    assert "trace-1" not in registry.get_active_trace_ids()


@pytest.mark.asyncio
async def test_cancel_existing_task():
    """cancel 应取消指定 trace_id 的 task 并等待其终止。"""
    registry = TaskRegistry()

    async def long_task():
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(long_task())
    registry.register("trace-2", task)

    cancelled = await registry.cancel("trace-2")
    assert cancelled is True
    assert task.cancelled() or task.done()
    assert "trace-2" not in registry.get_active_trace_ids()


@pytest.mark.asyncio
async def test_cancel_nonexistent_returns_false():
    """cancel 不存在的 trace_id 应返回 False。"""
    registry = TaskRegistry()
    cancelled = await registry.cancel("nonexistent")
    assert cancelled is False


@pytest.mark.asyncio
async def test_cancel_already_done_task_returns_false():
    """cancel 已完成的 task 应返回 False（无需取消）。"""
    registry = TaskRegistry()

    async def quick_task():
        pass

    task = asyncio.create_task(quick_task())
    registry.register("trace-3", task)
    await task
    await asyncio.sleep(0.01)  # let done_callback run

    cancelled = await registry.cancel("trace-3")
    assert cancelled is False


@pytest.mark.asyncio
async def test_cancel_all():
    """cancel_all 应取消所有活跃 task。"""
    registry = TaskRegistry()

    async def long_task():
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            raise

    task1 = asyncio.create_task(long_task())
    task2 = asyncio.create_task(long_task())
    registry.register("trace-a", task1)
    registry.register("trace-b", task2)

    assert len(registry.get_active_trace_ids()) == 2

    await registry.cancel_all()

    assert len(registry.get_active_trace_ids()) == 0
    assert task1.cancelled() or task1.done()
    assert task2.cancelled() or task2.done()


@pytest.mark.asyncio
async def test_cancel_times_out_gracefully():
    """cancel 时 task 若不响应取消（超 5s），cancel 仍应返回 True。"""
    registry = TaskRegistry()

    async def unresponsive_task():
        try:
            # 捕获 CancelledError 但不退出（模拟不听话的 task）
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            await asyncio.sleep(0.05)
            raise

    task = asyncio.create_task(unresponsive_task())
    registry.register("trace-stubborn", task)

    # task 会快速完成，这里主要验证 cancel 不卡死
    cancelled = await registry.cancel("trace-stubborn")
    # task 可能已完成或被取消，都算 True
    assert cancelled is True
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/shared/test_task_registry.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.shared.task_registry'`

- [ ] **Step 3: 创建 task_registry.py**

创建 `server/app/shared/task_registry.py`：

```python
"""TaskRegistry — lifecycle management for streaming background tasks.

Replaces the simple ``set[asyncio.Task]`` used in P0's ``conversation.py``
with a structured registry that:

1. Maps ``trace_id`` → ``asyncio.Task`` so tasks can be cancelled by ID
   (needed for the abort endpoint and for ``_terminating_reply`` tests).
2. Auto-removes completed tasks via ``add_done_callback``.
3. Supports ``cancel_all()`` for graceful application shutdown.

This is the P1 layer-5 "task finalization" mechanism — it ensures no
background task is orphaned when the server shuts down or when a client
disconnects mid-stream.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Timeout (seconds) for waiting a cancelled task to actually terminate.
#: A task that ignores ``CancelledError`` longer than this is abandoned
#: (the registry stops tracking it, but the OS-level coroutine may leak —
#: that's acceptable for P1; P5 will add hard process-level cancellation).
_CANCEL_TIMEOUT_S = 5.0


class TaskRegistry:
    """Registry mapping ``trace_id`` → background ``asyncio.Task``.

    Not thread-safe — must be used from the main event loop. All methods
    are coroutines (or sync getters) intended to run on the loop.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def register(self, trace_id: str, task: asyncio.Task[Any]) -> None:
        """Register *task* under *trace_id*.

        When the task completes (normally or by exception), it is
        automatically removed from the registry via ``add_done_callback``.
        """
        self._tasks[trace_id] = task

        def _on_done(_t: asyncio.Task[Any]) -> None:
            # pop only if the same task is still registered (avoid clobbering
            # a re-registered task with the same trace_id)
            if self._tasks.get(trace_id) is _t:
                self._tasks.pop(trace_id, None)

        task.add_done_callback(_on_done)

    async def cancel(self, trace_id: str) -> bool:
        """Cancel the task registered under *trace_id*.

        Returns ``True`` if a live task was found and cancelled,
        ``False`` if the trace_id is unknown or the task already finished.
        """
        task = self._tasks.get(trace_id)
        if task is None or task.done():
            return False

        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=_CANCEL_TIMEOUT_S)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Task didn't terminate within timeout — log and abandon.
            logger.warning(
                "Task trace_id=%s did not terminate within %.1fs after cancel; "
                "abandoning (may leak at OS level)",
                trace_id,
                _CANCEL_TIMEOUT_S,
            )
        return True

    def get_active_trace_ids(self) -> list[str]:
        """Return all currently-registered trace_ids (for debugging/monitoring)."""
        return list(self._tasks.keys())

    async def cancel_all(self) -> None:
        """Cancel every active task. Used during graceful application shutdown."""
        trace_ids = list(self._tasks.keys())
        for trace_id in trace_ids:
            await self.cancel(trace_id)


# ── Application-level singleton ──────────────────────────────────────

_registry: TaskRegistry | None = None


def get_task_registry() -> TaskRegistry:
    """Return the process-global ``TaskRegistry`` singleton.

    Lazily initialised so the event loop is only touched when first
    accessed (importing this module does not create one).
    """
    global _registry
    if _registry is None:
        _registry = TaskRegistry()
    return _registry
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/shared/test_task_registry.py -v
```

Expected: 6 个测试全部 PASS

- [ ] **Step 5: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/shared/task_registry.py tests/unit/shared/test_task_registry.py
.venv\Scripts\python.exe -m mypy app/shared/task_registry.py
```

- [ ] **Step 6: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/shared/task_registry.py server/tests/unit/shared/test_task_registry.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(task-registry): add TaskRegistry for background task lifecycle management

Maps trace_id -> asyncio.Task with auto-cleanup on done and cancel_all()
for graceful shutdown. Replaces P0's simple set with structured registry.
This is the P1 layer-5 task finalization mechanism."
```

---

## Task 2: conversation.py 集成 TaskRegistry

**Files:**
- Modify: `server/app/api/v1/conversation.py`

- [ ] **Step 1: 阅读现有 send_message_streaming 实现**

完整阅读 `server/app/api/v1/conversation.py`，重点关注：
- 第 129-187 行的 `send_message_streaming` 函数
- 第 182-185 行的 `_background_streaming_tasks.add(task)` / `task.add_done_callback(_background_streaming_tasks.discard)` 逻辑
- 文件顶部的 import 块

- [ ] **Step 2: 修改 send_message_streaming 改用 TaskRegistry**

在 `server/app/api/v1/conversation.py` 中：

**顶部添加 import**（在现有 import 块中）：
```python
from app.shared.task_registry import get_task_registry
```

**替换第 170-185 行**（`task = asyncio.create_task(...)` + `_background_streaming_tasks.add/discard`）：

找到这段代码：
```python
    task = asyncio.create_task(
        conversation_ai_service.generate_reply_streaming(
            db=db,
            container=container,
            conversation_id=conversation_id,
            content=body.content,
            diary_ids=body.diary_ids or [],
            user_id=str(user.id),
            auto_retrieve=body.auto_retrieve,
            trace_id=trace_id,
        )
    )
    # Keep a strong reference so the task is not garbage-collected, and
    # auto-discard on completion to avoid unbounded set growth.
    _background_streaming_tasks.add(task)
    task.add_done_callback(_background_streaming_tasks.discard)
```

替换为：
```python
    task = asyncio.create_task(
        conversation_ai_service.generate_reply_streaming(
            db=db,
            container=container,
            conversation_id=conversation_id,
            content=body.content,
            diary_ids=body.diary_ids or [],
            user_id=str(user.id),
            auto_retrieve=body.auto_retrieve,
            trace_id=trace_id,
        )
    )
    # Register with TaskRegistry for lifecycle management (cancel on abort,
    # auto-cleanup on done, cancel_all on shutdown).
    get_task_registry().register(trace_id, task)
```

**保留 `_background_streaming_tasks` 的定义**（如果它还被其他地方引用），但在 `send_message_streaming` 中不再使用它。如果搜索全文件确认 `_background_streaming_tasks` 不再被引用，可以删除它的定义。

- [ ] **Step 3: 添加 abort 端点（可选，但在这一步做最合适）**

在 `send_message_streaming` 之后添加：

```python
@router.post(
    "/{conversation_id}/messages/abort",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
)
async def abort_message(
    conversation_id: str,
    body: dict[str, Any],
    user: CurrentUserDep,
) -> dict[str, Any]:
    """Abort a streaming reply by trace_id.

    Returns ``{"cancelled": bool}`` indicating whether a live task was
    found and cancelled. The cancelled task's ``_terminating_reply``
    finally-block will still emit ``REPLY_END(error="cancelled")`` so the
    frontend can exit the streaming state cleanly.
    """
    trace_id = body.get("trace_id", "")
    if not trace_id:
        return {"cancelled": False}

    cancelled = await get_task_registry().cancel(trace_id)
    return {"cancelled": cancelled}
```

注意：这个端点需要 `body` 参数的 schema。检查项目是否用 Pydantic schema，如果是，创建一个 `AbortRequest` schema。如果直接用 `dict[str, Any]` 可以工作（FastAPI 允许），就用 dict。

- [ ] **Step 4: 运行现有 API 测试确认不退化**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/api/test_conversation_routes.py -v
.venv\Scripts\python.exe -m pytest tests/e2e/test_streaming_endpoint.py -v
```

Expected: 全部 PASS（现有端点行为不变）

- [ ] **Step 5: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/api/v1/conversation.py
.venv\Scripts\python.exe -m mypy app/api/v1/conversation.py
```

- [ ] **Step 6: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/api/v1/conversation.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "refactor(api): use TaskRegistry for streaming task lifecycle

Replace simple set with TaskRegistry in send_message_streaming.
Add optional POST /messages/abort endpoint for client-initiated cancel."
```

---

## Task 3: _terminating_reply 保证

**Files:**
- Modify: `server/app/services/conversation_ai_service.py`
- Modify: `server/tests/unit/services/test_conversation_ai_service.py`

- [ ] **Step 1: 阅读现有 generate_reply_streaming 实现**

完整阅读 `server/app/services/conversation_ai_service.py` 第 545-622 行的 `generate_reply_streaming` 函数。理解它的四步流程：
1. Step 1（第 584-595 行）：调用 `generate_reply()` 同步生成
2. Step 2（第 597-599 行）：无 trace_id 时早返回
3. Step 3（第 601-607 行）：危机时单 chunk 发布
4. Step 4（第 609-622 行）：非危机时分 chunk 流式发布

- [ ] **Step 2: 编写 _terminating_reply 的失败测试**

在 `server/tests/unit/services/test_conversation_ai_service.py` 末尾追加：

```python
import asyncio
from unittest.mock import patch, MagicMock

import pytest

from app.shared.streaming_events import StreamingEventType
from app.shared.trace_event_bus import get_event_bus


@pytest.mark.asyncio
async def test_generate_reply_streaming_emits_reply_end_on_llm_failure(
    stub_container, db_session
):
    """generate_reply_streaming 在 generate_reply 抛异常时必须发出 REPLY_END。"""
    from app.services import conversation_ai_service
    from app.services.conversation_ai_service import generate_reply_streaming

    trace_id = "test-trace-llm-failure"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    # Mock generate_reply 抛出异常
    with patch.object(
        conversation_ai_service,
        "generate_reply",
        side_effect=RuntimeError("LLM crashed"),
    ):
        # 不应该抛出——异常应被 try/finally 捕获
        await generate_reply_streaming(
            db=db_session,
            container=stub_container,
            conversation_id="test-conv",
            content="你好",
            diary_ids=[],
            user_id="test-user",
            trace_id=trace_id,
        )

    # 收集所有事件
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    await bus.unsubscribe(trace_id, queue)

    # 必须有 REPLY_END 事件（带 error 标记）
    reply_ends = [e for e in events if e["type"] == StreamingEventType.REPLY_END]
    assert len(reply_ends) >= 1
    assert reply_ends[0]["error"] is not None
    assert "LLM crashed" in reply_ends[0]["error"]


@pytest.mark.asyncio
async def test_generate_reply_streaming_emits_reply_end_on_cancel(
    stub_container, db_session
):
    """generate_reply_streaming 在被 cancel 时必须发出 REPLY_END(error='cancelled')。"""
    from app.services import conversation_ai_service
    from app.services.conversation_ai_service import generate_reply_streaming

    trace_id = "test-trace-cancel"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    # Mock generate_reply 被 CancelledError 中断
    async def slow_generate_reply(*args, **kwargs):
        await asyncio.sleep(0.1)
        raise asyncio.CancelledError()

    with patch.object(
        conversation_ai_service,
        "generate_reply",
        side_effect=slow_generate_reply,
    ):
        task = asyncio.create_task(
            generate_reply_streaming(
                db=db_session,
                container=stub_container,
                conversation_id="test-conv",
                content="你好",
                diary_ids=[],
                user_id="test-user",
                trace_id=trace_id,
            )
        )
        await asyncio.sleep(0.02)  # let it start
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    await bus.unsubscribe(trace_id, queue)

    # 必须有 REPLY_END 事件
    reply_ends = [e for e in events if e["type"] == StreamingEventType.REPLY_END]
    assert len(reply_ends) >= 1


@pytest.mark.asyncio
async def test_generate_reply_streaming_normal_path_single_reply_end(
    stub_container, db_session, mock_safe_result
):
    """正常路径只发一次 REPLY_END，不重复。"""
    from app.services import conversation_ai_service
    from app.services.conversation_ai_service import generate_reply_streaming

    trace_id = "test-trace-normal"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    mock_result = MagicMock()
    mock_result.is_crisis = False
    mock_result.reply_text = "你好呀"
    mock_result.token_info = {"total_tokens_used": 10}

    with patch.object(
        conversation_ai_service,
        "generate_reply",
        return_value=mock_result,
    ):
        await generate_reply_streaming(
            db=db_session,
            container=stub_container,
            conversation_id="test-conv",
            content="你好",
            diary_ids=[],
            user_id="test-user",
            trace_id=trace_id,
        )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    await bus.unsubscribe(trace_id, queue)

    reply_ends = [e for e in events if e["type"] == StreamingEventType.REPLY_END]
    assert len(reply_ends) == 1  # 只有一个，不重复
```

注意：`stub_container`、`db_session`、`mock_safe_result` 这些 fixture 需要参考现有测试文件 `test_conversation_ai_service.py` 的 conftest。如果 fixture 不存在，在测试中直接用 MagicMock 构造足够 stub。

- [ ] **Step 3: 运行测试确认失败**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/test_conversation_ai_service.py -v -k "streaming"
```

Expected: FAIL — 现有 `generate_reply_streaming` 无 try/finally，异常时不会发 REPLY_END

- [ ] **Step 4: 修改 generate_reply_streaming 添加 try/finally**

在 `server/app/services/conversation_ai_service.py` 中，找到 `generate_reply_streaming` 函数（第 545-622 行），**完全替换**它的函数体为以下带 try/finally 的版本。

**重要**：只替换函数体（从 `"""Streaming version..."""` docstring 开始到函数结束），不改变函数签名。

```python
async def generate_reply_streaming(
    db: Session,
    container: ServiceContainer,
    *,
    conversation_id: str,
    content: str,
    diary_ids: list[int],
    user_id: str,
    auto_retrieve: bool = True,
    crisis_guard: CrisisGuard | None = None,
    trace_id: str = "",
) -> None:
    """Streaming version of :func:`generate_reply` with _terminating_reply guarantee.

    Wraps the P0 simulated-streaming logic in a try/finally that guarantees
    a ``REPLY_END`` event is always published — even when the synchronous
    :func:`generate_reply` raises, or when the task is cancelled by the
    abort endpoint. This is the P1 layer-2 "agent terminating reply"
    mechanism: the frontend can never be left stuck in ``streaming`` state.

    Three paths through the try block:

    1. **Normal**: generate_reply succeeds → chunked publish → REPLY_END
    2. **CancelledError**: task cancelled by abort → REPLY_END(error="cancelled")
    3. **Other Exception**: any other failure → REPLY_END(error=str(exc))

    The ``finally`` block is a safety net: if the except branch itself
    raises before publishing REPLY_END, the finally publishes a
    "finalized" fallback. A ``reply_end_sent`` flag prevents duplicates
    on the normal path.
    """
    from app.shared.streaming_events import (
        publish_reply_end,
        publish_reply_start,
        publish_text_delta,
        publish_text_end,
    )

    reply_started = False
    reply_end_sent = False

    try:
        # ── Step 1: Full synchronous pipeline ──
        result = generate_reply(
            db,
            container,
            conversation_id=conversation_id,
            content=content,
            diary_ids=diary_ids,
            user_id=user_id,
            auto_retrieve=auto_retrieve,
            crisis_guard=crisis_guard,
            trace_id=trace_id or None,
        )

        # ── Step 2: No trace_id → nothing to publish to ──
        if not trace_id:
            return

        # ── Step 3: Crisis → single chunk ──
        if result.is_crisis:
            await publish_reply_start(trace_id, intent="crisis_signal")
            reply_started = True
            await publish_text_delta(trace_id, result.reply_text)
            await publish_text_end(trace_id)
            await publish_reply_end(trace_id)
            reply_end_sent = True
            return

        # ── Step 4: Non-crisis → simulated streaming ──
        await publish_reply_start(trace_id, intent="streaming")
        reply_started = True

        chunks = _split_into_chunks(result.reply_text, chunk_size=20)
        for chunk in chunks:
            await publish_text_delta(trace_id, chunk)
            await asyncio.sleep(0.02)

        await publish_text_end(trace_id)
        await publish_reply_end(
            trace_id,
            citations=[],
            usage=result.token_info or {},
        )
        reply_end_sent = True

    except asyncio.CancelledError:
        # User-initiated abort — clean shutdown, no fallback text needed.
        if reply_started and not reply_end_sent and trace_id:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="cancelled")
            reply_end_sent = True
        raise  # Propagate CancelledError to the task registry

    except Exception as exc:
        logger.exception("Streaming reply failed: %s", exc)
        if trace_id:
            if not reply_started:
                with contextlib.suppress(Exception):
                    await publish_reply_start(trace_id, intent="error")
                reply_started = True
            with contextlib.suppress(Exception):
                await publish_text_delta(trace_id, FALLBACK_FEEDBACK)
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error=str(exc))
            reply_end_sent = True

    finally:
        # Ultimate fallback: if an exception path itself failed before
        # publishing REPLY_END, ensure it happens here.
        if trace_id and reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="finalized")
```

确保文件顶部有 `import asyncio` 和 `import contextlib`。同时确保 `FALLBACK_FEEDBACK` 已从 `app.services.ai.prompts` 导入（搜索现有 import 确认）。

- [ ] **Step 5: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/test_conversation_ai_service.py -v -k "streaming"
```

Expected: PASS（3 个新测试 + 已有 streaming 测试）

- [ ] **Step 6: 确认现有测试不退化**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/test_conversation_ai_service.py -v
```

Expected: 全部 PASS

- [ ] **Step 7: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/services/conversation_ai_service.py
.venv\Scripts\python.exe -m mypy app/services/conversation_ai_service.py
```

- [ ] **Step 8: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/services/conversation_ai_service.py server/tests/unit/services/test_conversation_ai_service.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(streaming): add _terminating_reply guarantee to generate_reply_streaming

try/finally ensures REPLY_END is always emitted:
- Normal path: single REPLY_END (reply_end_sent flag prevents dupes)
- CancelledError: REPLY_END(error='cancelled'), re-raise to propagate
- Other Exception: REPLY_END(error=str(exc)) + fallback text
- finally: ultimate fallback if except branch itself fails

This is the P1 layer-2 agent terminating reply mechanism."
```

---

## Task 4: PersistentMCPConnection — 修复 session 闭包 bug

**Files:**
- Create: `server/app/services/ai/mcp_persistent.py`
- Create: `server/tests/unit/services/ai/test_mcp_persistent.py`
- Modify: `server/app/services/ai/tool_factory.py`

- [ ] **Step 1: 阅读现有 _load_mcp_tools 实现**

完整阅读 `server/app/services/ai/tool_factory.py` 第 264-321 行的 `_load_mcp_tools` 函数，理解 session 闭包 bug 的确切位置（`async with` 退出后 session 失效）。

- [ ] **Step 2: 编写 PersistentMCPConnection 的失败测试**

创建 `server/tests/unit/services/ai/test_mcp_persistent.py`：

```python
"""Unit tests for PersistentMCPConnection — fixes the session closure bug."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.mcp_persistent import PersistentMCPConnection


@pytest.mark.asyncio
async def test_connect_initializes_session():
    """connect() 应建立 session 并调用 initialize()。"""
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_session.call_tool = AsyncMock()
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm), \
         patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()

        mock_cm.__aenter__.assert_called_once()
        mock_session.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_call_tool_after_connect():
    """connect 后调用 call_tool 应委托给 session。"""
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_resp = MagicMock()
    mock_session.call_tool = AsyncMock(return_value=mock_resp)
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm), \
         patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()

        result = await conn.call_tool("search", {"query": "test"})
        mock_session.call_tool.assert_called_once_with("search", {"query": "test"})
        assert result is mock_resp


@pytest.mark.asyncio
async def test_call_tool_before_connect_raises():
    """未 connect 就调用 call_tool 应抛 RuntimeError。"""
    conn = PersistentMCPConnection("http://localhost:8081/sse")
    with pytest.raises(RuntimeError, match="Not connected"):
        await conn.call_tool("search", {})


@pytest.mark.asyncio
async def test_close_releases_session():
    """close() 应关闭 session 和 context manager。"""
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_session.call_tool = AsyncMock()
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm), \
         patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()
        await conn.close()

        mock_session.close.assert_called_once()
        mock_cm.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_close_is_idempotent():
    """多次调用 close() 不应抛异常。"""
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm), \
         patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()
        await conn.close()
        await conn.close()  # 不抛


@pytest.mark.asyncio
async def test_session_survives_after_async_context_exit():
    """核心 bug 修复：session 在 connect 后必须持续可用。

    这是 tool_factory.py 中 async with 退出后 session 失效 bug 的
    回归测试。
    """
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_session.call_tool = AsyncMock(return_value=MagicMock())
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm), \
         patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()

        # 模拟 tool_factory.py 的场景：发现工具后，多次调用
        for i in range(3):
            await conn.call_tool(f"tool_{i}", {})

        # session.call_tool 应被调用 3 次，全部成功
        assert mock_session.call_tool.call_count == 3
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/ai/test_mcp_persistent.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ai.mcp_persistent'`

- [ ] **Step 4: 创建 mcp_persistent.py**

创建 `server/app/services/ai/mcp_persistent.py`：

```python
"""PersistentMCPConnection — MCP client connection that survives beyond async with.

Fixes the session-closure bug in ``tool_factory.py::_load_mcp_tools`` where
``async with sse_client(...)`` exits (closing the session) but the generated
tool closures still reference the now-dead session.

``PersistentMCPConnection`` lifts the session lifecycle to object scope:
``connect()`` enters the async context manually and keeps it open;
``close()`` exits it. Between the two, ``call_tool()`` and ``list_tools()``
reuse the same live session.

Not a reconnect manager — if the connection drops mid-session, calls will
fail (the caller's layer-1 tool error handling kicks in and returns an
ERROR chunk to the model). Automatic reconnect is deferred to P5 or until
MCP is actually enabled in production.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy imports so this module doesn't hard-fail if mcp isn't installed.
# The imports happen inside connect(), and ImportError is caught there.
try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    _MCP_AVAILABLE = True
except ImportError:
    ClientSession = None  # type: ignore[assignment,misc]
    sse_client = None  # type: ignore[assignment]
    _MCP_AVAILABLE = False


class PersistentMCPConnection:
    """Persistent MCP client connection.

    Call ``connect()`` once at startup, then ``call_tool()`` / ``list_tools()``
    as needed, then ``close()`` at shutdown.

    All methods are coroutines and must run on the same event loop.
    """

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._session: ClientSession | None = None
        # sse_client() returns an async context manager; we hold it so we
        # can __aexit__ on close().
        self._cm: Any = None

    async def connect(self) -> None:
        """Establish the connection and initialize the session.

        Raises ``ImportError`` if the ``mcp`` package is not installed.
        Raises the underlying transport error if the endpoint is unreachable.
        """
        if not _MCP_AVAILABLE:
            raise ImportError("mcp package not installed; cannot connect")

        # Exit any previous connection first (idempotent connect).
        if self._session is not None:
            await self.close()

        self._cm = sse_client(self._endpoint)
        read, write = await self._cm.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.initialize()
        logger.info("MCP connected to %s", self._endpoint)

    async def list_tools(self) -> Any:
        """List available tools on the connected server."""
        if self._session is None:
            raise RuntimeError("Not connected; call connect() first")
        return await self._session.list_tools()

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Call a tool on the connected server."""
        if self._session is None:
            raise RuntimeError("Not connected; call connect() first")
        return await self._session.call_tool(name, args)

    async def close(self) -> None:
        """Close the connection. Safe to call multiple times."""
        with contextlib.suppress(Exception):
            if self._session is not None:
                await self._session.close()
        self._session = None

        if self._cm is not None:
            with contextlib.suppress(Exception):
                await self._cm.__aexit__(None, None, None)
        self._cm = None
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/ai/test_mcp_persistent.py -v
```

Expected: 6 个测试全部 PASS

- [ ] **Step 6: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/services/ai/mcp_persistent.py tests/unit/services/ai/test_mcp_persistent.py
.venv\Scripts\python.exe -m mypy app/services/ai/mcp_persistent.py
```

- [ ] **Step 7: 提交（PersistentMCPConnection 本身）**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/services/ai/mcp_persistent.py server/tests/unit/services/ai/test_mcp_persistent.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(mcp): add PersistentMCPConnection to fix session closure bug

Lifts MCP ClientSession lifecycle out of async with so it survives
beyond the discovery context. This is the foundation for the
tool_factory.py refactor in the next commit."
```

---

## Task 5: tool_factory.py 改用 PersistentMCPConnection

**Files:**
- Modify: `server/app/services/ai/tool_factory.py`
- Modify: `server/tests/unit/services/ai/test_mcp_tool_factory.py`

- [ ] **Step 1: 阅读现有 _load_mcp_tools 和 build_tool_map_with_mcp**

完整阅读 `server/app/services/ai/tool_factory.py` 的：
- `_load_mcp_tools`（第 264-321 行）
- `build_tool_map_with_mcp`（第 324 行开始）

- [ ] **Step 2: 改造 _load_mcp_tools**

将 `_load_mcp_tools` 函数（第 264-321 行）替换为使用 `PersistentMCPConnection` 的版本：

```python
def _load_mcp_tools(endpoint: str) -> dict[str, ToolFn]:
    """Load tools from an external MCP server endpoint.

    Uses :class:`PersistentMCPConnection` to keep the MCP session alive
    beyond the initial discovery call (fixes the P0 session-closure bug
    where ``async with`` exit killed the session that tool closures
    captured).

    Best-effort: returns empty dict on failure (import error, connection
    error, or tool listing error).

    Args:
        endpoint: MCP server SSE endpoint URL (e.g. http://localhost:8081/sse).
    """
    import asyncio

    from app.services.ai.mcp_persistent import PersistentMCPConnection

    async def _discover_and_create() -> dict[str, ToolFn]:
        tools: dict[str, ToolFn] = {}
        conn = PersistentMCPConnection(endpoint)
        try:
            await conn.connect()
            result = await conn.list_tools()

            for mcp_tool in result.tools:
                tool_name = mcp_tool.name

                def make_fn(name: str, connection: PersistentMCPConnection) -> Any:
                    async def _call_async(**kwargs: Any) -> str:
                        resp = await connection.call_tool(name, kwargs)
                        texts = [c.text for c in resp.content if hasattr(c, "text")]
                        return "\n".join(texts) if texts else str(resp)

                    def _call_sync(**kwargs: Any) -> str:
                        try:
                            return asyncio.run(_call_async(**kwargs))
                        except Exception as exc:
                            logger.error("MCP tool %s failed: %s", name, exc)
                            return f"MCP tool {name} error: {exc}"

                    return _call_sync

                tools[tool_name] = make_fn(tool_name, conn)
                logger.info("Loaded MCP tool: %s from %s", tool_name, endpoint)

            # NOTE: We intentionally do NOT close conn here. The connection
            # must stay alive for subsequent tool calls. It leaks for the
            # lifetime of the process — acceptable because MCP endpoints
            # are static config, and P5 will add a proper connection pool.
            # If tools is empty, close to avoid leaking a useless connection.
            if not tools:
                await conn.close()

        except ImportError as exc:
            logger.warning("mcp package not installed; cannot load MCP tools from %s: %s", endpoint, exc)
        except Exception as exc:
            logger.error("Failed to load MCP tools from %s: %s", endpoint, exc)
            with contextlib.suppress(Exception):
                await conn.close()

        return tools

    try:
        return asyncio.run(_discover_and_create())
    except Exception as exc:
        logger.error("MCP tool loading from %s failed: %s", endpoint, exc)
        return {}
```

注意：
- 关键变化是 `make_fn` 现在接收 `connection` 参数（显式捕获，不靠闭包）
- 连接在工具创建后**不关闭**（工具需要它）
- 只有加载失败或没有工具时才关闭连接

- [ ] **Step 3: 运行现有 MCP 测试确认不退化**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/ai/test_mcp_tool_factory.py -v
```

现有测试应该仍然通过，因为：
- `mcp_endpoints=None` 或空列表时不走新代码路径
- 真正连接 MCP 的测试（如 `mcp_endpoints=["http://localhost:9999/sse"]`）mock 了连接，需要检查 mock 是否与新代码兼容。如果测试失败，更新 mock 以适配 `PersistentMCPConnection`。

- [ ] **Step 4: 如果现有测试失败，更新 mock**

阅读 `test_mcp_tool_factory.py` 中 `mcp_endpoints=["http://localhost:8081/sse"]` 相关的测试，理解它们如何 mock MCP。如果 mock 的是 `sse_client` 和 `ClientSession` 的 `async with`，需要改为 mock `PersistentMCPConnection`。

具体策略：在测试中 patch `app.services.ai.tool_factory.PersistentMCPConnection`，让它返回一个 MagicMock，其 `connect()` / `list_tools()` / `call_tool()` 返回预设值。

- [ ] **Step 5: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/services/ai/tool_factory.py
.venv\Scripts\python.exe -m mypy app/services/ai/tool_factory.py
```

- [ ] **Step 6: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/services/ai/tool_factory.py server/tests/unit/services/ai/test_mcp_tool_factory.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "refactor(tool-factory): use PersistentMCPConnection to fix session bug

_load_mcp_tools now captures PersistentMCPConnection explicitly in each
tool closure instead of relying on an async-with session that dies after
discovery. MCP tool calls now work after the initial discovery context
exits."
```

---

## Task 6: 容错集成测试

**Files:**
- Create: `server/tests/e2e/test_streaming_resilience.py`

- [ ] **Step 1: 阅读现有 e2e 测试模式**

阅读 `server/tests/e2e/test_streaming_endpoint.py` 和 `server/tests/e2e/conftest.py`，理解 `test_client`、`auth_headers`、`e2e_client` 等 fixture 的用法。

- [ ] **Step 2: 创建容错集成测试**

创建 `server/tests/e2e/test_streaming_resilience.py`：

```python
"""Integration tests for P1 fault tolerance mechanisms.

Tests that streaming replies are resilient to failures:
- LLM crash still produces a REPLY_END event
- abort endpoint cancels an active streaming task
"""

import pytest


def test_streaming_endpoint_returns_trace_id(e2e_client, auth_headers):
    """冒烟测试：流式端点应返回 trace_id（P0 行为不退化）。"""
    # 先创建会话
    conv_resp = e2e_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"title": "resilience-test"},
    )
    assert conv_resp.status_code in (200, 201)
    conv_id = conv_resp.json()["id"]

    # 调用流式端点
    response = e2e_client.post(
        f"/api/v1/conversations/{conv_id}/messages/stream",
        json={"content": "你好", "auto_retrieve": False},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "trace_id" in data
    assert "streaming" in data


def test_abort_endpoint_returns_cancelled_false_for_unknown_trace(
    e2e_client, auth_headers
):
    """abort 不存在的 trace_id 应返回 cancelled=false。"""
    conv_resp = e2e_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"title": "abort-test"},
    )
    conv_id = conv_resp.json()["id"]

    response = e2e_client.post(
        f"/api/v1/conversations/{conv_id}/messages/abort",
        json={"trace_id": "nonexistent-trace"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cancelled"] is False


def test_abort_endpoint_returns_cancelled_false_for_empty_trace_id(
    e2e_client, auth_headers
):
    """abort 空 trace_id 应返回 cancelled=false。"""
    conv_resp = e2e_client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"title": "abort-empty-test"},
    )
    conv_id = conv_resp.json()["id"]

    response = e2e_client.post(
        f"/api/v1/conversations/{conv_id}/messages/abort",
        json={"trace_id": ""},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cancelled"] is False
```

注意：真正测试"LLM 崩溃后前端收到 REPLY_END"需要 mock LLM 并验证 SSE 事件流，这在 e2e 层比较复杂。上面三个测试覆盖了 abort 端点的基本行为。对于 LLM 崩溃场景，Task 3 的单元测试已经覆盖了。

- [ ] **Step 3: 运行测试**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/e2e/test_streaming_resilience.py -v
```

Expected: PASS

- [ ] **Step 4: 运行完整后端测试套件确认不退化**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/ tests/e2e/ -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 5: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check tests/e2e/test_streaming_resilience.py
```

- [ ] **Step 6: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/tests/e2e/test_streaming_resilience.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "test(e2e): add streaming resilience integration tests

Tests: streaming endpoint smoke test (no regression), abort endpoint
returns cancelled=false for unknown/empty trace_id."
```

---

## Task 7: 前端 abort（可选，低优先级）

**Files:**
- Modify: `src/shared/composables/useStreamingReply.ts`
- Modify: `src/shared/api/conversation.ts`

> **注意**：这个任务是可选的。如果时间有限，可以跳过直接到 Task 8 验证。120s 看门狗已经兜底"前端不卡死"。

- [ ] **Step 1: 在 conversation.ts 添加 abortStreaming 函数**

在 `src/shared/api/conversation.ts` 末尾添加：

```typescript
export async function abortStreaming(
  conversationId: string,
  traceId: string,
): Promise<{ cancelled: boolean }> {
  const client = await getHttpClient()
  const { data } = await client.post<{ cancelled: boolean }>(
    `/api/v1/conversations/${conversationId}/messages/abort`,
    { trace_id: traceId },
  )
  return data
}
```

- [ ] **Step 2: 在 useStreamingReply 添加 abort 函数**

在 `src/shared/composables/useStreamingReply.ts` 中：

**顶部添加常量**：
```typescript
const ABORT_CONFIRM_TIMEOUT_MS = 10_000 // 10s abort 确认超时
```

**在函数内添加变量**：
```typescript
let abortConfirmTimer: ReturnType<typeof setTimeout> | null = null
```

**添加 abort 函数**（在 `disconnect` 之前）：
```typescript
function abort(conversationId: string, traceId: string): void {
  if (status.value !== 'streaming') return

  // 发送 abort 请求（fire-and-forget，响应不重要）
  abortStreaming(conversationId, traceId).catch(() => {
    // 网络错误忽略——10s 确认定时器会兜底
  })

  // 启动 10s 确认定时器
  if (abortConfirmTimer) clearTimeout(abortConfirmTimer)
  abortConfirmTimer = setTimeout(() => {
    // 10s 内未收到 REPLY_END → 强制回 idle
    flushTokens()
    status.value = 'idle'
    abortConfirmTimer = null
  }, ABORT_CONFIRM_TIMEOUT_MS)
}
```

**在 REPLY_END 事件处理中清除 abortConfirmTimer**（在 `eventSource.addEventListener(REPLY_END_EVENT, ...)` 回调内）：
```typescript
// 清除 abort 确认定时器（如果有的话）
if (abortConfirmTimer) {
  clearTimeout(abortConfirmTimer)
  abortConfirmTimer = null
}
```

**在 disconnect 中清除 abortConfirmTimer**：
```typescript
function disconnect(): void {
  // ... 现有逻辑 ...
  if (abortConfirmTimer) {
    clearTimeout(abortConfirmTimer)
    abortConfirmTimer = null
  }
}
```

**在返回对象中添加 abort**：
```typescript
return {
  replyText,
  status,
  citations,
  connect,
  disconnect,
  reset,
  abort,
}
```

**更新 StreamingReplyReturn 接口**：
```typescript
export interface StreamingReplyReturn {
  replyText: Ref<string>
  status: Ref<StreamingReplyStatus>
  citations: Ref<Array<Record<string, unknown>>>
  connect: (sseUrl: string) => void
  disconnect: () => void
  reset: () => void
  abort: (conversationId: string, traceId: string) => void
}
```

- [ ] **Step 3: 运行前端测试确认不退化**

```bash
cd d:\work\night_diary_v2
npx vitest run
```

Expected: 全部 PASS

- [ ] **Step 4: lint 检查**

```bash
cd d:\work\night_diary_v2
npx eslint src/shared/composables/useStreamingReply.ts src/shared/api/conversation.ts
```

- [ ] **Step 5: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add src/shared/composables/useStreamingReply.ts src/shared/api/conversation.ts
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(frontend): add abort() to useStreamingReply with 10s confirm timeout

abort() sends POST /messages/abort and starts a 10s timer. If REPLY_END
is not received within 10s, forces status back to idle. Optional P1
enhancement — 120s watchdog already covers stuck UI."
```

---

## Task 8: 最终验证

- [ ] **Step 1: 运行完整后端测试**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/ tests/e2e/ -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 2: 运行完整前端测试**

```bash
cd d:\work\night_diary_v2
npx vitest run
```

Expected: 全部 PASS

- [ ] **Step 3: 后端 lint**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/ tests/
.venv\Scripts\python.exe -m mypy app/
```

- [ ] **Step 4: 前端 lint**

```bash
cd d:\work\night_diary_v2
npx eslint src/ --ext .ts,.vue
```

- [ ] **Step 5: 尝试运行 eval 基线**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/eval/ -v --timeout=300 -x
```

如果 eval 测试需要 LLM API key 而无法运行，记录原因并跳过。

- [ ] **Step 6: 汇总验证结果**

（无需提交，直接在对话中汇报各套件通过情况）

---

## 验证总结

完成所有任务后，验证以下端到端场景：

1. **TaskRegistry 生效**：多个流式请求并发，`get_task_registry().get_active_trace_ids()` 正确反映活跃任务
2. **_terminating_reply 保证**：手动 kill LLM 进程模拟崩溃，前端仍收到 `REPLY_END(error=...)`
3. **abort 端点工作**：发送 abort 请求，后端 task 在 5s 内终止，前端收到 `REPLY_END(error="cancelled")`
4. **MCP session 存活**：配置一个 MCP endpoint，发现工具后多次调用，不出现 session closed 错误
5. **现有 eval 基线不退化**

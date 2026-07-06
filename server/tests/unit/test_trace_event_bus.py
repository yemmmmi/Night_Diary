"""Unit tests for ``app.shared.trace_event_bus.TraceEventBus``.

Covers the six required scenarios:
- subscribe_and_publish: 订阅后发布事件能收到
- unsubscribe_removes_queue: 取消订阅后 key 被清理
- publish_to_no_subscribers: 无订阅者时不报错
- queue_full_drops_event: Queue size=1 时第二个事件被丢弃不阻塞
- multiple_subscribers: 两个订阅者都能收到
- cleanup_removes_empty: cleanup 删除空列表
"""

from __future__ import annotations

import pytest

from app.shared.trace_event_bus import TraceEventBus


@pytest.mark.asyncio
async def test_subscribe_and_publish() -> None:
    """订阅后发布事件能收到: a subscribed queue should receive the event."""
    bus = TraceEventBus()
    trace_id = "trace-001"

    queue = await bus.subscribe(trace_id)
    event = {"type": "span", "name": "step-1"}
    await bus.publish(trace_id, event)

    # put_nowait is synchronous, so the event is already enqueued.
    assert queue.qsize() == 1
    received = queue.get_nowait()
    assert received == event


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue() -> None:
    """取消订阅后 key 被清理: after unsubscribe the trace_id key is deleted."""
    bus = TraceEventBus()
    trace_id = "trace-002"

    queue = await bus.subscribe(trace_id)
    assert trace_id in bus._subscribers

    await bus.unsubscribe(trace_id, queue)

    # The list became empty → the key should have been deleted.
    assert trace_id not in bus._subscribers


@pytest.mark.asyncio
async def test_publish_to_no_subscribers() -> None:
    """无订阅者时不报错: publishing to a trace_id with no subscribers is a no-op."""
    bus = TraceEventBus()

    # No subscribers registered for this trace_id — should be a silent no-op.
    await bus.publish("trace-no-sub", {"type": "span"})


@pytest.mark.asyncio
async def test_queue_full_drops_event() -> None:
    """Queue size=1 时第二个事件被丢弃不阻塞: overflow event dropped, not blocked."""
    bus = TraceEventBus(max_queue_size=1)
    trace_id = "trace-full"

    queue = await bus.subscribe(trace_id)

    first = {"type": "span", "seq": 1}
    second = {"type": "span", "seq": 2}

    # First event fills the queue (capacity == 1).
    await bus.publish(trace_id, first)
    # Second event overflows → dropped with a warning, no blocking.
    await bus.publish(trace_id, second)

    assert queue.qsize() == 1
    assert queue.get_nowait() == first


@pytest.mark.asyncio
async def test_multiple_subscribers() -> None:
    """两个订阅者都能收到: each subscriber receives the fanned-out event."""
    bus = TraceEventBus()
    trace_id = "trace-multi"

    queue_a = await bus.subscribe(trace_id)
    queue_b = await bus.subscribe(trace_id)

    event = {"type": "span", "name": "fan-out"}
    await bus.publish(trace_id, event)

    assert queue_a.qsize() == 1
    assert queue_b.qsize() == 1
    assert queue_a.get_nowait() == event
    assert queue_b.get_nowait() == event


@pytest.mark.asyncio
async def test_cleanup_removes_empty() -> None:
    """cleanup 删除空列表: cleanup() deletes the entire subscriber list."""
    bus = TraceEventBus()
    trace_id = "trace-cleanup"

    await bus.subscribe(trace_id)
    assert trace_id in bus._subscribers

    await bus.cleanup(trace_id)

    assert trace_id not in bus._subscribers

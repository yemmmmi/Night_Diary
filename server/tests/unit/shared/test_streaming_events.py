"""Unit tests for streaming event publishing helpers."""

import pytest

from app.shared.streaming_events import (
    StreamingEventType,
    publish_reply_end,
    publish_reply_start,
    publish_retract,
    publish_text_delta,
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

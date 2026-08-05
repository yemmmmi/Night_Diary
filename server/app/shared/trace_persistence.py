"""Trace 持久化和事件推送辅助函数 (best-effort, 失败仅记日志)."""

from __future__ import annotations

import contextlib
import json
import logging
from typing import TYPE_CHECKING

from app.shared.pipeline_trace import PipelineTrace

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.shared.pipeline_trace import TraceSpan

logger = logging.getLogger(__name__)


def persist_trace(db: Session, trace: PipelineTrace, ref_id: str | None = None) -> None:
    """持久化 trace 到 pipeline_traces 表. best-effort, 失败仅记日志不中断."""
    try:
        from app.infrastructure.models.pipeline_trace import PipelineTraceRow

        trace_dict = trace.to_dict()
        row = PipelineTraceRow(
            trace_id=trace.trace_id,
            scenario=trace.scenario,
            user_id=trace.user_id,
            status=trace.status,
            started_at=trace.started_at,
            ended_at=trace.ended_at,
            duration_ms=trace.duration_ms,
            span_count=len(trace.spans),
            ref_id=ref_id,
            trace_json=json.dumps(trace_dict, ensure_ascii=False, default=str),
        )
        db.add(row)
        db.commit()
    except Exception as e:
        logger.warning("Failed to persist trace %s: %s", trace.trace_id, e)
        with contextlib.suppress(Exception):
            db.rollback()


async def publish_trace_complete(trace: PipelineTrace) -> None:
    """通过 EventBus 推送 trace_complete 事件 (异步版, 供 SSE handler 使用)。best-effort。"""
    try:
        from app.shared.trace_event_bus import get_event_bus

        event_bus = get_event_bus()
        await event_bus.publish(
            trace.trace_id,
            {
                "type": "trace_complete",
                "trace_id": trace.trace_id,
                "trace": {
                    "status": trace.status,
                    "duration_ms": trace.duration_ms,
                    "span_count": len(trace.spans),
                },
            },
        )
    except Exception as e:
        logger.warning("Failed to publish trace_complete: %s", e)


def publish_trace_complete_sync(trace: PipelineTrace) -> None:
    """Synchronous trace_complete push.

    Calling asyncio.run() on a sync endpoint (thread-pool thread) crashes the
    process on Windows (ProactorEventLoop conflict). TraceEventBus.publish only
    uses put_nowait internally (a synchronous op), so no event loop is needed —
    inline that logic here.
    """
    try:
        from contextlib import suppress

        from app.shared.trace_event_bus import get_event_bus

        event_bus = get_event_bus()
        event = {
            "type": "trace_complete",
            "trace_id": trace.trace_id,
            "trace": {
                "status": trace.status,
                "duration_ms": trace.duration_ms,
                "span_count": len(trace.spans),
            },
        }
        queues = event_bus._subscribers.get(trace.trace_id, [])
        for queue in queues:
            with suppress(Exception):
                queue.put_nowait(event)
    except Exception as e:
        logger.warning("Failed to publish trace_complete (sync): %s", e)


async def publish_span_complete(trace: PipelineTrace, span: TraceSpan) -> None:
    """Push a span_complete event through the EventBus. Best-effort."""
    try:
        from app.shared.trace_event_bus import get_event_bus

        event_bus = get_event_bus()
        await event_bus.publish(
            trace.trace_id,
            {
                "type": "span_complete",
                "trace_id": trace.trace_id,
                "span": span.to_dict(),
            },
        )
    except Exception as e:
        logger.warning("Failed to publish span_complete: %s", e)


def publish_span_complete_sync(trace: PipelineTrace, span: TraceSpan) -> None:
    """Sync wrapper for ``publish_span_complete`` — call from worker threads.

    Uses ``TraceEventBus.publish_from_thread`` so the fan-out is scheduled on
    the main event loop via ``call_soon_threadsafe``, avoiding the cross-loop
    race where ``asyncio.run`` creates a temporary loop that can't wake up
    the SSE subscriber's ``await queue.get()``.
    """
    try:
        from app.shared.trace_event_bus import get_event_bus

        event_bus = get_event_bus()
        event_bus.publish_from_thread(
            trace.trace_id,
            {
                "type": "span_complete",
                "trace_id": trace.trace_id,
                "span": span.to_dict(),
            },
        )
    except Exception as e:
        logger.warning("Failed to publish span_complete: %s", e)


def publish_trace_complete_sync(trace: PipelineTrace) -> None:
    """Sync wrapper for ``publish_trace_complete`` — call from worker threads."""
    try:
        from app.shared.trace_event_bus import get_event_bus

        event_bus = get_event_bus()
        event_bus.publish_from_thread(
            trace.trace_id,
            {
                "type": "trace_complete",
                "trace_id": trace.trace_id,
                "trace": {
                    "status": trace.status,
                    "duration_ms": trace.duration_ms,
                    "span_count": len(trace.spans),
                },
            },
        )
    except Exception as e:
        logger.warning("Failed to publish trace_complete: %s", e)

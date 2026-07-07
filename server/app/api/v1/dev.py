"""Developer-mode API routes for pipeline trace inspection.

Provides endpoints to list, inspect, delete, and live-stream pipeline
traces, plus aggregate statistics and middleware health checks. These
routes are intended for developer/debugging use and do not require
authentication.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func

from app.api.deps import DbDep
from app.infrastructure.models.pipeline_trace import PipelineTraceRow
from app.shared.pipeline_trace import get_trace
from app.shared.trace_event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dev", tags=["dev"])

# SSE heartbeat interval (seconds). If no events arrive within this
# window, a heartbeat comment is sent to keep the connection alive.
_SSE_HEARTBEAT_INTERVAL = 30.0


def _format_sse(event: dict) -> str:
    """Format a dict as an SSE message string.

    Uses ``default=str`` so non-JSON-serialisable values (datetime, etc.)
    are stringified instead of raising.
    """
    event_type = event.get("type", "message")
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {data}\n\n"


# ── Middleware availability helpers ──────────────────────────────────────


def _check_redis() -> bool:
    """Return ``True`` if the Redis client is connected."""
    try:
        from app.infrastructure.redis_client import is_redis_available

        return is_redis_available()
    except Exception:
        return False


def _check_neo4j() -> bool:
    """Return ``True`` if the Neo4j driver is connected."""
    try:
        from app.infrastructure.entity_graph import is_neo4j_available

        return is_neo4j_available()
    except Exception:
        return False


def _check_langgraph() -> bool:
    """Return ``True`` if LangGraph is importable."""
    try:
        from app.services.ai.conversation_graph import LANGGRAPH_AVAILABLE

        return bool(LANGGRAPH_AVAILABLE)
    except Exception:
        return False


def _check_rq() -> bool:
    """Return ``True`` if the RQ task queue is initialised.

    RQ availability is inferred from the ``_redis_queue`` singleton in
    ``app.infrastructure.task_queue`` — when Redis is unavailable or the
    ``rq`` package is not installed, this stays ``None`` and tasks fall
    back to daemon threads.
    """
    try:
        from app.infrastructure.task_queue import _redis_queue

        return _redis_queue is not None
    except Exception:
        return False


# ── Trace list ───────────────────────────────────────────────────────────


def _row_to_summary(row: PipelineTraceRow) -> dict[str, Any]:
    """Convert a ``PipelineTraceRow`` to a summary dict (without ``trace_json``)."""
    return {
        "trace_id": row.trace_id,
        "scenario": row.scenario,
        "user_id": row.user_id,
        "status": row.status,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "duration_ms": row.duration_ms,
        "span_count": row.span_count,
        "ref_id": row.ref_id,
    }


@router.get("/traces")
def list_traces(
    db: DbDep,
    scenario: str | None = Query(None, description="Filter by scenario"),
    status_filter: str | None = Query(
        None, alias="status", description="Filter by status"
    ),
    ref_id: str | None = Query(None, description="Filter by ref_id"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
) -> dict[str, Any]:
    """List pipeline traces with optional filters and pagination."""
    query = db.query(PipelineTraceRow)

    if scenario:
        query = query.filter(PipelineTraceRow.scenario == scenario)
    if status_filter:
        query = query.filter(PipelineTraceRow.status == status_filter)
    if ref_id:
        query = query.filter(PipelineTraceRow.ref_id == ref_id)

    total = query.count()

    offset = (page - 1) * page_size
    rows = (
        query.order_by(desc(PipelineTraceRow.created_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )
    items = [_row_to_summary(r) for r in rows]
    return {"items": items, "total": total}


# ── Trace detail ─────────────────────────────────────────────────────────


@router.get("/traces/{trace_id}")
def get_trace_detail(trace_id: str, db: DbDep) -> dict[str, Any]:
    """Return a single trace's full JSON payload."""
    row = db.get(PipelineTraceRow, trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    if row.trace_json:
        try:
            return json.loads(row.trace_json)
        except (json.JSONDecodeError, TypeError):
            # Fall back to summary if the JSON is corrupt.
            return _row_to_summary(row)
    return _row_to_summary(row)


# ── Trace delete ─────────────────────────────────────────────────────────


@router.delete(
    "/traces/{trace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_trace(trace_id: str, db: DbDep) -> Response:
    """Delete a pipeline trace by ID."""
    row = db.get(PipelineTraceRow, trace_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── SSE stream ───────────────────────────────────────────────────────────


@router.get("/traces/{trace_id}/stream")
async def stream_trace(
    trace_id: str, request: Request, db: DbDep
) -> StreamingResponse:
    """Server-Sent Events stream for a live trace.

    First pushes any already-completed spans (from the in-memory active
    trace or the persisted DB row), then subscribes to the ``TraceEventBus``
    for live events until the trace completes or the client disconnects.

    A heartbeat is sent every 30 seconds of inactivity to prevent proxy
    timeouts.
    """
    # Gather initial state from the DB while the session is valid.
    initial_events: list[dict[str, Any]] = []
    trace_already_complete = False

    # 1. Active in-memory trace (same context — covers the rare case where
    #    the SSE consumer shares the contextvar with the producer).
    active_trace = get_trace()
    if active_trace is not None and active_trace.trace_id == trace_id:
        for span in active_trace.spans:
            initial_events.append(
                {
                    "type": "span_complete",
                    "trace_id": trace_id,
                    "span": span.to_dict(),
                }
            )
        if active_trace.status in ("completed", "error"):
            initial_events.append(
                {
                    "type": "trace_complete",
                    "trace_id": trace_id,
                    "trace": active_trace.to_dict(),
                }
            )
            trace_already_complete = True

    # 2. Persisted DB row — push completed spans for traces in progress,
    #    or the full payload if the trace already finished.
    if not trace_already_complete:
        row = db.get(PipelineTraceRow, trace_id)
        if row is not None and row.trace_json:
            try:
                persisted = json.loads(row.trace_json)
                if row.status in ("completed", "error"):
                    initial_events.append(
                        {
                            "type": "trace_complete",
                            "trace_id": trace_id,
                            "trace": persisted,
                        }
                    )
                    trace_already_complete = True
                else:
                    for span in persisted.get("spans", []):
                        initial_events.append(
                            {
                                "type": "span_complete",
                                "trace_id": trace_id,
                                "span": span,
                            }
                        )
            except (json.JSONDecodeError, TypeError):
                pass

    return StreamingResponse(
        _trace_event_generator(
            trace_id, request, initial_events, trace_already_complete
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _trace_event_generator(
    trace_id: str,
    request: Request,
    initial_events: list[dict[str, Any]],
    trace_already_complete: bool,
) -> AsyncGenerator[str, None]:
    """Async generator yielding SSE-formatted trace events.

    1. Yields all ``initial_events`` (already-completed spans).
    2. If the trace is not yet complete, subscribes to the
       ``TraceEventBus`` and streams live events.
    3. Sends a heartbeat on 30s of inactivity.
    4. Closes after a ``trace_complete`` event or client disconnect.
    """
    # 1. Push already-completed spans.
    for event in initial_events:
        yield _format_sse(event)

    # If the trace already finished, close the stream immediately.
    if trace_already_complete:
        return

    # 2. Subscribe to the EventBus for live events.
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)
    try:
        while True:
            # Check for client disconnect before waiting.
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=_SSE_HEARTBEAT_INTERVAL,
                )
            except asyncio.TimeoutError:
                # Send heartbeat to keep the connection alive.
                yield _format_sse(
                    {"type": "heartbeat", "trace_id": trace_id}
                )
                continue

            yield _format_sse(event)

            # Close the stream once the trace is finalised.
            if event.get("type") == "trace_complete":
                break
    finally:
        await bus.unsubscribe(trace_id, queue)


# ── Stats ────────────────────────────────────────────────────────────────


@router.get("/stats")
def get_dev_stats(db: DbDep) -> dict[str, Any]:
    """Aggregate statistics across all pipeline traces."""
    total_traces = db.query(PipelineTraceRow).count()

    # Group by scenario.
    scenario_rows = (
        db.query(PipelineTraceRow.scenario, func.count(PipelineTraceRow.trace_id))
        .group_by(PipelineTraceRow.scenario)
        .all()
    )
    by_scenario = {scenario: count for scenario, count in scenario_rows}

    # Average duration (rows without duration_ms are ignored by AVG).
    avg_duration = db.query(func.avg(PipelineTraceRow.duration_ms)).scalar()
    avg_duration_ms = float(avg_duration) if avg_duration is not None else 0.0

    # Error count.
    error_count = (
        db.query(PipelineTraceRow)
        .filter(PipelineTraceRow.status == "error")
        .count()
    )

    return {
        "total_traces": total_traces,
        "by_scenario": by_scenario,
        "avg_duration_ms": avg_duration_ms,
        "error_count": error_count,
    }


# ── Middleware status ────────────────────────────────────────────────────


@router.get("/middleware-status")
def get_middleware_status() -> dict[str, Any]:
    """Health-check for infrastructure middleware."""
    return {
        "redis": _check_redis(),
        "neo4j": _check_neo4j(),
        "langgraph": _check_langgraph(),
        "rq": _check_rq(),
    }

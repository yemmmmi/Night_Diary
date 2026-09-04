"""Persist MCP tool calls to ``mcp_call_logs`` (mirrors llm_call_tracer)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models.mcp_call_log import McpCallLogRow

logger = logging.getLogger(__name__)

SNAPSHOT_MAX_BYTES = 2048


@dataclass(frozen=True, slots=True)
class McpCallRecord:
    user_id: str
    trace_id: str | None
    span_id: str
    endpoint_alias: str
    transport: str
    tool_name: str
    raw_tool_name: str
    status: str
    duration_ms: float
    error_message: str | None
    arguments_snapshot: str
    result_snapshot: str


def _truncate(value: str) -> str:
    return value[:SNAPSHOT_MAX_BYTES]


class McpCallTracer:
    """Append-only writer — best-effort: failures never break tool calls."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, entry: McpCallRecord) -> None:
        try:
            with self._session_factory() as session:
                session.add(
                    McpCallLogRow(
                        id=uuid.uuid4().hex,
                        user_id=entry.user_id,
                        trace_id=entry.trace_id,
                        span_id=entry.span_id,
                        endpoint_alias=entry.endpoint_alias,
                        transport=entry.transport,
                        tool_name=entry.tool_name,
                        raw_tool_name=entry.raw_tool_name,
                        status=entry.status,
                        duration_ms=entry.duration_ms,
                        error_message=entry.error_message,
                        arguments_snapshot=_truncate(entry.arguments_snapshot),
                        result_snapshot=_truncate(entry.result_snapshot),
                        created_at=datetime.now(UTC).timestamp(),
                    )
                )
                session.commit()
        except Exception as exc:
            logger.warning("mcp_call_logs write failed: %s", exc)


def list_calls(
    db: Session,
    *,
    endpoint: str | None = None,
    status: str | None = None,
    user_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Query call logs with filters + pagination (Dev API read path)."""
    query = db.query(McpCallLogRow)
    if endpoint:
        query = query.filter(McpCallLogRow.endpoint_alias == endpoint)
    if status:
        query = query.filter(McpCallLogRow.status == status)
    if user_id:
        query = query.filter(McpCallLogRow.user_id == user_id)
    total = query.count()
    rows = (
        query.order_by(desc(McpCallLogRow.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "trace_id": row.trace_id,
            "endpoint_alias": row.endpoint_alias,
            "transport": row.transport,
            "tool_name": row.tool_name,
            "raw_tool_name": row.raw_tool_name,
            "status": row.status,
            "duration_ms": row.duration_ms,
            "error_message": row.error_message,
            "arguments_snapshot": row.arguments_snapshot,
            "result_snapshot": row.result_snapshot,
            "created_at": row.created_at,
        }
        for row in rows
    ], total

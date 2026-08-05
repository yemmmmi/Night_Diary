"""基于 SQLite 的 LLMCallTracer 实现。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models.llm_call_log import LlmCallLogRow
from app.shared.tracing import LLMCallRecord


class SqliteLLMCallTracer:
    """将每次 LLM 调用持久化到 ``llm_call_logs`` 表，用于成本/延迟审查。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, entry: LLMCallRecord) -> None:
        with self._session_factory() as session:
            session.add(
                LlmCallLogRow(
                    id=entry.id,
                    decision_id=entry.decision_id,
                    trace_id=entry.trace_id,
                    agent_name=entry.agent_name,
                    call_type=entry.call_type,
                    model=entry.model,
                    tier=entry.tier,
                    prompt=entry.prompt,
                    response=entry.response,
                    latency_ms=entry.latency_ms,
                    tokens_in=entry.tokens_in,
                    tokens_out=entry.tokens_out,
                    error=entry.error,
                    created_at=entry.created_at.timestamp(),
                )
            )
            session.commit()

    def load_records(self, *, decision_id: str | None = None) -> list[LLMCallRecord]:
        with self._session_factory() as session:
            query = session.query(LlmCallLogRow)
            if decision_id is not None:
                query = query.filter(LlmCallLogRow.decision_id == decision_id)
            rows = query.order_by(LlmCallLogRow.created_at.asc()).all()
            return [
                LLMCallRecord(
                    id=row.id,
                    decision_id=row.decision_id,
                    trace_id=row.trace_id or "",
                    agent_name=row.agent_name,
                    call_type=row.call_type,
                    model=row.model,
                    tier=row.tier,
                    prompt=row.prompt,
                    response=row.response,
                    latency_ms=row.latency_ms,
                    tokens_in=row.tokens_in,
                    tokens_out=row.tokens_out,
                    error=row.error,
                    created_at=_timestamp_to_datetime(row.created_at),
                )
                for row in rows
            ]


def _timestamp_to_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC)

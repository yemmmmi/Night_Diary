"""SQLite-backed AgentDecisionLogger implementation."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models.agent_decision import AgentDecisionRow
from app.shared.tracing import AgentDecisionRecord


class SqliteAgentDecisionLogger:
    """Persist Supervisor/agent decisions to ``agent_decisions``."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, entry: AgentDecisionRecord) -> None:
        with self._session_factory() as session:
            session.add(
                AgentDecisionRow(
                    id=entry.id,
                    agent_name=entry.agent_name,
                    decision_type=entry.decision_type,
                    diary_id=entry.diary_id,
                    intent=entry.intent,
                    tier=entry.tier,
                    skill_ids=list(entry.skill_ids),
                    reasoning=entry.reasoning,
                    created_at=entry.created_at.timestamp(),
                )
            )
            session.commit()

    def load_records(self, *, diary_id: str | None = None) -> list[AgentDecisionRecord]:
        with self._session_factory() as session:
            query = session.query(AgentDecisionRow)
            if diary_id is not None:
                query = query.filter(AgentDecisionRow.diary_id == diary_id)
            rows = query.order_by(AgentDecisionRow.created_at.asc()).all()
            return [
                AgentDecisionRecord(
                    id=row.id,
                    agent_name=row.agent_name,
                    decision_type=row.decision_type,
                    diary_id=row.diary_id,
                    intent=row.intent,
                    tier=row.tier,
                    skill_ids=tuple(row.skill_ids or ()),
                    reasoning=row.reasoning,
                    created_at=_timestamp_to_datetime(row.created_at),
                )
                for row in rows
            ]


def _timestamp_to_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC)

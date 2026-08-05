"""基于 SQLite 的 SkillActivationTracer 实现。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models.skill_activation import SkillActivationRow
from app.shared.tracing import SkillActivationRecord


class SqliteSkillActivationTracer:
    """持久化技能激活评估结果，供后续在 B-9 中审查。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, entry: SkillActivationRecord) -> None:
        with self._session_factory() as session:
            session.add(
                SkillActivationRow(
                    id=entry.id,
                    decision_id=entry.decision_id,
                    skill_name=entry.skill_name,
                    activated=entry.activated,
                    score=entry.score,
                    threshold=entry.threshold,
                    input_digest=entry.input_digest[:200],
                    reason=entry.reason,
                    latency_ms=entry.latency_ms,
                    trace_id=entry.trace_id,
                    created_at=entry.created_at.timestamp(),
                )
            )
            session.commit()

    def load_records(self, *, decision_id: str | None = None) -> list[SkillActivationRecord]:
        with self._session_factory() as session:
            query = session.query(SkillActivationRow)
            if decision_id is not None:
                query = query.filter(SkillActivationRow.decision_id == decision_id)
            rows = query.order_by(SkillActivationRow.created_at.asc()).all()
            return [
                SkillActivationRecord(
                    id=row.id,
                    decision_id=row.decision_id,
                    skill_name=row.skill_name,
                    activated=row.activated,
                    score=row.score,
                    threshold=row.threshold,
                    input_digest=row.input_digest,
                    reason=row.reason,
                    latency_ms=row.latency_ms,
                    trace_id=row.trace_id or "",
                    created_at=_timestamp_to_datetime(row.created_at),
                )
                for row in rows
            ]


def _timestamp_to_datetime(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC)

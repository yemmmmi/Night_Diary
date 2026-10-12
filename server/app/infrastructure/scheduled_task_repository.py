"""SQLite-backed repository for scheduled tasks (A4)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models.scheduled_task import (
    ScheduledTaskRow,
    ScheduledTaskRunRow,
)

_UNSET: object = object()


class SqliteScheduledTaskStore:
    """Persist task definitions and their execution receipts."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    # ── Task definitions ───────────────────────────────────────────────

    def create(
        self,
        *,
        user_id: str,
        kind: str,
        cron_expr: str,
        payload_json: str,
        enabled: bool,
        next_run_at: datetime | None,
    ) -> ScheduledTaskRow:
        with self._session_factory() as session:
            row = ScheduledTaskRow(
                user_id=user_id,
                kind=kind,
                cron_expr=cron_expr,
                payload_json=payload_json,
                enabled=enabled,
                next_run_at=next_run_at,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get(self, task_id: str, *, user_id: str | None = None) -> ScheduledTaskRow | None:
        with self._session_factory() as session:
            row = session.get(ScheduledTaskRow, task_id)
            if row is None:
                return None
            if user_id is not None and row.user_id != user_id:
                return None
            return row

    def list_for_user(self, user_id: str) -> list[ScheduledTaskRow]:
        with self._session_factory() as session:
            stmt = (
                select(ScheduledTaskRow)
                .where(ScheduledTaskRow.user_id == user_id)
                .order_by(ScheduledTaskRow.created_at.asc())
            )
            return list(session.scalars(stmt))

    def update(
        self,
        task_id: str,
        *,
        user_id: str,
        cron_expr: str | None = None,
        payload_json: str | None = None,
        enabled: bool | None = None,
        next_run_at: object = _UNSET,
    ) -> ScheduledTaskRow | None:
        with self._session_factory() as session:
            row = session.get(ScheduledTaskRow, task_id)
            if row is None or row.user_id != user_id:
                return None
            if cron_expr is not None:
                row.cron_expr = cron_expr
            if payload_json is not None:
                row.payload_json = payload_json
            if enabled is not None:
                row.enabled = enabled
            if next_run_at is not _UNSET:
                row.next_run_at = next_run_at  # type: ignore[assignment]
            session.commit()
            session.refresh(row)
            return row

    def delete(self, task_id: str, *, user_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(ScheduledTaskRow, task_id)
            if row is None or row.user_id != user_id:
                return False
            session.delete(row)
            session.commit()
            return True

    def list_due(self, now: datetime, *, limit: int = 50) -> list[ScheduledTaskRow]:
        """Enabled tasks whose ``next_run_at`` is at or before ``now``."""
        with self._session_factory() as session:
            stmt = (
                select(ScheduledTaskRow)
                .where(
                    ScheduledTaskRow.enabled.is_(True),
                    ScheduledTaskRow.next_run_at.is_not(None),
                    ScheduledTaskRow.next_run_at <= now,
                )
                .order_by(ScheduledTaskRow.next_run_at.asc())
                .limit(limit)
            )
            return list(session.scalars(stmt))

    def set_next_run(self, task_id: str, next_run_at: datetime | None) -> None:
        with self._session_factory() as session:
            row = session.get(ScheduledTaskRow, task_id)
            if row is None:
                return
            row.next_run_at = next_run_at
            session.commit()

    def mark_last(self, task_id: str, *, status: str, last_run_at: datetime) -> None:
        with self._session_factory() as session:
            row = session.get(ScheduledTaskRow, task_id)
            if row is None:
                return
            row.last_status = status
            row.last_run_at = last_run_at
            session.commit()

    # ── Execution receipts ─────────────────────────────────────────────

    def record_run_started(self, *, task_id: str, user_id: str, kind: str) -> int:
        with self._session_factory() as session:
            row = ScheduledTaskRunRow(
                task_id=task_id,
                user_id=user_id,
                kind=kind,
                status="running",
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        summary: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            row = session.get(ScheduledTaskRunRow, run_id)
            if row is None:
                return
            row.status = status
            row.summary = summary
            row.error = (error or "")[:2000] if error else None
            row.finished_at = datetime.utcnow()
            session.commit()

    def list_runs(
        self, task_id: str, *, user_id: str, limit: int = 20
    ) -> list[ScheduledTaskRunRow]:
        with self._session_factory() as session:
            stmt = (
                select(ScheduledTaskRunRow)
                .where(
                    ScheduledTaskRunRow.task_id == task_id,
                    ScheduledTaskRunRow.user_id == user_id,
                )
                .order_by(ScheduledTaskRunRow.started_at.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt))

    def latest_runs(self, *, user_id: str, limit: int = 20) -> list[ScheduledTaskRunRow]:
        with self._session_factory() as session:
            stmt = (
                select(ScheduledTaskRunRow)
                .where(ScheduledTaskRunRow.user_id == user_id)
                .order_by(ScheduledTaskRunRow.started_at.desc())
                .limit(limit)
            )
            return list(session.scalars(stmt))


__all__ = ["SqliteScheduledTaskStore"]
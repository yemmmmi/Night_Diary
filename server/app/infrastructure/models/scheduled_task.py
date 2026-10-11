"""ORM models for user-orchestrable scheduled tasks (A4).

A4 (Hermes lessons): users can register recurring tasks — a cron expression
plus a task ``kind`` (daily review / weekly insight / plan reminder) and a
free-form ``payload``. A background scheduler loop dispatches due tasks
through the existing task queue; each execution is recorded as a durable run
row so the in-app "信箱/回执" can show what ran and when.

Schedule datetimes (``next_run_at`` / ``last_run_at``) are naive **local**
time (cron is naturally wall-clock); ``created_at`` / ``updated_at`` keep the
project-wide UTC convention.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


def _new_task_id() -> str:
    return uuid.uuid4().hex


class ScheduledTaskRow(Base):
    """A recurring task definition owned by one user."""

    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_task_id)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<ScheduledTaskRow(id={self.id!r}, kind={self.kind!r}, "
            f"cron={self.cron_expr!r}, enabled={self.enabled})>"
        )


class ScheduledTaskRunRow(Base):
    """One execution of a scheduled task — the in-app receipt."""

    __tablename__ = "scheduled_task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running"
    )  # running | done | failed
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ScheduledTaskRunRow(id={self.id}, task_id={self.task_id!r}, "
            f"status={self.status!r})>"
        )
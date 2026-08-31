"""ORM models for the plan/task domain (V3 P2).

A ``Plan`` is a named container of related tasks with a motivation and
source references (diary/memory citations). A ``Task`` is a single
actionable to-do, optionally belonging to a Plan.

Both tables carry ``source`` (manual vs agent) and
``created_from_conversation_id`` so we can audit which plans/tasks
originated from an Agent proposal vs direct user creation.

Note: ``user_id`` is a plain ``String(64)`` without a ``ForeignKey`` to
``users.id``. This mirrors the convention used by every other user-scoped
table (see ``conversation.py``, ``pipeline_trace.py``) and avoids a
``String`` → ``Integer`` type mismatch that would break the MySQL backend.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base


class PlanRow(Base):
    """A plan: a named container of tasks with motivation and source refs."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    motivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/archived/completed
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual/agent
    created_from_conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recurrence: Mapped[str | None] = mapped_column(String(32), nullable=True)  # none/daily/weekly:1-7
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_period: Mapped[str | None] = mapped_column(String(16), nullable=True)  # daily/weekly/total
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tasks: Mapped[list[TaskRow]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
    )


class TaskRow(Base):
    """A single to-do item, optionally belonging to a Plan."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    plan_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("plans.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/done/skipped
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_from_conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    plan: Mapped[PlanRow | None] = relationship(back_populates="tasks")

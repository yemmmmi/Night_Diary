"""ORM model for replayable background jobs (``jobs``).

Robustness P2-6: fire-and-forget sidecars (entity extraction, later memory
writes) are recorded as durable job rows so a process crash/restart does not
silently lose them. On startup, stale ``pending``/``running`` jobs are
re-queued (:func:`app.services.job_service.requeue_stale_jobs`).

``payload_json`` is a JSON blob of the job's arguments; each ``kind`` has a
matching handler in the job service. ``attempts`` bounds retries.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


def _new_job_id() -> str:
    return uuid.uuid4().hex


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_job_id)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )  # pending | running | done | failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<JobRow(id={self.id!r}, kind={self.kind!r}, status={self.status!r})>"

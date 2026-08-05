"""ORM model for pipeline trace storage (``pipeline_traces``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class PipelineTraceRow(Base):
    """Persisted representation of a full pipeline execution trace.

    Each row stores the high-level metadata (scenario, user, timing, status)
    plus the complete trace payload as JSON in ``trace_json`` so it can be
    replayed or inspected without re-running the pipeline.
    """

    __tablename__ = "pipeline_traces"
    __table_args__ = (
        Index("idx_traces_user", "user_id", "started_at"),
        Index("idx_traces_scenario", "scenario", "started_at"),
    )

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[str] = mapped_column(String(32))
    ended_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    span_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

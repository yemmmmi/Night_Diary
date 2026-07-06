"""ORM model for skill activation tracing."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class SkillActivationRow(Base):
    __tablename__ = "skill_activations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    skill_name: Mapped[str] = mapped_column(String(64), index=True)
    activated: Mapped[bool] = mapped_column(Boolean)
    score: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    input_digest: Mapped[str] = mapped_column(String(200), default="")
    reason: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[float] = mapped_column(Float)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

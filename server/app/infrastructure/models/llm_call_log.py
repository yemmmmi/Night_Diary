"""ORM model for LLM call tracing (``llm_call_logs``)."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class LlmCallLogRow(Base):
    __tablename__ = "llm_call_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    decision_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    call_type: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    tier: Mapped[str] = mapped_column(String(16), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    response: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[float] = mapped_column(Float)

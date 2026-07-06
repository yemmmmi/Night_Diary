"""ORM model for agent decision tracing (``agent_decisions``)."""

from __future__ import annotations

from sqlalchemy import JSON, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class AgentDecisionRow(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    decision_type: Mapped[str] = mapped_column(String(32), index=True)
    diary_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    intent: Mapped[str] = mapped_column(String(32), default="")
    tier: Mapped[str] = mapped_column(String(16), default="")
    # JSON array of activated skill names linked to SkillActivationRow.decision_id.
    skill_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float)

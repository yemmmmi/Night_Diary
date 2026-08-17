"""ORM model for AI analysis records (``analyses``)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from app.infrastructure.models.diary_entry import DiaryEntryRow


class AnalysisRow(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    diary_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("diary_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    token_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hit_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_miss_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    diary_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    execution_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    activated_agents: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)

    diary_entry: Mapped[DiaryEntryRow] = relationship(
        "DiaryEntryRow",
        back_populates="analysis",
    )

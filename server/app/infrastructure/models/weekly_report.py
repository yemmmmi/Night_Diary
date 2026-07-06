"""ORM model for AI weekly reports (``weekly_reports``).

A weekly report ("周记") is an AI-generated letter that aggregates a week's
diary entries and memory cards into one reflective reply. It reuses the
existing multi-agent pipeline (InsightAgent weekly-report mode) but is stored
independently of any single diary entry.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class WeeklyReportRow(Base):
    """A single AI-generated weekly letter for an ISO week (Mon-Sun)."""

    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    diary_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    card_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_mood: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<WeeklyReportRow(id={self.id}, "
            f"period_start={self.period_start}, "
            f"diary_count={self.diary_count}, card_count={self.card_count})>"
        )

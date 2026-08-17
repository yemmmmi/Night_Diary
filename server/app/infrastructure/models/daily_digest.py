"""ORM model for daily digests (``daily_digests``).

A daily digest is the per-day structured summary produced by scene 1's
"tree-hole" analysis: it aggregates the day's memory cards (``cards``
section, user-authored, zero LLM cost) with the typed diary's extraction
(``diary`` section, LLM or rule-based). Scene 2 reads it to understand a
referenced day without reading the full diary content.

One row per ``(user_id, date)`` — see ``app/shared/digest.py`` for the JSON
shape stored in ``digest_json``.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class DailyDigestRow(Base):
    """A single day's structured digest, scoped to a user."""

    __tablename__ = "daily_digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    digest_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_daily_digests_user_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<DailyDigestRow(user_id={self.user_id!r}, "
            f"date={self.date.isoformat()}, updated_at={self.updated_at})>"
        )

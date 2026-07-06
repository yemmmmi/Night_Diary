"""ORM model for memory cards (``memory_cards``).

Memory cards are lightweight, structured memory atoms that lower the
barrier to journaling. Each card captures a moment's emotion, event
summary, and tags in under 30 seconds, and can optionally be expanded
into a full diary entry.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class MemoryCardRow(Base):
    """A single memory card — structured fragment of a day's experience."""

    __tablename__ = "memory_cards"

    card_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    emotion: Mapped[str] = mapped_column(String(32), nullable=False, default="neutral")
    emotions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    mood_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    card_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="standard"
    )
    diary_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("diary_entries.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return (
            f"<MemoryCardRow(card_id={self.card_id!r}, "
            f"emotion={self.emotion!r}, "
            f"card_type={self.card_type!r}, "
            f"diary_id={self.diary_id})>"
        )

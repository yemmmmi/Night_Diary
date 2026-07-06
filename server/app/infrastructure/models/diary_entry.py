"""ORM model for diary entries (``diary_entries``)."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from app.infrastructure.models.analysis import AnalysisRow
    from app.infrastructure.models.tag import TagRow


class DiaryEntryRow(Base):
    """A diary entry, scoped to a user via ``user_id``."""

    __tablename__ = "diary_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weather: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    analysis: Mapped[AnalysisRow | None] = relationship(
        "AnalysisRow",
        back_populates="diary_entry",
        uselist=False,
        cascade="all, delete-orphan",
    )
    tags: Mapped[list[TagRow]] = relationship(
        "TagRow",
        secondary="diary_tags",
        back_populates="diary_entries",
    )

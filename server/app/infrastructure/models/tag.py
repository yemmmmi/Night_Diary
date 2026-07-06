"""ORM models for tags and diary-tag associations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    from app.infrastructure.models.diary_entry import DiaryEntryRow

diary_tag_association = Table(
    "diary_tags",
    Base.metadata,
    Column(
        "diary_id", Integer, ForeignKey("diary_entries.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime, default=datetime.utcnow),
)


class TagRow(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#6B7280")
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    diary_entries: Mapped[list[DiaryEntryRow]] = relationship(
        "DiaryEntryRow",
        secondary=diary_tag_association,
        back_populates="tags",
    )

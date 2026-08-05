"""记忆卡片的 ORM 模型（``memory_cards``）。

记忆卡片是轻量级、结构化的记忆原子，可降低写日记的门槛。
每张卡片在 30 秒内捕捉一个时刻的情绪、事件摘要和标签，
并可选择性地扩展为完整的日记条目。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class MemoryCardRow(Base):
    """单张记忆卡片 — 一天体验的结构化片段。"""

    __tablename__ = "memory_cards"

    card_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    emotion: Mapped[str] = mapped_column(String(32), nullable=False, default="neutral")
    emotions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    mood_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    card_type: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")
    diary_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("diary_entries.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
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

"""用户对 AI 回复显式反馈的 ORM 模型（``feedback``）。

同时支持场景一（日记分析）和场景二（对话）的反馈。
对于日记反馈，设置 ``analysis_id`` 和 ``diary_id``。
对于对话反馈，设置 ``conversation_id``。
``analysis_id`` 或 ``conversation_id`` 至少有一个必须非空。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class FeedbackRow(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    diary_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("diary_entries.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    response_style: Mapped[str] = mapped_column(String(32), nullable=False, default="empathetic")
    feedback_type: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="explicit")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

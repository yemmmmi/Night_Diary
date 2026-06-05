"""ORM model for explicit user feedback on AI responses (``feedback``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class FeedbackRow(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    diary_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("diary_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    response_style: Mapped[str] = mapped_column(String(32), nullable=False, default="empathetic")
    feedback_type: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="explicit")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

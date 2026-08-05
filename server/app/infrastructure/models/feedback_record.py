"""ORM model for explicit user feedback on AI responses (``feedback``).

Supports both scene-1 (diary analysis) and scene-2 (conversation) feedback.
For diary feedback, ``analysis_id`` and ``diary_id`` are set.
For conversation feedback, ``conversation_id`` is set.
At least one of ``analysis_id`` or ``conversation_id`` must be non-null.
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

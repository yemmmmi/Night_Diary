"""ORM model for online reply-quality scores (``reply_quality``).

The quality sentinel (robustness P1-4) samples real AI replies (diary
tree-hole replies + conversation replies) and grades them with a judge LLM.
Scores are stored per reply so drift over time is measurable via
``/api/v1/dev/stats/quality``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class ReplyQualityRow(Base):
    """One judge-graded reply sample."""

    __tablename__ = "reply_quality"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scenario: Mapped[str] = mapped_column(String(32), nullable=False)  # diary_reply | conversation
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reply_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<ReplyQualityRow(scenario={self.scenario!r}, ref_id={self.ref_id!r}, "
            f"overall={self.overall})>"
        )

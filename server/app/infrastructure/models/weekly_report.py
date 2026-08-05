"""AI 周报的 ORM 模型（``weekly_reports``）。

周报（"周记"）是 AI 生成的信件，将一周的日记条目和记忆卡片
聚合为一封反思性回复。它复用现有的多智能体管道
（InsightAgent 周报模式），但独立于任何单条日记条目存储。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class WeeklyReportRow(Base):
    """针对某个 ISO 周（周一至周日）生成的单封 AI 周记信件。"""

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

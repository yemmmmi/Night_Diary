"""管道追踪存储的 ORM 模型（``pipeline_traces``）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class PipelineTraceRow(Base):
    """完整管道执行追踪的持久化表示。

    每行存储高层元数据（场景、用户、时间、状态），
    以及完整的追踪载荷（JSON 格式存储在 ``trace_json`` 中），
    以便在不重新运行管道的情况下回放或审查。
    """

    __tablename__ = "pipeline_traces"
    __table_args__ = (
        Index("idx_traces_user", "user_id", "started_at"),
        Index("idx_traces_scenario", "scenario", "started_at"),
    )

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[str] = mapped_column(String(32))
    ended_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    span_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

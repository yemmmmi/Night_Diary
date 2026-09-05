"""ORM model for the ``mcp_call_logs`` table."""

from __future__ import annotations

from sqlalchemy import Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class McpCallLogRow(Base):
    """One MCP tool call (persisted for Dev panel + observability)."""

    __tablename__ = "mcp_call_logs"
    __table_args__ = (
        Index("ix_mcp_call_logs_endpoint_alias", "endpoint_alias"),
        Index("ix_mcp_call_logs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    span_id: Mapped[str] = mapped_column(String(64), default="")
    endpoint_alias: Mapped[str] = mapped_column(String(64))
    transport: Mapped[str] = mapped_column(String(16))
    tool_name: Mapped[str] = mapped_column(String(128))
    raw_tool_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    arguments_snapshot: Mapped[str] = mapped_column(Text, default="")
    result_snapshot: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float)

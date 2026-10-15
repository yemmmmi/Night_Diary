"""ORM model for the ``profile_change_log`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class ProfileChangeLogRow(Base):
    """One audited field-level change to a user's long-term profile (P1-B).

    Written by ``LongTermMemory.update_profile`` through the
    ``ProfileChangeLogStore`` port. ``source`` marks the trigger
    (promotion / mood_sync / manual), ``evidence_json`` stores the memory
    pairs (date + summary + emotion) the change was derived from.
    """

    __tablename__ = "profile_change_log"
    __table_args__ = (
        Index("ix_profile_change_log_user_id", "user_id"),
        Index("ix_profile_change_log_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64))
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

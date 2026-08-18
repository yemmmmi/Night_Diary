"""ORM model for the per-day user-mode baseline (V3.x mode system).

A ``DailyModeRow`` records the judged day-level mode baseline for a user on a
given calendar date, plus the day's switch bookkeeping and the mood signals that
fed the judgement. It is the authoritative read/write point for the scene-2 mode
system:

* ``MoodMonitor`` (judgement layer) reads/writes it when setting the day's
  baseline and recording automatic switches.
* The insight/review flows read it later ("on which days was the user mostly in
  which mode").

Unlike ``plans``/``tasks`` (String(32) uuid ids), this table uses an
autoincrement Integer PK plus a ``UniqueConstraint(user_id, date)`` because each
user has at most one row per day. ``user_id`` stays a plain ``String(64)``
without a foreign key, mirroring every other user-scoped table (and avoiding a
``String`` → ``Integer`` mismatch on MySQL).

Mode constants (internal codes, never shown to the user):
    ``daily``  = 日常
    ``followup`` = 跟进
    ``introspection`` = 内视
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class MODE:
    DAILY = "daily"
    FOLLOWUP = "followup"
    INTROSPECTION = "introspection"

    ALL = (DAILY, FOLLOWUP, INTROSPECTION)


class DailyModeRow(Base):
    """One user's judged mode baseline for one calendar day."""

    __tablename__ = "daily_modes"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_daily_modes_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    baseline_mode: Mapped[str] = mapped_column(String(20), default=MODE.DAILY)
    auto_switched: Mapped[bool] = mapped_column(Boolean, default=False)
    switch_count: Mapped[int] = mapped_column(Integer, default=0)
    mood_signals_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

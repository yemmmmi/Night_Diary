"""ORM models for episodic and long-term memory persistence."""

from __future__ import annotations

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class EpisodicMemoryRow(Base):
    __tablename__ = "episodic_memories"

    entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[float] = mapped_column(Float, index=True)
    importance: Mapped[float] = mapped_column(Float)
    payload_json: Mapped[str] = mapped_column(Text)


class LongTermProfileRow(Base):
    __tablename__ = "long_term_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[float] = mapped_column(Float)

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


class UserAboutRow(Base):
    """User-authored self-description ("关于我").

    Kept separate from :class:`LongTermProfileRow` (which is *system-inferred*):
    this is what the user says about themselves — background, preferences,
    expected tone. Injected at the frozen system-prompt prefix (B2/D6).
    """

    __tablename__ = "user_abouts"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)

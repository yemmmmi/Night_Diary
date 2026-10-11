"""ORM models for user-defined custom skills (A2).

Two tables:

* ``user_skills`` — the current definition of each user-authored skill.
* ``user_skill_versions`` — an append-only snapshot of every prior revision,
  written whenever a definition is updated, so a user can inspect (and later
  restore) history. Versioning mirrors the ``plan_change_log`` pattern (A3).
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class UserSkillRow(Base):
    __tablename__ = "user_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(String(200), default="")
    #: JSON array of trigger substrings.
    triggers_json: Mapped[str] = mapped_column(Text, default="[]")
    instruction: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[float] = mapped_column(Float, default=0.0)


class UserSkillVersionRow(Base):
    """Append-only snapshot of a skill revision (written on update)."""

    __tablename__ = "user_skill_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(String(200), default="")
    triggers_json: Mapped[str] = mapped_column(Text, default="[]")
    instruction: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=0.0)
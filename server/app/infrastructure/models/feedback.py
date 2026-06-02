"""ORM models for style preference feedback."""

from __future__ import annotations

from sqlalchemy import Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class StylePreferenceRow(Base):
    __tablename__ = "style_preferences"
    __table_args__ = (UniqueConstraint("user_id", "style", name="uq_style_preferences_user_style"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    style: Mapped[str] = mapped_column(String(32))
    alpha: Mapped[float] = mapped_column(Float, default=1.0)
    beta: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[float] = mapped_column(Float)

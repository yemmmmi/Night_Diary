"""ORM model for registered users (``users``).

Supports multi-tenant data isolation: every user-scoped table carries a
``user_id`` column (VARCHAR(64)) that stores ``str(users.id)`` or the
legacy sentinel ``'default'`` for pre-migration data.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class UserRow(Base):
    """A registered application user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    nickname: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<UserRow(id={self.id}, email={self.email!r}, "
            f"nickname={self.nickname!r})>"
        )

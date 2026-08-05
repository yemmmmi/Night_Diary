"""注册用户的 ORM 模型（``users``）。

支持多租户数据隔离：每个用户限定的表都携带 ``user_id``
列（VARCHAR(64)），存储 ``str(users.id)`` 或迁移前数据的
遗留哨兵值 ``'default'``。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class UserRow(Base):
    """已注册的应用用户。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<UserRow(id={self.id}, email={self.email!r}, nickname={self.nickname!r})>"

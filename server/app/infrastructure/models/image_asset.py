"""ORM model for uploaded image assets (``image_assets``).

Each row records one image uploaded by a user, scoped via ``user_id`` for
multi-tenant isolation. Diary entries reference assets by id through the
``diary_entries.image_assets_json`` column; the asset row keeps the storage
filename and metadata so the original file can be streamed back.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class ImageAssetRow(Base):
    """An uploaded image asset, scoped to a user via ``user_id``."""

    __tablename__ = "image_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
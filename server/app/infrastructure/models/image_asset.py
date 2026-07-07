"""ORM model for uploaded image assets (``image_assets``).

Each row records an image uploaded by a user, scoped via ``user_id`` for
multi-tenant isolation. The async image-processing pipeline writes back the
``semantic_description``/``extracted_text``/``content_type``/``processing_path``
columns once processing completes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
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
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Processing results (written back by the async pipeline)
    semantic_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    processing_path: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

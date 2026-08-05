"""用户配置的 LLM 供应商的 ORM 模型（``model_providers``）。"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base

TIER_VALUES = frozenset({"light", "medium", "heavy", "default"})


class ModelProviderRow(Base):
    __tablename__ = "model_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="未命名")
    api_key_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier: Mapped[str] = mapped_column(String(16), default="default", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

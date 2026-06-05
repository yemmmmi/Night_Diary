"""ModelProvider CRUD with Fernet-encrypted API keys."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.infrastructure.models.model_provider import TIER_VALUES, ModelProviderRow
from app.infrastructure.security import encrypt_api_key
from app.shared.errors import ModelProviderNotFoundError, ValidationError

logger = logging.getLogger(__name__)


def list_models(db: Session) -> list[ModelProviderRow]:
    return db.query(ModelProviderRow).order_by(ModelProviderRow.id.asc()).all()


def get_model(db: Session, model_id: int) -> ModelProviderRow:
    row = db.query(ModelProviderRow).filter(ModelProviderRow.id == model_id).first()
    if row is None:
        raise ModelProviderNotFoundError(model_id=model_id)
    return row


def _validate_tier(tier: str) -> str:
    normalized = tier.strip().lower()
    if normalized not in TIER_VALUES:
        raise ValidationError(f"tier 必须是 {sorted(TIER_VALUES)} 之一")
    return normalized


def validate_model_connection(base_url: str, api_key: str) -> str | None:
    if not base_url.startswith(("http://", "https://")):
        return "Base URL 格式错误"
    test_url = base_url.rstrip("/") + "/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(test_url, headers=headers)
        if resp.status_code in (200, 404):
            return None
        if resp.status_code == 401:
            return "API Key 无效（401）"
        return f"API 返回状态码 {resp.status_code}"
    except httpx.ConnectError:
        return f"无法连接到 {base_url}"
    except httpx.TimeoutException:
        return f"连接超时：{base_url}"


def create_model(
    db: Session,
    *,
    model_name: str,
    api_key: str,
    base_url: str,
    tier: str = "default",
    is_active: bool = False,
    settings: Settings | None = None,
) -> ModelProviderRow:
    tier = _validate_tier(tier)
    error = validate_model_connection(base_url, api_key)
    if error:
        raise ValidationError(error)

    row = ModelProviderRow(
        model_name=model_name,
        api_key_encrypted=encrypt_api_key(api_key, settings),
        base_url=base_url,
        tier=tier,
        is_active=is_active,
    )
    if is_active:
        _deactivate_others(db, tier=tier, exclude_id=None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_model(
    db: Session,
    model_id: int,
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    tier: str | None = None,
    is_active: bool | None = None,
    settings: Settings | None = None,
) -> ModelProviderRow:
    row = get_model(db, model_id)
    resolved_settings = settings or get_settings()

    if model_name is not None:
        row.model_name = model_name
    if base_url is not None:
        row.base_url = base_url
    if tier is not None:
        row.tier = _validate_tier(tier)
    if api_key is not None:
        test_url = (base_url or row.base_url) or ""
        test_key = api_key
        if test_url:
            error = validate_model_connection(test_url, test_key)
            if error:
                raise ValidationError(error)
        row.api_key_encrypted = encrypt_api_key(api_key, resolved_settings)
    if is_active is not None:
        row.is_active = is_active
        if is_active:
            _deactivate_others(db, tier=row.tier, exclude_id=row.id)

    db.commit()
    db.refresh(row)
    return row


def delete_model(db: Session, model_id: int) -> None:
    row = get_model(db, model_id)
    db.delete(row)
    db.commit()


def model_to_public_dict(row: ModelProviderRow) -> dict[str, Any]:
    """API-safe projection — never exposes the encrypted key."""
    return {
        "id": row.id,
        "model_name": row.model_name,
        "base_url": row.base_url,
        "tier": row.tier,
        "is_active": row.is_active,
        "is_default": row.is_default,
        "has_api_key": bool(row.api_key_encrypted),
    }


def get_active_provider_for_tier(db: Session, tier: str) -> ModelProviderRow | None:
    return (
        db.query(ModelProviderRow)
        .filter(
            ModelProviderRow.tier == tier,
            ModelProviderRow.is_active.is_(True),
            ModelProviderRow.api_key_encrypted.isnot(None),
        )
        .first()
    )


def _deactivate_others(db: Session, *, tier: str, exclude_id: int | None) -> None:
    query = db.query(ModelProviderRow).filter(ModelProviderRow.tier == tier)
    if exclude_id is not None:
        query = query.filter(ModelProviderRow.id != exclude_id)
    for row in query.all():
        row.is_active = False

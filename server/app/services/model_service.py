"""ModelProvider CRUD with Fernet-encrypted API keys."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.infrastructure.models.model_provider import TIER_VALUES, ModelProviderRow
from app.infrastructure.security import decrypt_api_key, encrypt_api_key
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


def _models_probe_candidates(base_url: str) -> list[str]:
    """Candidate GET /models URLs — DeepSeek uses root ``/models``, OpenAI uses ``/v1/models``."""
    root = base_url.rstrip("/")
    candidates: list[str] = []
    if root.endswith("/v1"):
        origin = root[: -len("/v1")]
        candidates.append(f"{origin}/models")
    candidates.append(f"{root}/models")
    if not root.endswith("/v1"):
        candidates.append(f"{root}/v1/models")
    # preserve order, dedupe
    seen: set[str] = set()
    ordered: list[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def _chat_completions_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def _external_http_client() -> httpx.Client:
    """Outbound LLM probe client — bypass system proxy to avoid Clash rewriting loopback/API."""
    return httpx.Client(timeout=10.0, trust_env=False)


def _probe_models_list(client: httpx.Client, url: str, headers: dict[str, str]) -> httpx.Response:
    return client.get(url, headers=headers)


def _probe_chat_smoke(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
    model_name: str = "deepseek-chat",
) -> httpx.Response:
    url = _chat_completions_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    return client.post(url, headers=headers, json=payload)


def validate_model_connection(
    base_url: str,
    api_key: str,
    *,
    model_name: str = "deepseek-chat",
) -> str | None:
    if not base_url.startswith(("http://", "https://")):
        return "Base URL 格式错误"

    headers = {"Authorization": f"Bearer {api_key}"}
    last_status: int | None = None

    try:
        with _external_http_client() as client:
            for test_url in _models_probe_candidates(base_url):
                resp = _probe_models_list(client, test_url, headers)
                if resp.status_code in (200, 404):
                    return None
                if resp.status_code == 401:
                    return "API Key 无效（401）"
                if resp.status_code not in (405, 404):
                    return f"API 返回状态码 {resp.status_code}（{test_url}）"
                last_status = resp.status_code

            # DeepSeek etc.: /models may 405 — fall back to minimal chat completion
            chat_resp = _probe_chat_smoke(
                client,
                base_url=base_url,
                api_key=api_key,
                model_name=model_name,
            )
            if chat_resp.status_code in (200, 201):
                return None
            if chat_resp.status_code == 401:
                return "API Key 无效（401）"
            if chat_resp.status_code == 400:
                # model name wrong but auth/endpoint OK
                return None
            return f"API 返回状态码 {chat_resp.status_code}（chat 探测）"
    except httpx.ConnectError:
        return f"无法连接到 {base_url}"
    except httpx.TimeoutException:
        return f"连接超时：{base_url}"

    if last_status is not None:
        return f"API 返回状态码 {last_status}"
    return None


def test_stored_model_connection(
    db: Session,
    model_id: int,
    *,
    settings: Settings | None = None,
) -> str | None:
    row = get_model(db, model_id)
    if not row.api_key_encrypted:
        return "未配置 API Key"
    if not row.base_url:
        return "未配置 API 地址"
    resolved = settings or get_settings()
    api_key = decrypt_api_key(row.api_key_encrypted, resolved)
    return validate_model_connection(row.base_url, api_key, model_name=row.model_name)


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
    error = validate_model_connection(base_url, api_key, model_name=model_name)
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
    elif not get_active_provider_for_tier(db, tier):
        row.is_active = True
        logger.info("Auto-activated first model for tier=%s (id pending commit)", tier)
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
        test_model = model_name or row.model_name
        if test_url:
            error = validate_model_connection(test_url, test_key, model_name=test_model)
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


def get_models_status(db: Session, settings: Settings | None = None) -> dict[str, object]:
    """Summarize which tiers have an active provider (for settings / diagnostics UI)."""
    resolved = settings or get_settings()
    tiers: list[dict[str, object]] = []
    for tier in ("light", "medium", "heavy", "default"):
        provider = get_active_provider_for_tier(db, tier)
        tiers.append(
            {
                "tier": tier,
                "configured": provider is not None,
                "model_name": provider.model_name if provider else None,
                "base_url": provider.base_url if provider else None,
                "is_active": bool(provider and provider.is_active),
            }
        )
    env_fallback = bool(resolved.llm_api_key) and not any(t["configured"] for t in tiers)
    return {
        "tiers": tiers,
        "env_fallback": env_fallback,
        "env_model_name": resolved.llm_model if env_fallback else None,
    }


def _deactivate_others(db: Session, *, tier: str, exclude_id: int | None) -> None:
    query = db.query(ModelProviderRow).filter(ModelProviderRow.tier == tier)
    if exclude_id is not None:
        query = query.filter(ModelProviderRow.id != exclude_id)
    for row in query.all():
        row.is_active = False

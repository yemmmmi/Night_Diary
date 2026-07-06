"""LLMFactory, Fernet encryption, and per-tier model resolution tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.infrastructure.security import decrypt_api_key, encrypt_api_key
from app.services import model_service
from app.shared.errors import AIServiceUnavailableError
from app.shared.llm_factory import LLMFactory, StubLLMClient
from app.shared.tracing import InMemoryLLMCallTracer


def _client_model(client: object) -> str:
    for attr in ("model", "model_name"):
        val = getattr(client, attr, None)
        if val:
            return str(val)
    return ""


def test_encrypt_decrypt_roundtrip() -> None:
    plain = "sk-test-secret-key"
    token = encrypt_api_key(plain)
    assert token != plain
    assert decrypt_api_key(token) == plain


def test_create_from_provider_builds_client(db_session) -> None:
    factory = LLMFactory()
    with patch.object(model_service, "validate_model_connection", return_value=None):
        row = model_service.create_model(
            db_session,
            user_id="default",
            model_name="deepseek-chat",
            api_key="sk-provider",
            base_url="https://api.deepseek.com/v1",
            tier="medium",
        )
    client = factory.create_from_provider(row)
    assert _client_model(client) == "deepseek-chat"
    assert hasattr(client, "invoke") or hasattr(client, "ainvoke")


def test_create_from_provider_uses_stub_when_langchain_missing(db_session) -> None:
    factory = LLMFactory()
    with patch.object(model_service, "validate_model_connection", return_value=None):
        row = model_service.create_model(
            db_session,
            user_id="default",
            model_name="deepseek-chat",
            api_key="sk-provider",
            base_url="https://api.deepseek.com/v1",
            tier="medium",
        )
    with patch.object(
        LLMFactory,
        "_build_client",
        return_value=StubLLMClient(model="deepseek-chat"),
    ):
        client = factory.create_from_provider(row)
    assert isinstance(client, StubLLMClient)


def test_create_for_tier_returns_active_provider_client(db_session) -> None:
    factory = LLMFactory()
    with patch.object(model_service, "validate_model_connection", return_value=None):
        model_service.create_model(
            db_session,
            user_id="default",
            model_name="heavy-model",
            api_key="sk-heavy",
            base_url="https://api.example.com/v1",
            tier="heavy",
            is_active=True,
        )
    client = factory.create_for_tier(db_session, "heavy")
    assert _client_model(client) == "heavy-model"


def test_create_for_tier_falls_back_to_default_tier(db_session) -> None:
    factory = LLMFactory()
    with patch.object(model_service, "validate_model_connection", return_value=None):
        model_service.create_model(
            db_session,
            user_id="default",
            model_name="default-model",
            api_key="sk-default",
            base_url="https://api.example.com/v1",
            tier="default",
            is_active=True,
        )
    client = factory.create_for_tier(db_session, "light")
    assert _client_model(client) == "default-model"


def test_resolve_by_tier_maps_active_providers(db_session) -> None:
    tracer = InMemoryLLMCallTracer()
    factory = LLMFactory()
    with patch.object(model_service, "validate_model_connection", return_value=None):
        model_service.create_model(
            db_session,
            user_id="default",
            model_name="light-model",
            api_key="sk-light",
            base_url="https://api.example.com/v1",
            tier="light",
            is_active=True,
        )
        model_service.create_model(
            db_session,
            user_id="default",
            model_name="heavy-model",
            api_key="sk-heavy",
            base_url="https://api.example.com/v1",
            tier="heavy",
            is_active=True,
        )

    clients = factory.resolve_by_tier(db_session, tracer=tracer)
    assert _client_model(clients["light"]) == "light-model"
    assert _client_model(clients["heavy"]) == "heavy-model"


def test_stored_api_key_is_encrypted_not_plaintext(db_session) -> None:
    plain = "sk-must-not-leak"
    with patch.object(model_service, "validate_model_connection", return_value=None):
        row = model_service.create_model(
            db_session,
            user_id="default",
            model_name="secure",
            api_key=plain,
            base_url="https://api.example.com/v1",
        )
    assert row.api_key_encrypted is not None
    assert plain not in row.api_key_encrypted
    public = model_service.model_to_public_dict(row)
    assert "api_key" not in public


def test_create_default_raises_when_env_unconfigured() -> None:
    from app.config import Settings

    factory = LLMFactory(settings=Settings(llm_api_key=""))
    with pytest.raises(AIServiceUnavailableError):
        factory.create_default()

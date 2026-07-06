"""Unit tests for model_service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import model_service
from app.shared.errors import ModelProviderNotFoundError, ValidationError


def test_create_and_list_models(db_session) -> None:
    with patch.object(model_service, "validate_model_connection", return_value=None):
        row = model_service.create_model(
            db_session,
            user_id="default",
            model_name="deepseek-chat",
            api_key="sk-test-key",
            base_url="https://api.deepseek.com/v1",
            tier="light",
            is_active=True,
        )
    assert row.id is not None
    assert row.tier == "light"
    assert row.api_key_encrypted != "sk-test-key"

    models = model_service.list_models(db_session, user_id="default")
    assert len(models) == 1
    public = model_service.model_to_public_dict(row)
    assert public["has_api_key"] is True
    assert "api_key" not in public


def test_create_model_rejects_bad_tier(db_session) -> None:
    with pytest.raises(ValidationError):
        model_service.create_model(
            db_session,
            user_id="default",
            model_name="x",
            api_key="k",
            base_url="https://api.example.com/v1",
            tier="invalid",
        )


def test_get_active_provider_for_tier(db_session) -> None:
    with patch.object(model_service, "validate_model_connection", return_value=None):
        model_service.create_model(
            db_session,
            user_id="default",
            model_name="heavy-model",
            api_key="sk-heavy",
            base_url="https://api.deepseek.com/v1",
            tier="heavy",
            is_active=True,
        )
    active = model_service.get_active_provider_for_tier(db_session, "heavy", user_id="default")
    assert active is not None
    assert active.model_name == "heavy-model"


def test_delete_model(db_session) -> None:
    with patch.object(model_service, "validate_model_connection", return_value=None):
        row = model_service.create_model(
            db_session,
            user_id="default",
            model_name="temp",
            api_key="sk-temp",
            base_url="https://api.example.com/v1",
        )
    model_service.delete_model(db_session, row.id, user_id="default")
    with pytest.raises(ModelProviderNotFoundError):
        model_service.get_model(db_session, row.id, user_id="default")


def test_models_probe_candidates_deepseek() -> None:
    urls = model_service._models_probe_candidates("https://api.deepseek.com/v1")
    assert urls[0] == "https://api.deepseek.com/models"
    assert "https://api.deepseek.com/v1/models" in urls


def test_validate_model_connection_deepseek_405_then_root_ok() -> None:
    base = "https://api.deepseek.com/v1"
    key = "sk-test"

    def fake_get(url: str, **kwargs: object) -> object:
        _ = kwargs

        class Resp:
            status_code = 405 if "/v1/models" in url else 200

        return Resp()

    with patch.object(model_service, "_external_http_client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = fake_get
        assert model_service.validate_model_connection(base, key) is None


def test_validate_model_connection_falls_back_to_chat() -> None:
    base = "https://api.deepseek.com/v1"
    key = "sk-test"

    def fake_get(url: str, **kwargs: object) -> object:
        _ = url, kwargs

        class Resp:
            status_code = 405

        return Resp()

    def fake_post(url: str, **kwargs: object) -> object:
        _ = url, kwargs

        class Resp:
            status_code = 200

        return Resp()

    with patch.object(model_service, "_external_http_client") as mock_client:
        client = mock_client.return_value.__enter__.return_value
        client.get.side_effect = fake_get
        client.post.side_effect = fake_post
        assert model_service.validate_model_connection(base, key) is None


def test_validate_model_connection_rejects_401() -> None:
    class Resp:
        status_code = 401

    with patch.object(model_service, "_external_http_client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = Resp()
        err = model_service.validate_model_connection(
            "https://api.deepseek.com/v1",
            "bad-key",
        )
    assert err is not None
    assert "401" in err

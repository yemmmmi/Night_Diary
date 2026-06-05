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
            model_name="deepseek-chat",
            api_key="sk-test-key",
            base_url="https://api.deepseek.com/v1",
            tier="light",
            is_active=True,
        )
    assert row.id is not None
    assert row.tier == "light"
    assert row.api_key_encrypted != "sk-test-key"

    models = model_service.list_models(db_session)
    assert len(models) == 1
    public = model_service.model_to_public_dict(row)
    assert public["has_api_key"] is True
    assert "api_key" not in public


def test_create_model_rejects_bad_tier(db_session) -> None:
    with pytest.raises(ValidationError):
        model_service.create_model(
            db_session,
            model_name="x",
            api_key="k",
            base_url="https://api.example.com/v1",
            tier="invalid",
        )


def test_get_active_provider_for_tier(db_session) -> None:
    with patch.object(model_service, "validate_model_connection", return_value=None):
        model_service.create_model(
            db_session,
            model_name="heavy-model",
            api_key="sk-heavy",
            base_url="https://api.deepseek.com/v1",
            tier="heavy",
            is_active=True,
        )
    active = model_service.get_active_provider_for_tier(db_session, "heavy")
    assert active is not None
    assert active.model_name == "heavy-model"


def test_delete_model(db_session) -> None:
    with patch.object(model_service, "validate_model_connection", return_value=None):
        row = model_service.create_model(
            db_session,
            model_name="temp",
            api_key="sk-temp",
            base_url="https://api.example.com/v1",
        )
    model_service.delete_model(db_session, row.id)
    with pytest.raises(ModelProviderNotFoundError):
        model_service.get_model(db_session, row.id)

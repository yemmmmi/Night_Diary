"""Unit tests for models API routes."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_models_test_connection_ok(authed_client: TestClient) -> None:
    with patch(
        "app.services.model_service.validate_model_connection",
        return_value=None,
    ):
        response = authed_client.post(
            "/api/v1/models/test-connection",
            json={
                "model_name": "deepseek-chat",
                "api_key": "sk-test",
                "base_url": "https://api.deepseek.com/v1",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True


def test_models_test_connection_failure(authed_client: TestClient) -> None:
    with patch(
        "app.services.model_service.validate_model_connection",
        return_value="API 返回状态码 405",
    ):
        response = authed_client.post(
            "/api/v1/models/test-connection",
            json={
                "model_name": "deepseek-chat",
                "api_key": "sk-test",
                "base_url": "https://api.deepseek.com/v1",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "405" in (body["message"] or "")


def test_models_test_stored_connection(authed_client: TestClient) -> None:
    with patch("app.services.model_service.validate_model_connection", return_value=None):
        created = authed_client.post(
            "/api/v1/models",
            json={
                "model_name": "deepseek-chat",
                "api_key": "sk-test",
                "base_url": "https://api.deepseek.com/v1",
                "tier": "default",
            },
        )
    model_id = created.json()["id"]

    with patch(
        "app.services.model_service.test_stored_model_connection",
        return_value=None,
    ):
        response = authed_client.post(f"/api/v1/models/{model_id}/test-connection")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_models_status(authed_client: TestClient) -> None:
    response = authed_client.get("/api/v1/models/status")
    assert response.status_code == 200
    body = response.json()
    assert "tiers" in body
    assert len(body["tiers"]) == 4


def test_meta_version(authed_client: TestClient) -> None:
    response = authed_client.get("/meta/version")
    assert response.status_code == 200
    assert "version" in response.json()

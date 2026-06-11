"""Unit tests for models API routes."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_models_test_connection_ok(api_client: TestClient) -> None:
    with patch(
        "app.services.model_service.validate_model_connection",
        return_value=None,
    ):
        response = api_client.post(
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


def test_models_test_connection_failure(api_client: TestClient) -> None:
    with patch(
        "app.services.model_service.validate_model_connection",
        return_value="API 返回状态码 405",
    ):
        response = api_client.post(
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


def test_models_status(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/models/status")
    assert response.status_code == 200
    body = response.json()
    assert "tiers" in body
    assert len(body["tiers"]) == 4


def test_meta_version(api_client: TestClient) -> None:
    response = api_client.get("/meta/version")
    assert response.status_code == 200
    assert "version" in response.json()

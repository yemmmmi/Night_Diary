"""Smoke tests for tags and stats API routes."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_tags_crud(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/tags", json={"name": "工作", "color": "#112233"})
    assert created.status_code == 201
    tag_id = created.json()["id"]

    listing = api_client.get("/api/v1/tags")
    assert listing.status_code == 200
    assert any(tag["id"] == tag_id for tag in listing.json())

    deleted = api_client.delete(f"/api/v1/tags/{tag_id}")
    assert deleted.status_code == 204


def test_stats_endpoint(api_client: TestClient) -> None:
    api_client.post("/api/v1/diary/entries", json={"content": "统计测试"})
    response = api_client.get("/api/v1/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["diary_count"] >= 1
    assert "total_token_cost" in body


def test_models_create_never_returns_api_key(api_client: TestClient) -> None:
    with patch("app.services.model_service.validate_model_connection", return_value=None):
        response = api_client.post(
            "/api/v1/models",
            json={
                "model_name": "deepseek-chat",
                "api_key": "sk-secret-key",
                "base_url": "https://api.example.com/v1",
                "tier": "default",
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert body["has_api_key"] is True
    assert "api_key" not in body
    assert "sk-secret" not in str(body)

"""Unit tests for diary API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_list_diary_entries(authed_client: TestClient) -> None:
    create = authed_client.post(
        "/api/v1/diary/entries",
        json={"content": "API 路由测试日记"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["id"] > 0
    assert body["content"] == "API 路由测试日记"

    listing = authed_client.get("/api/v1/diary/entries")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_get_update_delete_diary_entry(authed_client: TestClient) -> None:
    diary_id = authed_client.post(
        "/api/v1/diary/entries",
        json={"content": "待更新日记"},
    ).json()["id"]

    got = authed_client.get(f"/api/v1/diary/entries/{diary_id}")
    assert got.status_code == 200

    updated = authed_client.put(
        f"/api/v1/diary/entries/{diary_id}",
        json={"content": "已更新日记"},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "已更新日记"

    deleted = authed_client.delete(f"/api/v1/diary/entries/{diary_id}")
    assert deleted.status_code == 204

    missing = authed_client.get(f"/api/v1/diary/entries/{diary_id}")
    assert missing.status_code == 404
    assert missing.json()["detail"]


def test_create_diary_validation_error(authed_client: TestClient) -> None:
    response = authed_client.post("/api/v1/diary/entries", json={"content": "   "})
    assert response.status_code == 422


def test_create_diary_with_explicit_date(authed_client: TestClient) -> None:
    response = authed_client.post(
        "/api/v1/diary/entries",
        json={"content": "指定日期日记", "date": "2025-06-01"},
    )
    assert response.status_code == 201
    assert response.json()["date"] == "2025-06-01"


def test_get_missing_diary_returns_app_error_shape(authed_client: TestClient) -> None:
    response = authed_client.get("/api/v1/diary/entries/9999")
    assert response.status_code == 404
    assert "detail" in response.json()

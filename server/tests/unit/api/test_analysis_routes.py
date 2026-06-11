"""Unit tests for analysis API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_diary(client: TestClient, content: str = "分析 API 测试") -> int:
    response = client.post("/api/v1/diary/entries", json={"content": content})
    assert response.status_code == 201
    return response.json()["id"]


def test_trigger_and_get_analysis(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)

    triggered = api_client.post(f"/api/v1/analysis/{diary_id}")
    assert triggered.status_code == 201
    body = triggered.json()
    assert body["diary_id"] == diary_id
    assert body["execution_tier"]
    assert body["ai_ans"]

    fetched = api_client.get(f"/api/v1/analysis/{diary_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_duplicate_analysis_returns_409(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)
    assert api_client.post(f"/api/v1/analysis/{diary_id}").status_code == 201
    duplicate = api_client.post(f"/api/v1/analysis/{diary_id}")
    assert duplicate.status_code == 409


def test_regenerate_analysis_replaces_existing(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)
    first = api_client.post(f"/api/v1/analysis/{diary_id}")
    assert first.status_code == 201

    regen = api_client.post(f"/api/v1/analysis/{diary_id}/regenerate")
    assert regen.status_code == 200
    assert regen.json()["ai_ans"]
    assert regen.json()["diary_id"] == diary_id
    assert regen.json()["ai_ans"]
    assert api_client.get(f"/api/v1/analysis/{diary_id}").status_code == 200


def test_delete_analysis_clears_reply(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)
    assert api_client.post(f"/api/v1/analysis/{diary_id}").status_code == 201

    deleted = api_client.delete(f"/api/v1/analysis/{diary_id}")
    assert deleted.status_code == 204
    assert api_client.get(f"/api/v1/analysis/{diary_id}").status_code == 404

    entry = api_client.get(f"/api/v1/diary/entries/{diary_id}")
    assert entry.status_code == 200
    assert entry.json()["ai_ans"] in (None, "")


def test_get_analysis_before_trigger_returns_404(api_client: TestClient) -> None:
    diary_id = _create_diary(api_client)
    response = api_client.get(f"/api/v1/analysis/{diary_id}")
    assert response.status_code == 404

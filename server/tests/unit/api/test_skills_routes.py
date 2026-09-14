"""Unit tests for the skill discovery routes (GET /api/v1/skills)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_skills_returns_builtin_specs(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/skills")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [item["id"] for item in items] == ["record", "insight", "plan"]
    for item in items:
        assert item["label"]
        assert item["description"]


def test_list_skills_requires_auth(api_client: TestClient) -> None:
    resp = api_client.get("/api/v1/skills")
    assert resp.status_code == 401

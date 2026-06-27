"""Unit tests for export/import API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_export_all_reachable(api_client: TestClient) -> None:
    """GET /api/v1/export/all returns 200 with valid export structure."""
    response = api_client.get("/api/v1/export/all")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert "exported_at" in body
    assert "diaries" in body
    assert "memory_cards" in body


def test_import_json_reachable(api_client: TestClient) -> None:
    """POST /api/v1/import/json accepts exported data and returns summary."""
    # First export the current (empty) state
    exported = api_client.get("/api/v1/export/all").json()

    # Import it back
    response = api_client.post("/api/v1/import/json", json={"data": exported})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "imported" in body


def test_export_route_registered_under_v1(api_client: TestClient) -> None:
    """Export routes are accessible under /api/v1 prefix (not bare /export)."""
    # Bare path without /api/v1 should return 404
    bare = api_client.get("/export/all")
    assert bare.status_code == 404

    # With /api/v1 prefix should return 200
    prefixed = api_client.get("/api/v1/export/all")
    assert prefixed.status_code == 200

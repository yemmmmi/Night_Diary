"""Unit tests for the user-mode API routes (V3.x mode system).

Exercises ``GET /api/v1/mode`` (current mode) and ``POST /api/v1/mode``
(manual override) using the shared ``authed_client`` / ``api_client`` fixtures
like the other route tests.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_current_mode_defaults_to_daily(authed_client: TestClient) -> None:
    """A brand-new user with no signals defaults to the `daily` mode."""
    resp = authed_client.get("/api/v1/mode")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] in {"daily", "followup", "introspection"}
    assert "display_name" in body


def test_manual_override_sets_mode(authed_client: TestClient) -> None:
    """Manual override returns the chosen mode and persists it."""
    resp = authed_client.post("/api/v1/mode", json={"mode": "introspection"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "introspection"
    assert resp.json()["display_name"] == "内视"
    # Subsequent GET reflects the persisted override.
    again = authed_client.get("/api/v1/mode")
    assert again.json()["mode"] == "introspection"


def test_invalid_mode_rejected(authed_client: TestClient) -> None:
    resp = authed_client.post("/api/v1/mode", json={"mode": "not-a-mode"})
    assert resp.status_code == 400

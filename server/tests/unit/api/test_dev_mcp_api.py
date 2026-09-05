"""Unit tests for the MCP Dev API endpoints (status / tools / calls)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_mcp_status_empty(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/dev/mcp/status")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_mcp_tools_lists_local_tools(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/dev/mcp/tools")
    assert resp.status_code == 200
    items = resp.json()["items"]
    names = [t["name"] for t in items]
    assert "search_diary" in names
    assert "list_todos" in names
    assert all(t["source"] == "local" for t in items)


def test_mcp_calls_empty(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/dev/mcp/calls")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


def test_mcp_calls_pagination_params(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/v1/dev/mcp/calls?page=1&page_size=5&status=success")
    assert resp.status_code == 200
    assert "total" in resp.json()

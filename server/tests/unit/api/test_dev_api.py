"""Unit tests for Dev API routes.

Tests the developer-mode endpoints for pipeline trace inspection:
- GET  /api/v1/dev/traces          — list traces with filters
- GET  /api/v1/dev/traces/{id}     — trace detail (404 when missing)
- DELETE /api/v1/dev/traces/{id}   — delete trace (404 when missing)
- GET  /api/v1/dev/stats           — aggregate statistics
- GET  /api/v1/dev/middleware-status — infrastructure health check

The Dev API routes do not require authentication, but we use the
``authed_client`` fixture (which provides a fully-bootstrapped app)
for convenience.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_traces_empty(authed_client: TestClient) -> None:
    """GET /api/v1/dev/traces should return an empty list when no traces exist."""
    response = authed_client.get("/api/v1/dev/traces")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)
    assert data["total"] == 0


def test_list_traces_with_scenario_filter(authed_client: TestClient) -> None:
    """GET /api/v1/dev/traces?scenario=diary should accept the scenario parameter."""
    response = authed_client.get("/api/v1/dev/traces?scenario=diary")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["items"], list)


def test_list_traces_with_status_filter(authed_client: TestClient) -> None:
    """GET /api/v1/dev/traces?status=completed should accept the status parameter."""
    response = authed_client.get("/api/v1/dev/traces?status=completed")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["items"], list)


def test_list_traces_pagination(authed_client: TestClient) -> None:
    """GET /api/v1/dev/traces should support page and page_size parameters."""
    response = authed_client.get("/api/v1/dev/traces?page=1&page_size=5")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


def test_get_trace_not_found(authed_client: TestClient) -> None:
    """GET /api/v1/dev/traces/{nonexistent} should return 404."""
    response = authed_client.get("/api/v1/dev/traces/nonexistent-trace-id")
    assert response.status_code == 404


def test_delete_trace_not_found(authed_client: TestClient) -> None:
    """DELETE /api/v1/dev/traces/{nonexistent} should return 404."""
    response = authed_client.delete("/api/v1/dev/traces/nonexistent-trace-id")
    assert response.status_code == 404


def test_get_dev_stats(authed_client: TestClient) -> None:
    """GET /api/v1/dev/stats should return aggregate statistics."""
    response = authed_client.get("/api/v1/dev/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_traces" in data
    assert "by_scenario" in data
    assert "avg_duration_ms" in data
    assert "error_count" in data
    assert isinstance(data["total_traces"], int)
    assert isinstance(data["by_scenario"], dict)
    assert isinstance(data["avg_duration_ms"], (int, float))
    assert isinstance(data["error_count"], int)


def test_get_middleware_status(authed_client: TestClient) -> None:
    """GET /api/v1/dev/middleware-status should return middleware health."""
    response = authed_client.get("/api/v1/dev/middleware-status")
    assert response.status_code == 200
    data = response.json()
    # Middleware status fields: redis, neo4j, langgraph, rq
    assert "redis" in data
    assert "langgraph" in data
    assert "neo4j" in data
    assert "rq" in data
    # Each value should be a boolean
    assert isinstance(data["redis"], bool)
    assert isinstance(data["langgraph"], bool)

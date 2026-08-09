"""Integration tests for P1 fault tolerance mechanisms.

Tests that streaming replies are resilient to failures:
- Streaming endpoint smoke test (no regression from P0)
- abort endpoint returns correct response for various trace_id scenarios
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_conversation(e2e_client: TestClient) -> str:
    """Create a conversation and return its id.

    Mirrors the helper in ``test_streaming_endpoint.py``: the
    ``POST /api/v1/conversations`` endpoint takes no body. The
    ``e2e_client`` fixture already carries a valid ``Authorization``
    header, so no explicit ``auth_headers`` argument is needed.
    """
    response = e2e_client.post("/api/v1/conversations")
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_streaming_endpoint_smoke_test(e2e_client: TestClient) -> None:
    """冒烟测试: 流式端点应返回 trace_id (P0 行为不退化)。"""
    conversation_id = _create_conversation(e2e_client)

    response = e2e_client.post(
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        json={"content": "你好", "auto_retrieve": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert "trace_id" in data
    assert "streaming" in data


def test_abort_returns_false_for_unknown_trace(e2e_client: TestClient) -> None:
    """abort 不存在的 trace_id 应返回 cancelled=false。"""
    conversation_id = _create_conversation(e2e_client)

    response = e2e_client.post(
        f"/api/v1/conversations/{conversation_id}/messages/abort",
        json={"trace_id": "nonexistent-trace-id"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cancelled"] is False


def test_abort_returns_false_for_empty_trace_id(e2e_client: TestClient) -> None:
    """abort 空 trace_id 应返回 cancelled=false。"""
    conversation_id = _create_conversation(e2e_client)

    response = e2e_client.post(
        f"/api/v1/conversations/{conversation_id}/messages/abort",
        json={"trace_id": ""},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cancelled"] is False


def test_abort_returns_false_for_missing_trace_key(e2e_client: TestClient) -> None:
    """abort 请求缺少 trace_id key 应返回 cancelled=false (不报错)。"""
    conversation_id = _create_conversation(e2e_client)

    response = e2e_client.post(
        f"/api/v1/conversations/{conversation_id}/messages/abort",
        json={},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cancelled"] is False

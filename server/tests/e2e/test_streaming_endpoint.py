"""End-to-end integration tests for the V3 P0 streaming message endpoint.

These tests exercise the full HTTP stack (real JWT auth, real settings,
real database) without mocking ``get_settings`` or the streaming service.
They complement the unit-level route tests in
``tests/unit/api/test_conversation_routes.py`` which patch settings to
force ``streaming_enabled=True``.

The default deployment has ``STREAMING_ENABLED=false`` so the endpoint
returns the fallback payload ``{"streaming": False, "trace_id": ""}``.
When the flag is flipped, the same endpoint must echo the client-supplied
``X-Trace-Id`` header (or generate a fresh UUID).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_conversation(e2e_client: TestClient) -> str:
    """Create a conversation and return its id.

    The ``POST /api/v1/conversations`` endpoint takes no body, so we
    mirror the pattern used by the unit route tests.
    """
    response = e2e_client.post("/api/v1/conversations")
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_streaming_endpoint_returns_trace_id_field(e2e_client: TestClient) -> None:
    """Streaming endpoint returns trace_id and streaming fields for the frontend."""
    conversation_id = _create_conversation(e2e_client)

    response = e2e_client.post(
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        json={"content": "你好", "auto_retrieve": False},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    # Both fields must always be present in the response model.
    assert "trace_id" in data
    assert "streaming" in data
    # ``streaming`` is a boolean toggle driven by STREAMING_ENABLED.
    assert isinstance(data["streaming"], bool)
    # ``trace_id`` is always a string (empty in fallback mode).
    assert isinstance(data["trace_id"], str)


def test_streaming_endpoint_404_for_unknown_conversation(e2e_client: TestClient) -> None:
    """Unknown conversation id returns 404, matching the synchronous endpoint."""
    response = e2e_client.post(
        "/api/v1/conversations/nonexistent-id/messages/stream",
        json={"content": "你好"},
    )
    assert response.status_code == 404


def test_streaming_endpoint_fallback_payload_shape(e2e_client: TestClient) -> None:
    """Default STREAMING_ENABLED=false returns a stable fallback payload.

    The frontend relies on this exact shape to decide whether to fall
    back to the synchronous endpoint, so we assert its structure.
    """
    conversation_id = _create_conversation(e2e_client)

    response = e2e_client.post(
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        json={"content": "你好"},
    )

    assert response.status_code == 200
    data = response.json()
    # Default deployment has streaming disabled.
    assert data["streaming"] is False
    assert data["trace_id"] == ""


def test_streaming_endpoint_accepts_x_trace_id_header(e2e_client: TestClient) -> None:
    """X-Trace-Id header is accepted by the endpoint without error.

    When streaming_enabled=false the trace_id is an empty string
    (fallback path). When streaming_enabled=true the client-supplied
    trace_id is echoed verbatim. Here we only verify the endpoint
    accepts the header and behaves according to the config.
    """
    conversation_id = _create_conversation(e2e_client)
    custom_trace = "my-custom-trace-12345"

    response = e2e_client.post(
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        json={"content": "你好", "auto_retrieve": False},
        headers={"X-Trace-Id": custom_trace},
    )

    assert response.status_code == 200
    data = response.json()
    if data.get("streaming"):
        # When streaming is enabled the header must be echoed verbatim.
        assert data["trace_id"] == custom_trace
    else:
        # Fallback path: trace_id is empty regardless of the header.
        assert data["trace_id"] == ""


def test_streaming_endpoint_rejects_invalid_token(e2e_client: TestClient) -> None:
    """Invalid Authorization token is rejected (401) to prove auth protection."""
    conversation_id = _create_conversation(e2e_client)

    # Override the valid default token with a well-formed but unregistered one.
    response = e2e_client.post(
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        json={"content": "你好"},
        headers={"Authorization": "Bearer invalid-token-not-registered"},
    )
    assert response.status_code == 401

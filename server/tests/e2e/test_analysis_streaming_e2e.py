"""End-to-end integration tests for the V3 P4 scene-1 streaming endpoint.

These tests exercise the full HTTP stack (real JWT auth, real settings,
real database) without mocking ``get_settings`` or the streaming service.
They mirror the scene-2 streaming e2e tests in
``tests/e2e/test_streaming_endpoint.py``.

The default deployment has ``STREAMING_ENABLED=false`` so the stream
endpoint returns the fallback payload
``{"streaming": False, "trace_id": ""}``. When the flag is flipped the
same endpoint must echo the client-supplied ``X-Trace-Id`` header (or
generate a fresh UUID) and launch the background streaming task.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_diary(e2e_client: TestClient) -> int:
    """Create a diary entry and return its id."""
    response = e2e_client.post(
        "/api/v1/diary/entries",
        json={"content": "E2E 流式分析测试: 今天心情平静。"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_analysis_stream_returns_trace_id_fields(e2e_client: TestClient) -> None:
    """Stream endpoint returns ``trace_id`` and ``streaming`` fields."""
    diary_id = _create_diary(e2e_client)

    response = e2e_client.post(f"/api/v1/analysis/{diary_id}/stream")

    assert response.status_code == 200, response.text
    data = response.json()
    # Both fields must always be present in the response model.
    assert "trace_id" in data
    assert "streaming" in data
    # ``streaming`` is a boolean toggle driven by STREAMING_ENABLED.
    assert isinstance(data["streaming"], bool)
    # ``trace_id`` is always a string (empty in fallback mode).
    assert isinstance(data["trace_id"], str)


def test_analysis_stream_fallback_payload_shape(e2e_client: TestClient) -> None:
    """Default STREAMING_ENABLED=false returns a stable fallback payload.

    The frontend relies on this exact shape to decide whether to fall
    back to the synchronous endpoint, so we assert its structure.
    """
    diary_id = _create_diary(e2e_client)

    response = e2e_client.post(f"/api/v1/analysis/{diary_id}/stream")

    assert response.status_code == 200
    data = response.json()
    # Default deployment has streaming disabled.
    assert data["streaming"] is False
    assert data["trace_id"] == ""


def test_analysis_stream_404_for_missing_diary(e2e_client: TestClient) -> None:
    """Unknown diary id returns 404, matching the synchronous endpoint.

    The stream endpoint validates diary existence up-front (mirroring the
    scene-2 conversation existence check) before the streaming flag is
    consulted, so a missing diary is rejected regardless of the flag.
    """
    response = e2e_client.post("/api/v1/analysis/999999/stream")
    assert response.status_code == 404


def test_analysis_stream_accepts_x_trace_id_header(e2e_client: TestClient) -> None:
    """``X-Trace-Id`` header is accepted by the endpoint without error.

    When streaming_enabled=false the trace_id is an empty string
    (fallback path). When streaming_enabled=true the client-supplied
    trace_id is echoed verbatim. Here we only verify the endpoint
    accepts the header and behaves according to the config.
    """
    diary_id = _create_diary(e2e_client)
    custom_trace = "my-analysis-trace-12345"

    response = e2e_client.post(
        f"/api/v1/analysis/{diary_id}/stream",
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


def test_analysis_stream_rejects_invalid_token(e2e_client: TestClient) -> None:
    """Invalid Authorization token is rejected (401) to prove auth protection."""
    diary_id = _create_diary(e2e_client)

    response = e2e_client.post(
        f"/api/v1/analysis/{diary_id}/stream",
        headers={"Authorization": "Bearer invalid-token-not-registered"},
    )
    assert response.status_code == 401


def test_analysis_abort_returns_cancelled_flag(e2e_client: TestClient) -> None:
    """Abort endpoint returns a ``cancelled`` boolean for any trace_id.

    For an unknown trace_id (no live streaming task), it must return
    ``{"cancelled": False}`` rather than erroring.
    """
    response = e2e_client.post("/api/v1/analysis/abort/unknown-trace-id")

    assert response.status_code == 200, response.text
    data = response.json()
    assert "cancelled" in data
    assert isinstance(data["cancelled"], bool)
    # No live task is registered for this trace_id in the e2e env.
    assert data["cancelled"] is False

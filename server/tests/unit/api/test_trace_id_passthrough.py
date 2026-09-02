"""Tests for X-Trace-Id header passthrough to service layer.

Verifies that the ``X-Trace-Id`` request header is correctly extracted in
the API routes and forwarded as the ``trace_id`` keyword argument to the
underlying service functions (``trigger_analysis`` and ``generate_reply``).

Uses ``monkeypatch`` to mock the service layer — same pattern as
``test_analysis_routes.py::_patch_analysis_route``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import AnalysisResponse

# ── Analysis route: trace_id passthrough ────────────────────────────────


def _patch_analysis_route(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, object]
) -> None:
    """Patch analysis route's service/mapper refs to capture ``trace_id``.

    Stubs ``trigger_analysis``, ``get_entry`` and ``analysis_to_response``
    so the handler returns a valid 201 without booting the LLM.
    """

    import app.api.v1.analysis as route

    def fake_trigger(db, did, container, *, style_fragment=None, user_id=None, trace_id=None):  # type: ignore[no-untyped-def]
        captured["trace_id"] = trace_id
        return (object(), 0)

    class _FakeEntry:
        reply = "fake reply"

    def fake_get_entry(db, did, *, user_id=None):  # type: ignore[no-untyped-def]
        return _FakeEntry()

    def fake_to_response(  # type: ignore[no-untyped-def]
        row, *, reply=None, db=None, referenced_memory_count=0, user_id=None
    ):
        return AnalysisResponse(
            id=1,
            diary_id=1,
            created_at=datetime.now(UTC),
            token_cost=0,
            cache_hit_tokens=0,
            cache_miss_tokens=0,
            output_tokens=0,
            agent_mode="multi_agent",
            execution_tier="medium",
            activated_agents="",
            reply=reply,
            referenced_memory_count=referenced_memory_count,
        )

    monkeypatch.setattr(route.analysis_service, "trigger_analysis", fake_trigger)
    monkeypatch.setattr(route.diary_service, "get_entry", fake_get_entry)
    monkeypatch.setattr(route, "analysis_to_response", fake_to_response)


def _create_diary(client: TestClient, content: str = "trace_id 测试") -> int:
    response = client.post("/api/v1/diary/entries", json={"content": content})
    assert response.status_code == 201
    return response.json()["id"]


def test_analysis_route_passes_trace_id_to_service(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """X-Trace-Id request header should be forwarded to trigger_analysis."""
    captured: dict[str, object] = {}
    _patch_analysis_route(monkeypatch, captured)

    diary_id = _create_diary(authed_client, "测试 trace_id 传递")

    trace_id = "test-trace-passthrough-123"
    response = authed_client.post(
        f"/api/v1/analysis/{diary_id}",
        headers={"X-Trace-Id": trace_id},
    )
    assert response.status_code == 201
    assert captured["trace_id"] == trace_id


def test_analysis_route_without_trace_id_passes_none(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without X-Trace-Id header, trace_id should be None."""
    captured: dict[str, object] = {}
    _patch_analysis_route(monkeypatch, captured)

    diary_id = _create_diary(authed_client, "测试无 trace_id")

    response = authed_client.post(f"/api/v1/analysis/{diary_id}")
    assert response.status_code == 201
    assert captured["trace_id"] is None


# ── Conversation route: trace_id passthrough ───────────────────────────


def test_conversation_route_passes_trace_id_to_service(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Conversation X-Trace-Id header should be forwarded to generate_reply."""
    import app.api.v1.conversation as route
    from app.services.conversation_ai_service import ChatReplyResult

    captured: dict[str, object] = {}

    def fake_generate_reply(  # type: ignore[no-untyped-def]
        db, container, *, conversation_id, content, diary_ids,
        user_id, auto_retrieve=True, trace_id=None,
        card_ids=None, plan_ids=None,
    ):
        captured["trace_id"] = trace_id
        return ChatReplyResult(
            reply_text="测试回复",
            retrieved_diary_ids=[],
            retrieved_memory_ids=[],
        )

    # Create a conversation first
    conv_response = authed_client.post("/api/v1/conversations")
    assert conv_response.status_code == 201
    conversation_id = conv_response.json()["id"]

    monkeypatch.setattr(
        route.conversation_ai_service, "generate_reply", fake_generate_reply
    )

    trace_id = "test-chat-trace-456"
    response = authed_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "你好", "diary_ids": [], "auto_retrieve": False},
        headers={"X-Trace-Id": trace_id},
    )
    assert response.status_code == 201
    assert captured["trace_id"] == trace_id


def test_conversation_route_without_trace_id_passes_none(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without X-Trace-Id header, generate_reply should receive trace_id=None."""
    import app.api.v1.conversation as route
    from app.services.conversation_ai_service import ChatReplyResult

    captured: dict[str, object] = {}

    def fake_generate_reply(  # type: ignore[no-untyped-def]
        db, container, *, conversation_id, content, diary_ids,
        user_id, auto_retrieve=True, trace_id=None,
        card_ids=None, plan_ids=None,
    ):
        captured["trace_id"] = trace_id
        return ChatReplyResult(
            reply_text="测试回复",
            retrieved_diary_ids=[],
            retrieved_memory_ids=[],
        )

    # Create a conversation first
    conv_response = authed_client.post("/api/v1/conversations")
    assert conv_response.status_code == 201
    conversation_id = conv_response.json()["id"]

    monkeypatch.setattr(
        route.conversation_ai_service, "generate_reply", fake_generate_reply
    )

    response = authed_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "你好", "diary_ids": [], "auto_retrieve": False},
    )
    assert response.status_code == 201
    assert captured["trace_id"] is None

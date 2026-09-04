"""Tests for X-Trace-Id header passthrough to service layer.

Verifies that the ``X-Trace-Id`` request header is correctly extracted in
the API routes and forwarded as the ``trace_id`` keyword argument to the
underlying service functions (``generate_reply``).

Uses ``monkeypatch`` to mock the service layer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


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
        card_ids=None, plan_ids=None, forced_skill=None,
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
        card_ids=None, plan_ids=None, forced_skill=None,
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

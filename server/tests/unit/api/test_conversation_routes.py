"""API route tests for conversations."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.services.conversation_ai_service import ChatReplyResult


def _create_conversation(authed_client: TestClient) -> str:
    response = authed_client.post("/api/v1/conversations")
    assert response.status_code == 201
    return response.json()["id"]


def test_conversation_message_flow(authed_client: TestClient) -> None:
    conversation_id = _create_conversation(authed_client)
    diary_id = authed_client.post("/api/v1/diary/entries", json={"content": "今天有点焦虑"}).json()[
        "id"
    ]

    with patch(
        "app.api.v1.conversation.conversation_ai_service.generate_reply",
        return_value=ChatReplyResult(
            reply_text="我理解你的感受，愿意多说说吗？",
            retrieved_diary_ids=[diary_id],
            retrieved_memory_ids=[],
        ),
    ):
        sent = authed_client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": "想聊聊今天", "diary_ids": [diary_id], "auto_retrieve": False},
        )

    assert sent.status_code == 201
    body = sent.json()
    assert body["message"]["role"] == "user"
    assert body["reply"]["role"] == "assistant"
    assert body["reply"]["content"] == "我理解你的感受，愿意多说说吗？"
    assert body["reply"]["retrieved_diary_ids"] == [diary_id]

    history = authed_client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert history.status_code == 200
    assert len(history.json()) == 2


def test_send_message_rejects_too_many_pins(authed_client: TestClient) -> None:
    conversation_id = _create_conversation(authed_client)
    response = authed_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "测试", "diary_ids": [1, 2, 3, 4]},
    )
    assert response.status_code == 422


def test_send_message_rejects_unknown_skill(authed_client: TestClient) -> None:
    conversation_id = _create_conversation(authed_client)
    response = authed_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "测试", "skill": "dance"},
    )
    assert response.status_code == 422


def test_send_message_passes_skill_to_generate_reply(authed_client: TestClient) -> None:
    """手动指定 skill 时透传给 generate_reply(含 None 默认)。"""
    conversation_id = _create_conversation(authed_client)

    with patch(
        "app.api.v1.conversation.conversation_ai_service.generate_reply",
        return_value=ChatReplyResult(
            reply_text="已记下。",
            retrieved_diary_ids=[],
            retrieved_memory_ids=[],
        ),
    ) as mock_generate:
        sent = authed_client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": "开了一整天会", "skill": "record", "auto_retrieve": False},
        )

    assert sent.status_code == 201
    assert mock_generate.call_args.kwargs["forced_skill"] == "record"

    with patch(
        "app.api.v1.conversation.conversation_ai_service.generate_reply",
        return_value=ChatReplyResult(
            reply_text="聊聊吧。",
            retrieved_diary_ids=[],
            retrieved_memory_ids=[],
        ),
    ) as mock_generate:
        sent = authed_client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": "随便聊聊", "auto_retrieve": False},
        )

    assert sent.status_code == 201
    assert mock_generate.call_args.kwargs["forced_skill"] is None


def test_send_message_rejects_too_many_attached_cards(authed_client: TestClient) -> None:
    conversation_id = _create_conversation(authed_client)
    response = authed_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "测试", "card_ids": ["a", "b", "c", "d"]},
    )
    assert response.status_code == 422


def test_send_message_rejects_too_many_attached_plans(authed_client: TestClient) -> None:
    conversation_id = _create_conversation(authed_client)
    response = authed_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "测试", "plan_ids": ["a", "b", "c", "d"]},
    )
    assert response.status_code == 422


def test_send_message_with_attached_cards_and_plans(authed_client: TestClient) -> None:
    """附卡片/计划随信落库: 响应回显、历史可回读, 回信侧不带附物。"""
    conversation_id = _create_conversation(authed_client)
    card_id = authed_client.post(
        "/api/v1/cards",
        json={"emotion": "平静", "event_summary": "和夜记聊了睡眠"},
    ).json()["card_id"]
    plan_id = authed_client.post(
        "/api/v1/plans",
        json={"title": "读完一本书", "motivation": "想保持输入"},
    ).json()["id"]

    with patch(
        "app.api.v1.conversation.conversation_ai_service.generate_reply",
        return_value=ChatReplyResult(
            reply_text="收到，我看看你附的卡片和计划。",
            retrieved_diary_ids=[],
            retrieved_memory_ids=[],
        ),
    ) as mock_generate:
        sent = authed_client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={
                "content": "帮我看看这两样",
                "card_ids": [card_id],
                "plan_ids": [plan_id],
                "auto_retrieve": False,
            },
        )

    assert sent.status_code == 201
    body = sent.json()
    assert body["message"]["attached_card_ids"] == [card_id]
    assert body["message"]["attached_plan_ids"] == [plan_id]
    assert body["reply"]["attached_card_ids"] is None
    assert body["reply"]["attached_plan_ids"] is None
    assert mock_generate.call_args.kwargs["card_ids"] == [card_id]
    assert mock_generate.call_args.kwargs["plan_ids"] == [plan_id]

    history = authed_client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert history.status_code == 200
    user_row = history.json()[0]
    assert user_row["role"] == "user"
    assert user_row["attached_card_ids"] == [card_id]
    assert user_row["attached_plan_ids"] == [plan_id]


# ── V3 P0: streaming endpoint ────────────────────────────────────────


def test_send_message_streaming_disabled_returns_fallback(
    authed_client: TestClient,
) -> None:
    """STREAMING_ENABLED=false (default) returns {streaming: False, trace_id: ''}."""
    conversation_id = _create_conversation(authed_client)

    # Ensure the global setting is the default (False).
    with patch("app.api.v1.conversation.get_settings") as mock_settings:
        mock_settings.return_value.streaming_enabled = False
        response = authed_client.post(
            f"/api/v1/conversations/{conversation_id}/messages/stream",
            json={"content": "你好"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body == {"streaming": False, "trace_id": ""}


def test_send_message_streaming_enabled_returns_trace_id(
    authed_client: TestClient,
) -> None:
    """STREAMING_ENABLED=true 时返回 {streaming: True, trace_id: <uuid>}。"""
    conversation_id = _create_conversation(authed_client)

    # Patch the streaming generator to a no-op AsyncMock so the background
    # task doesn't actually run the LLM pipeline.
    with (
        patch("app.api.v1.conversation.get_settings") as mock_settings,
        patch(
            "app.services.conversation_ai_service.generate_reply_streaming",
            new=AsyncMock(return_value=None),
        ),
    ):
        mock_settings.return_value.streaming_enabled = True
        response = authed_client.post(
            f"/api/v1/conversations/{conversation_id}/messages/stream",
            json={"content": "你好"},
            headers={"X-Trace-Id": "client-supplied-trace-id"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["streaming"] is True
    # When X-Trace-Id is supplied it should be echoed back.
    assert body["trace_id"] == "client-supplied-trace-id"


def test_send_message_streaming_generates_trace_id_when_missing(
    authed_client: TestClient,
) -> None:
    """When X-Trace-Id is absent, a UUID trace_id is generated."""
    conversation_id = _create_conversation(authed_client)

    with (
        patch("app.api.v1.conversation.get_settings") as mock_settings,
        patch(
            "app.services.conversation_ai_service.generate_reply_streaming",
            new=AsyncMock(return_value=None),
        ),
    ):
        mock_settings.return_value.streaming_enabled = True
        response = authed_client.post(
            f"/api/v1/conversations/{conversation_id}/messages/stream",
            json={"content": "你好"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["streaming"] is True
    # A UUID was generated server-side.
    assert isinstance(body["trace_id"], str)
    assert len(body["trace_id"]) > 0
    assert body["trace_id"] != ""


def test_send_message_streaming_unknown_conversation_404(
    authed_client: TestClient,
) -> None:
    """Unknown conversation_id should raise ConversationNotFoundError (404)."""
    response = authed_client.post(
        "/api/v1/conversations/nonexistent/messages/stream",
        json={"content": "你好"},
    )
    assert response.status_code == 404

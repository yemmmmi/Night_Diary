"""API route tests for conversations."""

from __future__ import annotations

from unittest.mock import patch

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

"""Route tests for the OpenAI-compatible facade (A5)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.conversation_ai_service import ChatReplyResult
from app.shared.streaming_events import (
    publish_reply_end,
    publish_reply_start,
    publish_text_delta,
    publish_text_end,
)

_REPLY = ChatReplyResult(
    reply_text="我在听，慢慢说。",
    retrieved_diary_ids=[],
    retrieved_memory_ids=[],
    token_info={"prompt_tokens": 3, "completion_tokens": 5, "total_tokens_used": 8},
)

_PATCH_REPLY = "app.api.v1.openai_compat.conversation_ai_service.generate_reply"


def _post(client: TestClient, payload: dict) -> object:
    return client.post("/v1/chat/completions", json=payload)


def test_non_stream_completion_shape(authed_client: TestClient) -> None:
    with patch(_PATCH_REPLY, return_value=_REPLY):
        resp = _post(
            authed_client,
            {"model": "deepseek-chat", "messages": [{"role": "user", "content": "今天很累"}]},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "deepseek-chat"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "我在听，慢慢说。"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"] == {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}


def test_uses_last_user_turn_only(authed_client: TestClient) -> None:
    with patch(_PATCH_REPLY, return_value=_REPLY) as mock_generate:
        resp = _post(
            authed_client,
            {
                "messages": [
                    {"role": "system", "content": "你是助手"},
                    {"role": "user", "content": "第一句"},
                    {"role": "assistant", "content": "旧回复"},
                    {"role": "user", "content": [{"type": "text", "text": "第二句"}]},
                ]
            },
        )
    assert resp.status_code == 200
    assert mock_generate.call_args.kwargs["content"] == "第二句"


def test_reuses_one_api_conversation(authed_client: TestClient) -> None:
    with patch(_PATCH_REPLY, return_value=_REPLY):
        assert _post(authed_client, {"messages": [{"role": "user", "content": "早"}]}).status_code == 200
        assert _post(authed_client, {"messages": [{"role": "user", "content": "晚"}]}).status_code == 200

    conversations = authed_client.get("/api/v1/conversations").json()
    api_convs = [c for c in conversations if c["title"] == "API 接入"]
    assert len(api_convs) == 1
    history = authed_client.get(f"/api/v1/conversations/{api_convs[0]['id']}/messages").json()
    assert len(history) == 4


def test_explicit_conversation_id_is_honored(authed_client: TestClient) -> None:
    conv_id = authed_client.post("/api/v1/conversations").json()["id"]
    with patch(_PATCH_REPLY, return_value=_REPLY):
        resp = _post(
            authed_client,
            {"conversation_id": conv_id, "messages": [{"role": "user", "content": "你好"}]},
        )
    assert resp.status_code == 200
    history = authed_client.get(f"/api/v1/conversations/{conv_id}/messages").json()
    assert len(history) == 2


def test_unknown_conversation_id_returns_openai_error(authed_client: TestClient) -> None:
    resp = _post(
        authed_client,
        {"conversation_id": "nope", "messages": [{"role": "user", "content": "你好"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "invalid_request_error"


def test_rejects_missing_user_message(authed_client: TestClient) -> None:
    resp = _post(authed_client, {"messages": [{"role": "system", "content": "hi"}]})
    assert resp.status_code == 400
    assert "user" in resp.json()["error"]["message"]


def test_rejects_n_greater_than_one(authed_client: TestClient) -> None:
    resp = _post(
        authed_client,
        {"n": 2, "messages": [{"role": "user", "content": "你好"}]},
    )
    assert resp.status_code == 400


def test_requires_authentication(api_client: TestClient) -> None:
    resp = api_client.post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "你好"}]}
    )
    assert resp.status_code == 401


def test_models_endpoint(authed_client: TestClient) -> None:
    resp = authed_client.get("/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    assert body["data"] and body["data"][0]["object"] == "model"


def test_streaming_completion(authed_client: TestClient) -> None:
    async def _fake_stream(**kwargs: object) -> None:
        trace_id = str(kwargs["trace_id"])
        await publish_reply_start(trace_id)
        await publish_text_delta(trace_id, "你好")
        await publish_text_delta(trace_id, "，世界")
        await publish_text_end(trace_id)
        await publish_reply_end(trace_id, usage={"total_tokens_used": 7})

    with patch(
        "app.api.v1.openai_compat.conversation_ai_service.generate_reply_streaming",
        new=_fake_stream,
    ):
        resp = _post(
            authed_client,
            {"stream": True, "messages": [{"role": "user", "content": "你好"}]},
        )

    assert resp.status_code == 200
    text = resp.text
    assert "chat.completion.chunk" in text
    assert '"role": "assistant"' in text
    assert "你好" in text and "，世界" in text
    assert '"finish_reason": "stop"' in text
    assert text.rstrip().endswith("data: [DONE]")
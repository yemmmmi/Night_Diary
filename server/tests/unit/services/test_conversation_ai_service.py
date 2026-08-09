"""Unit tests for conversation AI service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services import conversation_ai_service, conversation_service, diary_service
from app.services.conversation_ai_service import ChatReplyResult
from app.shared.errors import ValidationError


class _StubLLM:
    def invoke(self, prompt: str):
        return MagicMock(content="这是测试回复。")


def test_generate_reply_uses_pinned_and_retrieved(db_session, monkeypatch) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="今天工作很累")
    conv = conversation_service.create_conversation(db_session, user_id="default")

    container = MagicMock()
    container.ensure_ai_stack = MagicMock()
    container.retriever = None
    container.episodic_memory = None
    container._llm_for_tier = MagicMock(return_value=_StubLLM())

    with patch.object(
        conversation_ai_service,
        "_retrieve_related_diary_ids",
        return_value=[],
    ):
        result = conversation_ai_service.generate_reply(
            db_session,
            container,
            user_id="default",
            conversation_id=conv.id,
            content="帮我看看这篇日记",
            diary_ids=[entry.id],
            auto_retrieve=False,
            use_graph=False,
        )

    assert isinstance(result, ChatReplyResult)
    # Reply now includes citation section (P2 Task 8: result integration enhancement)
    assert "这是测试回复。" in result.reply_text
    assert result.retrieved_diary_ids == [entry.id]


def test_normalize_diary_ids_rejects_overflow() -> None:
    with pytest.raises(ValidationError):
        conversation_ai_service._normalize_diary_ids([1, 2, 3, 4])


# ── PR-4: generate_card_from_conversation ──


class _StubCardLLM:
    """Returns a fixed JSON card summary."""

    def invoke(self, prompt: str):
        return MagicMock(
            content='{"event_summary": "工作压力大导致焦虑", "tags": ["工作", "焦虑", "压力"]}'
        )


def test_generate_card_returns_real_emotion_not_hardcoded(db_session) -> None:
    """Card-gen must return emotion based on user message content, not hardcoded '平静'."""
    conv = conversation_service.create_conversation(db_session, user_id="default")
    conversation_service.add_user_message_and_reply(
        db_session,
        user_id="default",
        conversation_id=conv.id,
        content="今天工作太累了，焦虑得睡不着",
        reply_content="我理解你的感受",
    )

    container = MagicMock()
    container.ensure_ai_stack = MagicMock()
    container._llm_for_tier = MagicMock(return_value=_StubCardLLM())

    result = conversation_ai_service.generate_card_from_conversation(
        db_session,
        container,
        user_id="default",
        conversation_id=conv.id,
    )

    # "焦虑" is a negative keyword → emotion should be "低落", not "平静"
    assert result["emotion"] != "平静"
    assert result["emotion"] == "低落"
    assert "event_summary" in result
    assert "tags" in result
    assert isinstance(result["tags"], list)


def test_generate_card_positive_emotion(db_session) -> None:
    """Positive user message → emotion should be '积极'."""
    conv = conversation_service.create_conversation(db_session, user_id="default")
    conversation_service.add_user_message_and_reply(
        db_session,
        user_id="default",
        conversation_id=conv.id,
        content="今天很开心，感觉很幸福",
        reply_content="太好了",
    )

    container = MagicMock()
    container.ensure_ai_stack = MagicMock()
    container._llm_for_tier = MagicMock(return_value=_StubCardLLM())

    result = conversation_ai_service.generate_card_from_conversation(
        db_session,
        container,
        user_id="default",
        conversation_id=conv.id,
    )
    assert result["emotion"] == "积极"


def test_generate_card_fallback_when_llm_unavailable(db_session) -> None:
    """When LLM is None, should still return emotion + fallback summary."""
    conv = conversation_service.create_conversation(db_session, user_id="default")
    conversation_service.add_user_message_and_reply(
        db_session,
        user_id="default",
        conversation_id=conv.id,
        content="很难过，很痛苦，感觉撑不住了",
        reply_content="我陪着你",
    )

    container = MagicMock()
    container.ensure_ai_stack = MagicMock()
    container._llm_for_tier = MagicMock(return_value=None)

    result = conversation_ai_service.generate_card_from_conversation(
        db_session,
        container,
        user_id="default",
        conversation_id=conv.id,
    )
    assert result["emotion"] == "低落"
    assert "event_summary" in result
    assert result["tags"] == ["夜话"]


def test_generate_card_empty_conversation(db_session) -> None:
    """Empty conversation → returns neutral default."""
    conv = conversation_service.create_conversation(db_session, user_id="default")

    container = MagicMock()
    container.ensure_ai_stack = MagicMock()

    result = conversation_ai_service.generate_card_from_conversation(
        db_session,
        container,
        user_id="default",
        conversation_id=conv.id,
    )
    assert result["emotion"] == "平静"
    assert result["event_summary"] == "暂无对话内容"


# ── V3 P0: generate_reply_streaming ──────────────────────────────────


def test_split_into_chunks_empty_returns_empty_list() -> None:
    """空字符串应返回空列表。"""
    assert conversation_ai_service._split_into_chunks("") == []


def test_split_into_chunks_chinese_punctuation() -> None:
    """Chinese end-of-sentence marks act as split points and stay with the prior chunk."""
    text = "你好。世界！今天怎么样？"
    chunks = conversation_ai_service._split_into_chunks(text, chunk_size=20)
    assert chunks == ["你好。", "世界！", "今天怎么样？"]


def test_split_into_chunks_english_punctuation() -> None:
    """English end-of-sentence marks and newlines also act as split points."""
    text = "Hello world. How are you? I am fine!"
    chunks = conversation_ai_service._split_into_chunks(text, chunk_size=20)
    assert chunks == ["Hello world.", "How are you?", "I am fine!"]


def test_split_into_chunks_long_sentence_subdivided() -> None:
    """超过 chunk_size 的句子应被进一步切分成等长块。"""
    text = "这是一段非常非常长的中文句子没有任何标点符号应该被切分成多个小块来模拟流式输出"
    # 39 chars total → 4 chunks of (10, 10, 10, 9).
    chunks = conversation_ai_service._split_into_chunks(text, chunk_size=10)
    assert len(chunks) == 4
    # All chunks except the last are exactly chunk_size.
    assert all(len(c) == 10 for c in chunks[:-1])
    assert len(chunks[-1]) == 9
    assert "".join(chunks) == text


def test_split_into_chunks_newline_also_splits() -> None:
    """换行符应作为切分点。"""
    text = "第一行\n第二行\n第三行"
    chunks = conversation_ai_service._split_into_chunks(text, chunk_size=20)
    assert chunks == ["第一行", "第二行", "第三行"]


async def test_generate_reply_streaming_crisis_publishes_single_chunk(
    db_session,
) -> None:
    """Crisis detection result is published via SSE as a single TEXT_DELTA (not chunked)."""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    bus = get_event_bus()
    trace_id = "test-streaming-crisis"
    queue = await bus.subscribe(trace_id)

    container = MagicMock()
    crisis_result = ChatReplyResult(
        reply_text="安全模板：请联系心理热线。",
        retrieved_diary_ids=[],
        retrieved_memory_ids=[],
        is_crisis=True,
    )

    with patch.object(conversation_ai_service, "generate_reply", return_value=crisis_result):
        await conversation_ai_service.generate_reply_streaming(
            db_session,
            container,
            conversation_id="conv-1",
            content="我想结束这一切",
            diary_ids=[],
            user_id="default",
            trace_id=trace_id,
        )

    # Drain all events from the queue.
    events: list[dict] = []
    while not queue.empty():
        events.append(queue.get_nowait())

    # Expect: REPLY_START, one TEXT_DELTA, TEXT_END, REPLY_END.
    types = [e["type"] for e in events]
    assert types == [
        StreamingEventType.REPLY_START,
        StreamingEventType.TEXT_DELTA,
        StreamingEventType.TEXT_END,
        StreamingEventType.REPLY_END,
    ]
    # The crisis branch should publish the safe template as ONE chunk.
    delta_events = [e for e in events if e["type"] == StreamingEventType.TEXT_DELTA]
    assert len(delta_events) == 1
    assert delta_events[0]["text"] == "安全模板：请联系心理热线。"
    # REPLY_START should carry crisis_signal intent.
    assert events[0]["intent"] == "crisis_signal"

    await bus.unsubscribe(trace_id, queue)


async def test_generate_reply_streaming_non_crisis_publishes_multiple_chunks(
    db_session,
) -> None:
    """非危机结果应通过 SSE 分段发布 TEXT_DELTA。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    bus = get_event_bus()
    trace_id = "test-streaming-normal"
    queue = await bus.subscribe(trace_id)

    container = MagicMock()
    reply_text = "你好。今天天气不错。要一起散步吗？"
    normal_result = ChatReplyResult(
        reply_text=reply_text,
        retrieved_diary_ids=[],
        retrieved_memory_ids=[],
        is_crisis=False,
        token_info={"total_tokens_used": 42},
    )

    with patch.object(conversation_ai_service, "generate_reply", return_value=normal_result):
        await conversation_ai_service.generate_reply_streaming(
            db_session,
            container,
            conversation_id="conv-1",
            content="你好",
            diary_ids=[],
            user_id="default",
            trace_id=trace_id,
        )

    events: list[dict] = []
    while not queue.empty():
        events.append(queue.get_nowait())

    types = [e["type"] for e in events]
    # Expect: REPLY_START, 3 TEXT_DELTA, TEXT_END, REPLY_END.
    assert types[0] == StreamingEventType.REPLY_START
    assert types[-2] == StreamingEventType.TEXT_END
    assert types[-1] == StreamingEventType.REPLY_END
    delta_events = [e for e in events if e["type"] == StreamingEventType.TEXT_DELTA]
    assert len(delta_events) == 3  # three sentences
    # Reassembled text matches the original reply.
    reassembled = "".join(e["text"] for e in delta_events)
    assert reassembled == reply_text
    # REPLY_END should carry the token usage info.
    reply_end_event = events[-1]
    assert reply_end_event["usage"]["total_tokens_used"] == 42

    await bus.unsubscribe(trace_id, queue)


async def test_generate_reply_streaming_no_trace_id_publishes_nothing(
    db_session,
) -> None:
    """Empty trace_id must not publish any event to the bus (no SSE subscriber)."""
    from app.shared.trace_event_bus import get_event_bus

    bus = get_event_bus()
    # Use a sentinel trace_id we never subscribe to, to ensure no events land.
    trace_id_unused = "should-not-appear"
    queue = await bus.subscribe(trace_id_unused)

    container = MagicMock()
    normal_result = ChatReplyResult(
        reply_text="hello",
        retrieved_diary_ids=[],
        retrieved_memory_ids=[],
    )

    with patch.object(conversation_ai_service, "generate_reply", return_value=normal_result):
        # Empty trace_id → early return after generate_reply.
        await conversation_ai_service.generate_reply_streaming(
            db_session,
            container,
            conversation_id="conv-1",
            content="hi",
            diary_ids=[],
            user_id="default",
            trace_id="",
        )

    # Nothing should have been published to the unused trace_id.
    assert queue.empty()

    await bus.unsubscribe(trace_id_unused, queue)

"""Unit tests for conversation AI service."""

from __future__ import annotations

import asyncio
import contextlib
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
    """Crisis detection result is published via SSE as a single TEXT_DELTA."""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    bus = get_event_bus()
    trace_id = "test-streaming-crisis"
    queue = await bus.subscribe(trace_id)

    container = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.is_crisis = True
    mock_ctx.safe_response = "安全模板：请联系心理热线。"

    with patch.object(
        conversation_ai_service, "_prepare_reply_context", return_value=mock_ctx
    ):
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


async def test_generate_reply_streaming_non_crisis_delegates_to_astream(
    db_session,
) -> None:
    """非危机路径应委托给 run_conversation_loop_streaming 并发布 TEXT_DELTA。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    bus = get_event_bus()
    trace_id = "test-streaming-normal"
    queue = await bus.subscribe(trace_id)

    container = MagicMock()
    reply_tokens = ["你好。", "今天天气不错。", "要一起散步吗？"]

    mock_ctx = MagicMock()
    mock_ctx.is_crisis = False
    mock_ctx.pinned_diaries_text = ""
    mock_ctx.retrieved_diaries_text = ""
    mock_ctx.episodic_text = ""
    mock_ctx.memory_ids = []
    mock_ctx.tools = None
    mock_ctx.crisis_guard = None
    mock_ctx.intent_result = None

    async def mock_stream(**kwargs):
        """Mimic run_conversation_loop_streaming: publish events + yield tokens."""
        from app.shared.streaming_events import (
            publish_reply_end,
            publish_reply_start,
            publish_text_delta,
            publish_text_end,
        )

        tid = kwargs.get("trace_id", "")
        await publish_reply_start(tid, intent="casual_chat")
        for token in reply_tokens:
            await publish_text_delta(tid, token)
            yield token
        await publish_text_end(tid)
        await publish_reply_end(tid, usage={"total_tokens_used": 42})

    with patch.object(
        conversation_ai_service, "_prepare_reply_context", return_value=mock_ctx
    ), patch(
        "app.services.ai.conversation_loop.run_conversation_loop_streaming",
        side_effect=mock_stream,
    ):
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
    assert len(delta_events) == 3  # three tokens
    # Reassembled text matches the original reply.
    reassembled = "".join(e["text"] for e in delta_events)
    assert reassembled == "".join(reply_tokens)
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
    mock_ctx = MagicMock()
    mock_ctx.is_crisis = False

    with patch.object(
        conversation_ai_service, "_prepare_reply_context", return_value=mock_ctx
    ):
        # Empty trace_id → early return after _prepare_reply_context.
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


# ── P1 Task 3: _terminating_reply guarantee tests ─────────────────────


async def test_streaming_emits_reply_end_on_prepare_context_failure() -> None:
    """_prepare_reply_context 抛异常时，generate_reply_streaming 必须发出 REPLY_END。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-trace-ctx-failure"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    try:
        with patch.object(
            conversation_ai_service,
            "_prepare_reply_context",
            side_effect=RuntimeError("Context prep crashed"),
        ):
            # Should NOT raise — the exception is caught by the try/finally.
            await conversation_ai_service.generate_reply_streaming(
                db=MagicMock(),
                container=MagicMock(),
                conversation_id="test-conv",
                content="你好",
                diary_ids=[],
                user_id="test-user",
                trace_id=trace_id,
            )

        # Collect all events published to the subscribed queue.
        events: list[dict] = []
        while not queue.empty():
            events.append(queue.get_nowait())

        # Must carry a REPLY_END event with the error marker.
        reply_ends = [e for e in events if e.get("type") == StreamingEventType.REPLY_END]
        assert len(reply_ends) >= 1, (
            f"Expected REPLY_END event, got events: {[e.get('type') for e in events]}"
        )
        assert reply_ends[-1]["error"] is not None
        assert "Context prep crashed" in reply_ends[-1]["error"]
    finally:
        await bus.unsubscribe(trace_id, queue)


async def test_streaming_emits_reply_end_on_cancel() -> None:
    """generate_reply_streaming 被 cancel 时必须发出 REPLY_END。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-trace-cancel"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    try:
        mock_ctx = MagicMock()
        mock_ctx.is_crisis = False
        mock_ctx.pinned_diaries_text = ""
        mock_ctx.retrieved_diaries_text = ""
        mock_ctx.episodic_text = ""
        mock_ctx.memory_ids = []
        mock_ctx.tools = None
        mock_ctx.crisis_guard = None
        mock_ctx.intent_result = None

        async def slow_stream(**kwargs):
            """Mimic run_conversation_loop_streaming with delays for cancellation window."""
            from app.shared.streaming_events import (
                publish_reply_start,
                publish_text_delta,
            )

            tid = kwargs.get("trace_id", "")
            await publish_reply_start(tid, intent="casual_chat")
            for _ in range(50):
                await publish_text_delta(tid, "字")
                yield "字"
                await asyncio.sleep(0.05)

        with patch.object(
            conversation_ai_service, "_prepare_reply_context", return_value=mock_ctx
        ), patch(
            "app.services.ai.conversation_loop.run_conversation_loop_streaming",
            side_effect=slow_stream,
        ):
            task = asyncio.create_task(
                conversation_ai_service.generate_reply_streaming(
                    db=MagicMock(),
                    container=MagicMock(),
                    conversation_id="test-conv",
                    content="你好",
                    diary_ids=[],
                    user_id="test-user",
                    trace_id=trace_id,
                )
            )
            # Let the task reach the streaming loop (REPLY_START + a few deltas).
            await asyncio.sleep(0.15)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        events: list[dict] = []
        while not queue.empty():
            events.append(queue.get_nowait())

        reply_ends = [e for e in events if e.get("type") == StreamingEventType.REPLY_END]
        assert len(reply_ends) >= 1, (
            f"Expected REPLY_END on cancel, got: {[e.get('type') for e in events]}"
        )
    finally:
        await bus.unsubscribe(trace_id, queue)


async def test_streaming_normal_path_single_reply_end() -> None:
    """正常路径只发一次 REPLY_END，不重复。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-trace-normal"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    try:
        mock_ctx = MagicMock()
        mock_ctx.is_crisis = False
        mock_ctx.pinned_diaries_text = ""
        mock_ctx.retrieved_diaries_text = ""
        mock_ctx.episodic_text = ""
        mock_ctx.memory_ids = []
        mock_ctx.tools = None
        mock_ctx.crisis_guard = None
        mock_ctx.intent_result = None

        async def mock_stream(**kwargs):
            from app.shared.streaming_events import (
                publish_reply_end,
                publish_reply_start,
                publish_text_delta,
                publish_text_end,
            )

            tid = kwargs.get("trace_id", "")
            await publish_reply_start(tid, intent="casual_chat")
            await publish_text_delta(tid, "你好呀")
            yield "你好呀"
            await publish_text_end(tid)
            await publish_reply_end(tid)

        with patch.object(
            conversation_ai_service, "_prepare_reply_context", return_value=mock_ctx
        ), patch(
            "app.services.ai.conversation_loop.run_conversation_loop_streaming",
            side_effect=mock_stream,
        ):
            await conversation_ai_service.generate_reply_streaming(
                db=MagicMock(),
                container=MagicMock(),
                conversation_id="test-conv",
                content="你好",
                diary_ids=[],
                user_id="test-user",
                trace_id=trace_id,
            )

        events: list[dict] = []
        while not queue.empty():
            events.append(queue.get_nowait())

        reply_ends = [e for e in events if e.get("type") == StreamingEventType.REPLY_END]
        assert len(reply_ends) == 1, (
            f"Expected exactly 1 REPLY_END, got {len(reply_ends)}"
        )
    finally:
        await bus.unsubscribe(trace_id, queue)


# ── P3 Task 7: _prepare_reply_context extraction + real astream ──────


def test_prepare_reply_context_detects_crisis(stub_container, db_session) -> None:
    """_prepare_reply_context 对危机输入应返回 is_crisis=True。"""
    from app.services.conversation_ai_service import _prepare_reply_context

    ctx = _prepare_reply_context(
        db_session,
        stub_container,
        conversation_id="conv-crisis",
        content="我不想活了",
        diary_ids=[],
        user_id="user-1",
        auto_retrieve=False,
        crisis_guard=None,
        trace_id=None,
    )
    assert ctx.is_crisis is True
    assert ctx.safe_response is not None


def test_prepare_reply_context_safe_input(stub_container, db_session) -> None:
    """_prepare_reply_context 对安全输入应返回 is_crisis=False。"""
    from app.services.conversation_ai_service import _prepare_reply_context

    ctx = _prepare_reply_context(
        db_session,
        stub_container,
        conversation_id="conv-safe",
        content="你好",
        diary_ids=[],
        user_id="user-1",
        auto_retrieve=False,
        crisis_guard=None,
        trace_id="trace-1",
    )
    assert ctx.is_crisis is False
    assert ctx.conversation_id == "conv-safe"


async def test_generate_reply_streaming_uses_real_astream(
    stub_container, db_session
) -> None:
    """generate_reply_streaming 应走真实 astream（不再走模拟分块）。"""
    from app.services import conversation_ai_service as svc
    from app.services.conversation_ai_service import generate_reply_streaming
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-real-stream"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    mock_ctx = MagicMock()
    mock_ctx.is_crisis = False
    mock_ctx.intent_result = None
    mock_ctx.pinned_diaries_text = ""
    mock_ctx.retrieved_diaries_text = ""
    mock_ctx.episodic_text = ""
    mock_ctx.memory_ids = []
    mock_ctx.tools = None
    mock_ctx.crisis_guard = None
    mock_ctx.content = "你好"

    async def mock_stream(**kwargs):
        from app.shared.streaming_events import (
            publish_reply_end,
            publish_reply_start,
            publish_text_delta,
            publish_text_end,
        )

        tid = kwargs.get("trace_id", "")
        await publish_reply_start(tid, intent="casual_chat")
        for token in ["你", "好", "呀"]:
            await publish_text_delta(tid, token)
            yield token
        await publish_text_end(tid)
        await publish_reply_end(tid)

    with patch.object(
        svc, "_prepare_reply_context", return_value=mock_ctx
    ), patch(
        "app.services.ai.conversation_loop.run_conversation_loop_streaming",
        side_effect=mock_stream,
    ):
        await generate_reply_streaming(
            db=db_session,
            container=stub_container,
            conversation_id="conv-1",
            content="你好",
            diary_ids=[],
            user_id="user-1",
            trace_id=trace_id,
        )

    events: list[dict] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    deltas = [e for e in events if e.get("type") == StreamingEventType.TEXT_DELTA]
    assert len(deltas) >= 1


# ── V3 P7: middleware pipeline regression ─────────────────────────────


async def test_generate_reply_streaming_crisis_still_short_circuits_with_pipeline(
    db_session,
) -> None:
    """P7 回归：接入默认中间件管道后，crisis intent 仍走安全模板短路。

    The middleware must NOT bypass the crisis short-circuit: the safe
    template is published as a single TEXT_DELTA with exactly one REPLY_END,
    and the FinalizeMiddleware still schedules the severe-signal audit
    write-back (persist_atom).
    """
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    bus = get_event_bus()
    trace_id = "test-p7-crisis"
    queue = await bus.subscribe(trace_id)

    container = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.is_crisis = True
    mock_ctx.safe_response = "安全模板：请联系心理热线。"

    with patch.object(
        conversation_ai_service, "_prepare_reply_context", return_value=mock_ctx
    ), patch("app.infrastructure.task_queue.enqueue_task") as mock_enqueue:
        await conversation_ai_service.generate_reply_streaming(
            db_session,
            container,
            conversation_id="conv-crisis-p7",
            content="我不想活了",
            diary_ids=[],
            user_id="default",
            trace_id=trace_id,
        )

    events: list[dict] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    types = [e["type"] for e in events]
    assert types == [
        StreamingEventType.REPLY_START,
        StreamingEventType.TEXT_DELTA,
        StreamingEventType.TEXT_END,
        StreamingEventType.REPLY_END,
    ]
    delta_events = [e for e in events if e["type"] == StreamingEventType.TEXT_DELTA]
    assert len(delta_events) == 1
    assert delta_events[0]["text"] == "安全模板：请联系心理热线。"
    # 危机审计写回：severe signal → FinalizeMiddleware 调度 persist_atom
    assert mock_enqueue.called
    assert mock_enqueue.call_args.args[0].__name__ == "persist_atom"


# ── V3 tree-hole: scene-2 diary reference prefers the day digest ────────


def test_format_retrieved_diaries_prefers_day_digest(db_session) -> None:
    """置顶/检索日记：有 digest 用 digest 块，无 digest 回落全文摘录。"""
    from datetime import date

    from app.infrastructure.models.diary_entry import DiaryEntryRow
    from app.services import diary_service
    from app.services.conversation_ai_service import _format_retrieved_diaries
    from app.services.digest_service import upsert_digest
    from app.shared.digest import DiaryDigest, DiaryDigestPart

    # 有 digest 的日记
    digest_entry = DiaryEntryRow(
        user_id="user-d", content="今天很焦虑，加班到很晚。", date=date(2026, 8, 12)
    )
    db_session.add(digest_entry)
    db_session.commit()
    db_session.refresh(digest_entry)

    upsert_digest(
        db_session,
        user_id="user-d",
        day=date(2026, 8, 12),
        digest=DiaryDigest(
            digest_type="basic",
            date=date(2026, 8, 12),
            source="llm",
            diary=DiaryDigestPart(
                intent="emotional_support",
                emotion="焦虑",
                topics=["加班"],
                summary="加班到很晚，整体焦虑。",
                temporal_refs=[],
            ),
        ),
    )
    db_session.commit()

    # 无 digest 的旧日记
    legacy_entry = diary_service.create_entry(
        db_session, user_id="user-d", content="旧日记全文很长……"
    )

    text = _format_retrieved_diaries(
        db_session, [digest_entry.id, legacy_entry.id], user_id="user-d"
    )

    assert "当日摘要" in text  # digest 块优先
    assert "加班到很晚，整体焦虑" in text
    assert "情绪：焦虑" in text
    assert "旧日记全文很长" in text  # 无 digest → 回落全文摘录

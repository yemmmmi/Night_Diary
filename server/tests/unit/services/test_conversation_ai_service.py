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
        db_session, container, user_id="default", conversation_id=conv.id,
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
        db_session, container, user_id="default", conversation_id=conv.id,
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
        db_session, container, user_id="default", conversation_id=conv.id,
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
        db_session, container, user_id="default", conversation_id=conv.id,
    )
    assert result["emotion"] == "平静"
    assert result["event_summary"] == "暂无对话内容"

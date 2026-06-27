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
    entry = diary_service.create_entry(db_session, content="今天工作很累")
    conv = conversation_service.create_conversation(db_session)

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
            conversation_id=conv.id,
            content="帮我看看这篇日记",
            diary_ids=[entry.id],
            auto_retrieve=False,
        )

    assert isinstance(result, ChatReplyResult)
    assert result.reply_text == "这是测试回复。"
    assert result.retrieved_diary_ids == [entry.id]


def test_normalize_diary_ids_rejects_overflow() -> None:
    with pytest.raises(ValidationError):
        conversation_ai_service._normalize_diary_ids([1, 2, 3, 4])

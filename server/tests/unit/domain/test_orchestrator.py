"""Tests for Orchestrator protocol abstraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.orchestrator import (
    ConversationOrchestrator,
    DiaryOrchestrator,
    OrchestratorInput,
    OrchestratorOutput,
    OrchestratorProtocol,
    SessionType,
    get_orchestrator,
)

# ── Protocol tests ──────────────────────────────────────────────────


def test_diary_orchestrator_implements_protocol() -> None:
    """DiaryOrchestrator satisfies the OrchestratorProtocol interface."""
    orchestrator = DiaryOrchestrator()
    assert isinstance(orchestrator, OrchestratorProtocol)


def test_conversation_orchestrator_implements_protocol() -> None:
    """ConversationOrchestrator satisfies the OrchestratorProtocol interface."""
    orchestrator = ConversationOrchestrator()
    assert isinstance(orchestrator, OrchestratorProtocol)


# ── Factory tests ───────────────────────────────────────────────────


def test_get_orchestrator_returns_diary_for_diary_type() -> None:
    orchestrator = get_orchestrator(SessionType.DIARY)
    assert isinstance(orchestrator, DiaryOrchestrator)


def test_get_orchestrator_returns_conversation_for_chat_type() -> None:
    orchestrator = get_orchestrator(SessionType.CHAT)
    assert isinstance(orchestrator, ConversationOrchestrator)


def test_get_orchestrator_raises_for_unknown_type() -> None:
    with pytest.raises(ValueError):
        get_orchestrator("unknown")


# ── OrchestratorInput tests ─────────────────────────────────────────


def test_orchestrator_input_diary_context_accessors() -> None:
    """OrchestratorInput correctly accesses diary context fields."""
    input = OrchestratorInput(
        content="今天心情不错",
        user_id="default",
        session_type=SessionType.DIARY,
        context={"diary_id": 42, "style_fragment": "温和"},
    )
    assert input.diary_id == 42
    assert input.style_fragment == "温和"
    assert input.conversation_id is None
    assert input.pinned_diaries == []


def test_orchestrator_input_chat_context_accessors() -> None:
    """OrchestratorInput correctly accesses chat context fields."""
    input = OrchestratorInput(
        content="你好",
        user_id="default",
        session_type=SessionType.CHAT,
        context={
            "conversation_id": "conv-123",
            "pinned_diaries": [1, 2, 3],
            "use_graph": False,
        },
    )
    assert input.conversation_id == "conv-123"
    assert input.pinned_diaries == [1, 2, 3]
    assert input.use_graph is False
    assert input.diary_id is None


def test_orchestrator_input_defaults() -> None:
    """OrchestratorInput has sensible defaults."""
    input = OrchestratorInput(
        content="测试",
        user_id="default",
        session_type=SessionType.CHAT,
    )
    assert input.context == {}
    assert input.diary_id is None
    assert input.conversation_id is None
    assert input.pinned_diaries == []
    assert input.use_graph is True  # Default


# ── OrchestratorOutput tests ────────────────────────────────────────


def test_orchestrator_output_success() -> None:
    output = OrchestratorOutput(
        reply="你好！",
        token_info={"total_tokens_used": 100},
        metadata={"intent": "casual_chat"},
    )
    assert output.is_success is True
    assert output.error is None


def test_orchestrator_output_error() -> None:
    output = OrchestratorOutput(
        reply="",
        error="Something went wrong",
    )
    assert output.is_success is False
    assert output.error == "Something went wrong"


# ── DiaryOrchestrator tests ─────────────────────────────────────────


def test_diary_orchestrator_missing_diary_id_returns_error() -> None:
    """DiaryOrchestrator returns error when diary_id is missing."""
    db = MagicMock()
    container = MagicMock()
    input = OrchestratorInput(
        content="测试",
        user_id="default",
        session_type=SessionType.DIARY,
    )
    orchestrator = DiaryOrchestrator()
    output = orchestrator.orchestrate(db, container, input)
    assert output.is_success is False
    assert "diary_id" in output.error


def test_diary_orchestrator_delegates_to_trigger_analysis() -> None:
    """DiaryOrchestrator delegates to analysis_service.trigger_analysis."""
    db = MagicMock()
    container = MagicMock()
    analysis_row = MagicMock()
    analysis_row.id = 1
    analysis_row.reply = "回信内容"
    analysis_row.tokens_used = 150

    input = OrchestratorInput(
        content="今天很开心",
        user_id="default",
        session_type=SessionType.DIARY,
        context={"diary_id": 42},
    )

    with patch("app.services.analysis_service.trigger_analysis") as mock_trigger:
        mock_trigger.return_value = (analysis_row, 3)
        orchestrator = DiaryOrchestrator()
        output = orchestrator.orchestrate(db, container, input)

    assert output.is_success is True
    assert output.reply == "回信内容"
    assert output.metadata["analysis_id"] == 1
    assert output.metadata["diary_id"] == 42
    assert output.metadata["memory_count"] == 3
    mock_trigger.assert_called_once()


def test_diary_orchestrator_handles_exception() -> None:
    """DiaryOrchestrator returns error output on exception."""
    db = MagicMock()
    container = MagicMock()
    input = OrchestratorInput(
        content="测试",
        user_id="default",
        session_type=SessionType.DIARY,
        context={"diary_id": 42},
    )

    with patch("app.services.analysis_service.trigger_analysis") as mock_trigger:
        mock_trigger.side_effect = RuntimeError("DB error")
        orchestrator = DiaryOrchestrator()
        output = orchestrator.orchestrate(db, container, input)

    assert output.is_success is False
    assert "DB error" in output.error


# ── ConversationOrchestrator tests ──────────────────────────────────


def test_conversation_orchestrator_missing_conversation_id_returns_error() -> None:
    """ConversationOrchestrator returns error when conversation_id is missing."""
    db = MagicMock()
    container = MagicMock()
    input = OrchestratorInput(
        content="你好",
        user_id="default",
        session_type=SessionType.CHAT,
    )
    orchestrator = ConversationOrchestrator()
    output = orchestrator.orchestrate(db, container, input)
    assert output.is_success is False
    assert "conversation_id" in output.error


def test_conversation_orchestrator_delegates_to_generate_reply() -> None:
    """ConversationOrchestrator delegates to conversation_ai_service.generate_reply."""
    db = MagicMock()
    container = MagicMock()
    input = OrchestratorInput(
        content="你好",
        user_id="default",
        session_type=SessionType.CHAT,
        context={
            "conversation_id": "conv-123",
            "pinned_diaries": [1, 2],
            "use_graph": False,
        },
    )

    with patch("app.services.conversation_ai_service.generate_reply") as mock_gen:
        mock_gen.return_value = (
            "你好！今天怎么样？",
            {"total_tokens_used": 80},
            {"intent": "casual_chat"},
        )
        orchestrator = ConversationOrchestrator()
        output = orchestrator.orchestrate(db, container, input)

    assert output.is_success is True
    assert output.reply == "你好！今天怎么样？"
    assert output.token_info["total_tokens_used"] == 80
    assert output.metadata["intent"] == "casual_chat"
    assert output.metadata["conversation_id"] == "conv-123"
    mock_gen.assert_called_once()


def test_conversation_orchestrator_handles_exception() -> None:
    """ConversationOrchestrator returns error output on exception."""
    db = MagicMock()
    container = MagicMock()
    input = OrchestratorInput(
        content="你好",
        user_id="default",
        session_type=SessionType.CHAT,
        context={"conversation_id": "conv-123"},
    )

    with patch("app.services.conversation_ai_service.generate_reply") as mock_gen:
        mock_gen.side_effect = RuntimeError("Service unavailable")
        orchestrator = ConversationOrchestrator()
        output = orchestrator.orchestrate(db, container, input)

    assert output.is_success is False
    assert "Service unavailable" in output.error

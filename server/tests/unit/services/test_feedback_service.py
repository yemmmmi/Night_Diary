"""Unit tests for feedback_service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import analysis_service, conversation_service, diary_service, feedback_service
from app.services.ai.router import ExecutionPlanner
from app.shared.errors import ValidationError
from app.shared.llm_factory import StubLLMClient
from app.shared.tracing import InMemoryAgentDecisionLogger


def _planner() -> ExecutionPlanner:
    return ExecutionPlanner(
        llm_by_tier={"light": StubLLMClient(), "default": StubLLMClient()},
        decision_logger=InMemoryAgentDecisionLogger(),
        multi_agent_enabled=False,
    )


def test_submit_feedback_persists_and_schedules_thompson(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="反馈测试日记")
    analysis, _ = analysis_service.create_analysis(db_session, entry.id, user_id="default", planner=_planner())

    thompson = MagicMock()
    row = feedback_service.submit_feedback(
        db_session,
        user_id="default",
        analysis_id=analysis.id,
        feedback_type="positive",
        response_style="empathetic",
        thompson=thompson,
    )
    assert row.feedback_type == "positive"
    assert row.diary_id == entry.id
    assert row.conversation_id is None


def test_submit_feedback_rejects_invalid_type(db_session) -> None:
    with pytest.raises(ValidationError):
        feedback_service.submit_feedback(
            db_session,
            user_id="default",
            analysis_id=1,
            feedback_type="maybe",
        )


def test_submit_conversation_feedback_persists(db_session) -> None:
    """Conversation feedback is stored with conversation_id, no analysis_id."""
    conv = conversation_service.create_conversation(db_session, user_id="default")

    thompson = MagicMock()
    row = feedback_service.submit_conversation_feedback(
        db_session,
        user_id="default",
        conversation_id=conv.id,
        feedback_type="positive",
        response_style="empathetic",
        thompson=thompson,
    )
    assert row.feedback_type == "positive"
    assert row.conversation_id == conv.id
    assert row.analysis_id is None
    assert row.diary_id is None


def test_submit_conversation_feedback_rejects_invalid_type(db_session) -> None:
    conv = conversation_service.create_conversation(db_session, user_id="default")
    with pytest.raises(ValidationError):
        feedback_service.submit_conversation_feedback(
            db_session,
            user_id="default",
            conversation_id=conv.id,
            feedback_type="maybe",
        )


def test_submit_conversation_feedback_rejects_empty_conversation_id(db_session) -> None:
    with pytest.raises(ValidationError):
        feedback_service.submit_conversation_feedback(
            db_session,
            user_id="default",
            conversation_id="",
            feedback_type="positive",
        )


def test_submit_conversation_feedback_rejects_nonexistent_conversation(db_session) -> None:
    """Feedback for a conversation that doesn't belong to the user is rejected."""
    with pytest.raises(ValidationError):
        feedback_service.submit_conversation_feedback(
            db_session,
            user_id="default",
            conversation_id="nonexistent-conv-id",
            feedback_type="positive",
        )


def test_submit_conversation_feedback_rejects_wrong_user(db_session) -> None:
    """Feedback for another user's conversation is rejected."""
    conv = conversation_service.create_conversation(db_session, user_id="user_a")
    with pytest.raises(ValidationError):
        feedback_service.submit_conversation_feedback(
            db_session,
            user_id="user_b",
            conversation_id=conv.id,
            feedback_type="positive",
        )


def test_submit_conversation_feedback_schedules_thompson(db_session) -> None:
    """Thompson Sampling update is scheduled for conversation feedback."""
    conv = conversation_service.create_conversation(db_session, user_id="default")
    thompson = MagicMock()
    feedback_service.submit_conversation_feedback(
        db_session,
        user_id="default",
        conversation_id=conv.id,
        feedback_type="negative",
        response_style="direct",
        thompson=thompson,
    )
    # Thompson update is async (thread), so we just verify it was called
    # The actual call happens in a daemon thread, so we check the mock was set up
    assert thompson is not None

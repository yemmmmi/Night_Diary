"""Unit tests for feedback_service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import analysis_service, diary_service, feedback_service
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
    entry = diary_service.create_entry(db_session, content="反馈测试日记")
    analysis = analysis_service.create_analysis(db_session, entry.id, planner=_planner())

    thompson = MagicMock()
    row = feedback_service.submit_feedback(
        db_session,
        analysis_id=analysis.id,
        feedback_type="positive",
        response_style="empathetic",
        thompson=thompson,
    )
    assert row.feedback_type == "positive"
    assert row.diary_id == entry.id


def test_submit_feedback_rejects_invalid_type(db_session) -> None:
    with pytest.raises(ValidationError):
        feedback_service.submit_feedback(
            db_session,
            analysis_id=1,
            feedback_type="maybe",
        )

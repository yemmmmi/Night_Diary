"""Unit tests for analysis_service orchestration."""

from __future__ import annotations

import pytest

from app.services import analysis_service, diary_service
from app.services.ai.router import ExecutionPlanner
from app.shared.errors import AnalysisUnchangedError, DiaryAlreadyExistsError
from app.shared.llm_factory import StubLLMClient
from app.shared.tracing import InMemoryAgentDecisionLogger


def _planner() -> ExecutionPlanner:
    return ExecutionPlanner(
        llm_by_tier={"light": StubLLMClient(), "medium": StubLLMClient(), "default": StubLLMClient()},
        decision_logger=InMemoryAgentDecisionLogger(),
        multi_agent_enabled=False,
    )


def test_create_analysis_persists_result(db_session) -> None:
    entry = diary_service.create_entry(db_session, content="今天工作很累。")
    analysis = analysis_service.create_analysis(db_session, entry.id, planner=_planner())

    assert analysis.id is not None
    assert analysis.diary_id == entry.id
    db_session.refresh(entry)
    assert entry.ai_ans
    assert analysis.execution_tier


def test_create_analysis_rejects_duplicate(db_session) -> None:
    entry = diary_service.create_entry(db_session, content="重复分析测试")
    analysis_service.create_analysis(db_session, entry.id, planner=_planner())
    with pytest.raises(DiaryAlreadyExistsError):
        analysis_service.create_analysis(db_session, entry.id, planner=_planner())


def test_update_analysis_rejects_unchanged_content(db_session) -> None:
    entry = diary_service.create_entry(db_session, content="固定内容")
    analysis_service.create_analysis(db_session, entry.id, planner=_planner())
    with pytest.raises(AnalysisUnchangedError):
        analysis_service.update_analysis(db_session, entry.id, planner=_planner())

"""Unit tests for analysis_service orchestration."""

from __future__ import annotations

import pytest

from app.services import analysis_service, diary_service
from app.services.ai.router import ExecutionPlanner
from app.shared.errors import AnalysisNotFoundError, AnalysisUnchangedError, DiaryAlreadyExistsError
from app.shared.llm_factory import StubLLMClient
from app.shared.tracing import InMemoryAgentDecisionLogger


def _planner() -> ExecutionPlanner:
    return ExecutionPlanner(
        llm_by_tier={
            "light": StubLLMClient(),
            "medium": StubLLMClient(),
            "default": StubLLMClient(),
        },
        decision_logger=InMemoryAgentDecisionLogger(),
        multi_agent_enabled=False,
    )


class _FakeContainer:
    def __init__(self, planner: ExecutionPlanner) -> None:
        self._planner = planner

    def build_execution_planner(self, _db, *, user_id: str = "default") -> ExecutionPlanner:
        return self._planner


def test_create_analysis_persists_result(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="今天工作很累。")
    analysis, mem_count = analysis_service.create_analysis(
        db_session, entry.id, user_id="default", planner=_planner()
    )

    assert analysis.id is not None
    assert analysis.diary_id == entry.id
    db_session.refresh(entry)
    assert entry.reply
    assert analysis.execution_tier
    assert mem_count == 0  # no episodic memory in stub planner


def test_create_analysis_rejects_duplicate(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="重复分析测试")
    analysis_service.create_analysis(db_session, entry.id, user_id="default", planner=_planner())
    with pytest.raises(DiaryAlreadyExistsError):
        analysis_service.create_analysis(
            db_session, entry.id, user_id="default", planner=_planner()
        )


def test_update_analysis_rejects_unchanged_content(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="固定内容")
    analysis_service.create_analysis(db_session, entry.id, user_id="default", planner=_planner())
    with pytest.raises(AnalysisUnchangedError):
        analysis_service.update_analysis(
            db_session, entry.id, user_id="default", planner=_planner()
        )


def test_regenerate_analysis_replaces_existing(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="重新生成测试")
    first, _ = analysis_service.create_analysis(
        db_session, entry.id, user_id="default", planner=_planner()
    )
    second, _ = analysis_service.regenerate_analysis(
        db_session,
        entry.id,
        user_id="default",
        container=_FakeContainer(_planner()),
    )
    assert second.diary_id == entry.id
    db_session.refresh(entry)
    assert entry.reply
    from app.infrastructure.models.analysis import AnalysisRow

    assert db_session.query(AnalysisRow).filter_by(diary_id=entry.id).count() == 1
    assert db_session.query(type(first)).filter_by(diary_id=entry.id).count() == 1


def test_delete_analysis_for_diary_clears_reply(db_session) -> None:
    entry = diary_service.create_entry(db_session, user_id="default", content="删除分析测试")
    analysis_service.create_analysis(db_session, entry.id, user_id="default", planner=_planner())
    assert (
        analysis_service.delete_analysis_for_diary(db_session, entry.id, user_id="default") is True
    )
    db_session.refresh(entry)
    assert entry.reply is None
    with pytest.raises(AnalysisNotFoundError):
        analysis_service.get_analysis(db_session, entry.id, user_id="default")

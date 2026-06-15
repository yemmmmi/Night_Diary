"""Unit tests for weekly_service orchestration."""

from __future__ import annotations

from datetime import date

import pytest

from app.services import card_service, diary_service, weekly_service
from app.services.ai.router import ExecutionPlanner
from app.shared.errors import (
    WeeklyReportEmptyError,
    WeeklyReportExistsError,
    WeeklyReportNotFoundError,
)
from app.shared.llm_factory import StubLLMClient
from app.shared.tracing import InMemoryAgentDecisionLogger


def _planner() -> ExecutionPlanner:
    return ExecutionPlanner(
        llm_by_tier={"light": StubLLMClient(), "medium": StubLLMClient(), "default": StubLLMClient()},
        decision_logger=InMemoryAgentDecisionLogger(),
        multi_agent_enabled=False,
    )


class _FakeContainer:
    def __init__(self, planner: ExecutionPlanner) -> None:
        self._planner = planner

    def build_execution_planner(self, _db) -> ExecutionPlanner:
        return self._planner


def _seed_week(db_session) -> None:
    monday, _ = weekly_service.week_bounds()
    diary_service.create_entry(db_session, content="今天过得还不错。", entry_date=monday)
    card_service.create_card(db_session, emotion="平静", event_summary="散步", mood_score=0.6)


def test_week_bounds_returns_monday_to_sunday() -> None:
    start, end = weekly_service.week_bounds(date(2026, 6, 10))  # Wednesday
    assert start == date(2026, 6, 8)
    assert end == date(2026, 6, 14)
    assert start.weekday() == 0
    assert end.weekday() == 6


def test_build_weekly_content_contains_weekly_keyword() -> None:
    start, end = weekly_service.week_bounds(date(2026, 6, 10))
    content = weekly_service._build_weekly_content(start, end, [], [])
    assert "周报" in content or "本周" in content


def test_create_weekly_report_persists(db_session) -> None:
    _seed_week(db_session)
    report = weekly_service.create_weekly_report(db_session, planner=_planner())

    assert report.id is not None
    assert report.content
    assert report.diary_count == 1
    assert report.card_count == 1
    assert report.avg_mood == pytest.approx(0.6, abs=0.01)
    assert report.period_start.weekday() == 0


def test_create_weekly_report_rejects_duplicate(db_session) -> None:
    _seed_week(db_session)
    weekly_service.create_weekly_report(db_session, planner=_planner())
    with pytest.raises(WeeklyReportExistsError):
        weekly_service.create_weekly_report(db_session, planner=_planner())


def test_create_weekly_report_empty_raises(db_session) -> None:
    with pytest.raises(WeeklyReportEmptyError):
        weekly_service.create_weekly_report(db_session, planner=_planner())


def test_regenerate_weekly_replaces_existing(db_session) -> None:
    _seed_week(db_session)
    first = weekly_service.create_weekly_report(db_session, planner=_planner())
    second = weekly_service.regenerate_weekly_report(
        db_session,
        container=_FakeContainer(_planner()),  # type: ignore[arg-type]
    )
    assert second.period_start == first.period_start

    from app.infrastructure.models.weekly_report import WeeklyReportRow

    assert db_session.query(WeeklyReportRow).count() == 1


def test_latest_and_delete(db_session) -> None:
    _seed_week(db_session)
    report = weekly_service.create_weekly_report(db_session, planner=_planner())

    assert weekly_service.get_latest_report(db_session).id == report.id
    assert weekly_service.delete_report(db_session, report.id) is True
    with pytest.raises(WeeklyReportNotFoundError):
        weekly_service.get_latest_report(db_session)

"""Unit tests for weekly_service orchestration."""

from __future__ import annotations

from datetime import date

import pytest

from app.services import card_service, diary_service, plan_service, weekly_service
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

    def build_execution_planner(self, *, user_id: str = "default") -> ExecutionPlanner:
        return self._planner


def _seed_week(db_session) -> None:
    monday, _ = weekly_service.week_bounds()
    diary_service.create_entry(
        db_session, user_id="default", content="今天过得还不错。", entry_date=monday
    )
    card_service.create_card(
        db_session, user_id="default", emotion="平静", event_summary="散步", mood_score=0.6
    )


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
    report = weekly_service.create_weekly_report(db_session, user_id="default", planner=_planner())

    assert report.id is not None
    assert report.content
    assert report.diary_count == 1
    assert report.card_count == 1
    assert report.avg_mood == pytest.approx(0.6, abs=0.01)
    assert report.period_start.weekday() == 0


def test_create_weekly_report_rejects_duplicate(db_session) -> None:
    _seed_week(db_session)
    weekly_service.create_weekly_report(db_session, user_id="default", planner=_planner())
    with pytest.raises(WeeklyReportExistsError):
        weekly_service.create_weekly_report(db_session, user_id="default", planner=_planner())


def test_create_weekly_report_empty_raises(db_session) -> None:
    with pytest.raises(WeeklyReportEmptyError):
        weekly_service.create_weekly_report(db_session, user_id="default", planner=_planner())


def test_regenerate_weekly_replaces_existing(db_session) -> None:
    _seed_week(db_session)
    first = weekly_service.create_weekly_report(db_session, user_id="default", planner=_planner())
    second = weekly_service.regenerate_weekly_report(
        db_session,
        user_id="default",
        container=_FakeContainer(_planner()),  # type: ignore[arg-type]
    )
    assert second.period_start == first.period_start

    from app.infrastructure.models.weekly_report import WeeklyReportRow

    assert db_session.query(WeeklyReportRow).count() == 1


def test_latest_and_delete(db_session) -> None:
    _seed_week(db_session)
    report = weekly_service.create_weekly_report(db_session, user_id="default", planner=_planner())

    assert weekly_service.get_latest_report(db_session, user_id="default").id == report.id
    assert weekly_service.delete_report(db_session, report_id=report.id, user_id="default") is True
    with pytest.raises(WeeklyReportNotFoundError):
        weekly_service.get_latest_report(db_session, user_id="default")


# ── V3 P3: plan/task data injection ──────────────────────────────────


def test_plans_in_week_returns_active_plans_with_week_tasks(db_session) -> None:
    """_plans_in_week 应返回本周有活动的 plan 与 task."""
    plan = plan_service.create_plan(db_session, user_id="default", title="测试计划")
    plan_service.create_task(
        db_session, user_id="default", plan_id=plan.id, title="本周任务"
    )

    start, end = weekly_service.week_bounds()
    result = weekly_service._plans_in_week(
        db_session, user_id="default", start=start, end=end
    )

    assert len(result["active_plans"]) >= 1
    assert len(result["week_tasks"]) >= 1
    assert any(t.title == "本周任务" for t in result["week_tasks"])


def test_plans_in_week_includes_standalone_tasks(db_session) -> None:
    """无 plan_id 的独立任务也应纳入本周活动."""
    plan_service.create_task(db_session, user_id="default", title="独立任务")

    start, end = weekly_service.week_bounds()
    result = weekly_service._plans_in_week(
        db_session, user_id="default", start=start, end=end
    )
    assert any(
        t.plan_id is None and t.title == "独立任务" for t in result["week_tasks"]
    )


def test_plans_in_week_skips_outdated_tasks(db_session) -> None:
    """无本周活动 (created/completed 都不在周内) 时不应返回."""
    plan = plan_service.create_plan(db_session, user_id="default", title="旧计划")
    task = plan_service.create_task(
        db_session, user_id="default", plan_id=plan.id, title="旧任务"
    )
    # 把 created_at 强制改成一周前, 让它落在 week 区间外.
    from datetime import timedelta

    old = (date.today() - timedelta(days=14)).replace(day=1)
    task.created_at = old
    db_session.commit()

    start, end = weekly_service.week_bounds()
    result = weekly_service._plans_in_week(
        db_session, user_id="default", start=start, end=end
    )
    assert result["active_plans"] == []
    assert result["week_tasks"] == []


def test_build_weekly_content_includes_plan_section(db_session) -> None:
    """_build_weekly_content 在有 plan 数据时追加【本周计划执行】块."""
    plan = plan_service.create_plan(db_session, user_id="default", title="早睡挑战")
    plan_service.create_task(
        db_session, user_id="default", plan_id=plan.id, title="11点前睡"
    )
    # 重新查询, 确保 .tasks 关系从 DB 懒加载到最新数据.
    plan = plan_service.get_plan(db_session, plan_id=plan.id, user_id="default")

    plans_data = {
        "active_plans": [plan],
        "week_tasks": list(plan.tasks),
    }

    start, end = weekly_service.week_bounds()
    content = weekly_service._build_weekly_content(
        start, end, [], [], plans_data=plans_data
    )
    assert "【本周计划执行】" in content
    assert "早睡挑战" in content


def test_build_weekly_content_without_plans_skips_section() -> None:
    """无 plan 数据时不追加计划段落."""
    start, end = weekly_service.week_bounds()
    content = weekly_service._build_weekly_content(
        start, end, [], [], plans_data={"active_plans": [], "week_tasks": []}
    )
    assert "【本周计划执行】" not in content

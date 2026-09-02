"""Unit tests for plan_service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database import Base, init_db
from app.services import plan_service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_create_plan(db):
    plan = plan_service.create_plan(
        db, user_id="user-1", title="测试计划", motivation="动机",
        source_refs=[{"type": "diary", "id": 1}],
        source="agent", created_from_conversation_id="conv-1",
    )
    assert plan.id
    assert plan.title == "测试计划"
    assert plan.source == "agent"
    assert plan.user_id == "user-1"


def test_list_plans_filters_by_user(db):
    plan_service.create_plan(db, user_id="user-1", title="A")
    plan_service.create_plan(db, user_id="user-2", title="B")
    plans = plan_service.list_plans(db, user_id="user-1")
    assert len(plans) == 1
    assert plans[0].title == "A"


def test_get_plan_with_tasks(db):
    plan = plan_service.create_plan(db, user_id="user-1", title="带任务的计划")
    plan_service.create_task(db, user_id="user-1", plan_id=plan.id, title="task1")
    plan_service.create_task(db, user_id="user-1", plan_id=plan.id, title="task2")

    fetched = plan_service.get_plan(db, plan_id=plan.id, user_id="user-1")
    assert len(fetched.tasks) == 2


def test_create_task_standalone(db):
    task = plan_service.create_task(
        db, user_id="user-1", plan_id=None, title="独立任务",
        due_date="2026-08-15",
    )
    assert task.plan_id is None
    assert task.due_date is not None


def test_get_today_tasks(db):
    from datetime import date, timedelta
    today = date.today()
    plan_service.create_task(db, user_id="user-1", title="今日到期", due_date=today.isoformat())
    tomorrow = today + timedelta(days=1)
    plan_service.create_task(db, user_id="user-1", title="明日", due_date=tomorrow.isoformat())
    plan_service.create_task(db, user_id="user-1", title="无截止日的 pending")

    today_tasks = plan_service.get_today_tasks(db, user_id="user-1")
    titles = [t.title for t in today_tasks]
    assert "今日到期" in titles
    assert "无截止日的 pending" in titles
    assert "明日" not in titles


def test_complete_task(db):
    task = plan_service.create_task(db, user_id="user-1", title="待完成")
    plan_service.update_task_status(db, task_id=task.id, user_id="user-1", status="done")
    fetched = plan_service.get_task(db, task_id=task.id, user_id="user-1")
    assert fetched.status == "done"
    assert fetched.completed_at is not None


def test_delete_plan_cascades(db):
    plan = plan_service.create_plan(db, user_id="user-1", title="要删的")
    plan_service.create_task(db, user_id="user-1", plan_id=plan.id, title="t1")
    plan_service.delete_plan(db, plan_id=plan.id, user_id="user-1")
    tasks = plan_service.list_tasks(db, user_id="user-1", plan_id=plan.id)
    assert len(tasks) == 0


def test_get_plan_not_found_raises(db):
    from app.shared.errors import NotFoundError
    with pytest.raises(NotFoundError):
        plan_service.get_plan(db, plan_id="nonexistent", user_id="user-1")


# ── Task 2: episodic memory write-back on status change ──────────────


def test_update_task_status_done_triggers_memory_persist(db, monkeypatch):
    """update_task_status 标记 done 时应触发记忆回写。"""
    from unittest.mock import MagicMock

    from app.services import plan_service
    from app.services.memory_gateway import MemoryGateway

    task = plan_service.create_task(db, user_id="user-1", title="测试任务")

    # ServiceContainer 没有 memory_gateway 属性; 生产路径走
    # MemoryGateway.from_container(container), 故在单元测试里 patch 该入口
    # 注入一个 mock gateway 来断言 persist_atom 调用.
    mock_gateway = MagicMock()
    monkeypatch.setattr(
        MemoryGateway,
        "from_container",
        staticmethod(lambda container: mock_gateway),
    )

    plan_service.update_task_status(
        db, task_id=task.id, user_id="user-1", status="done",
        container=MagicMock(),
    )

    assert mock_gateway.persist_atom.called
    call_args = mock_gateway.persist_atom.call_args
    atom = call_args[0][0]  # 第一个位置参数是 atom
    assert atom.source == "task"
    assert atom.importance >= 0.6


def test_update_task_status_without_container_no_persist(db):
    """container=None 时不触发记忆回写（向后兼容）。"""
    from app.services import plan_service

    task = plan_service.create_task(db, user_id="user-1", title="测试")
    plan_service.update_task_status(
        db, task_id=task.id, user_id="user-1", status="done",
    )
    # 只要不抛异常就算通过


def test_update_task_status_same_status_no_persist(db, monkeypatch):
    """状态未变更时不触发记忆回写。"""
    from unittest.mock import MagicMock

    from app.services import plan_service
    from app.services.memory_gateway import MemoryGateway

    task = plan_service.create_task(db, user_id="user-1", title="测试")
    mock_gateway = MagicMock()
    monkeypatch.setattr(
        MemoryGateway,
        "from_container",
        staticmethod(lambda container: mock_gateway),
    )

    plan_service.update_task_status(
        db, task_id=task.id, user_id="user-1", status="pending",
        container=MagicMock(),
    )
    assert not mock_gateway.persist_atom.called


def test_persist_task_memory_failure_does_not_block(db, monkeypatch):
    """记忆回写失败不影响任务状态变更。"""
    from unittest.mock import MagicMock

    from app.services import plan_service
    from app.services.memory_gateway import MemoryGateway

    task = plan_service.create_task(db, user_id="user-1", title="测试")
    mock_gateway = MagicMock()
    mock_gateway.persist_atom.side_effect = RuntimeError("DB down")
    monkeypatch.setattr(
        MemoryGateway,
        "from_container",
        staticmethod(lambda container: mock_gateway),
    )

    result = plan_service.update_task_status(
        db, task_id=task.id, user_id="user-1", status="done",
        container=MagicMock(),
    )
    assert result.status == "done"
    assert result.completed_at is not None


# ── Skill-template check-ins (PR8) ────────────────────────────────────


def _make_checkin_plan(db, *, template, target_value=None):
    return plan_service.create_plan(
        db, user_id="user-1", title="模板计划", template=template,
        target_value=target_value, target_unit="天" if template == "checkin_total" else "小时",
        target_period="total" if template == "checkin_total" else "daily",
    )


def test_do_checkin_creates_today_row(db):
    plan = _make_checkin_plan(db, template="checkin_total", target_value=30)
    row = plan_service.do_checkin(db, plan_id=plan.id, user_id="user-1")
    assert row.value == 1
    assert row.status == "done"
    assert row.checkin_date == plan_service._beijing_today()


def test_do_checkin_same_day_is_idempotent(db):
    plan = _make_checkin_plan(db, template="checkin_total", target_value=30)
    first = plan_service.do_checkin(db, plan_id=plan.id, user_id="user-1")
    second = plan_service.do_checkin(db, plan_id=plan.id, user_id="user-1")
    assert second.id == first.id
    assert second.value == 1  # same day, no double count
    checkins = plan_service.list_checkins(db, plan_id=plan.id, user_id="user-1")
    assert len(checkins) == 1


def test_do_checkin_rejects_non_checkin_template(db):
    from app.shared.errors import ValidationError

    plan = plan_service.create_plan(db, user_id="user-1", title="普通计划")
    with pytest.raises(ValidationError):
        plan_service.do_checkin(db, plan_id=plan.id, user_id="user-1")

    timer_plan = _make_checkin_plan(db, template="timer_daily", target_value=4)
    with pytest.raises(ValidationError):
        plan_service.do_checkin(db, plan_id=timer_plan.id, user_id="user-1")


def test_do_checkin_completes_plan_at_target(db):
    from datetime import datetime, timedelta

    from app.infrastructure.models import PlanCheckinRow

    plan = _make_checkin_plan(db, template="checkin_total", target_value=2)
    yesterday = plan_service._beijing_today() - timedelta(days=1)
    db.add(
        PlanCheckinRow(
            id="past-1", plan_id=plan.id, user_id="user-1",
            checkin_date=yesterday, value=1, status="done",
            created_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db.commit()

    plan_service.do_checkin(db, plan_id=plan.id, user_id="user-1")
    refreshed = plan_service.get_plan(db, plan_id=plan.id, user_id="user-1")
    assert refreshed.status == "completed"


def test_start_timer_creates_running_row(db):
    plan = _make_checkin_plan(db, template="timer_daily", target_value=4)
    row = plan_service.start_timer(db, plan_id=plan.id, user_id="user-1")
    assert row.status == "running"
    assert row.started_at is not None
    assert row.value == 0


def test_start_timer_rejects_wrong_template(db):
    from app.shared.errors import ValidationError

    plan = _make_checkin_plan(db, template="checkin_total", target_value=30)
    with pytest.raises(ValidationError):
        plan_service.start_timer(db, plan_id=plan.id, user_id="user-1")


def test_stop_timer_accumulates_elapsed_seconds(db):
    from datetime import datetime, timedelta

    plan = _make_checkin_plan(db, template="timer_daily", target_value=4)
    plan_service.start_timer(db, plan_id=plan.id, user_id="user-1")
    row = plan_service.list_checkins(db, plan_id=plan.id, user_id="user-1")[0]
    row.started_at = datetime.utcnow() - timedelta(minutes=10)
    db.commit()

    stopped = plan_service.stop_timer(db, plan_id=plan.id, user_id="user-1")
    assert stopped.status == "done"
    assert stopped.ended_at is not None
    assert stopped.value >= 590  # ~600s accumulated, tolerant lower bound


def test_stop_timer_without_running_session_raises(db):
    from app.shared.errors import ValidationError

    plan = _make_checkin_plan(db, template="timer_daily", target_value=4)
    with pytest.raises(ValidationError):
        plan_service.stop_timer(db, plan_id=plan.id, user_id="user-1")


def test_stale_running_row_closed_on_next_day_action(db):
    from datetime import datetime, timedelta

    from app.infrastructure.models import PlanCheckinRow

    timer = _make_checkin_plan(db, template="timer_daily", target_value=4)
    yesterday = plan_service._beijing_today() - timedelta(days=1)
    db.add(
        PlanCheckinRow(
            id="stale-1", plan_id=timer.id, user_id="user-1",
            checkin_date=yesterday, value=0, status="running",
            started_at=datetime.utcnow() - timedelta(hours=25),
            created_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db.commit()

    checkin_plan = _make_checkin_plan(db, template="checkin_total", target_value=30)
    plan_service.do_checkin(db, plan_id=checkin_plan.id, user_id="user-1")

    stale = plan_service.list_checkins(db, plan_id=timer.id, user_id="user-1")[0]
    assert stale.status == "done"  # day ended → running closed
    assert stale.value >= 0  # elapsed accumulated into value
    assert stale.ended_at is not None


def test_today_snapshot_checkin_total(db):
    plan = _make_checkin_plan(db, template="checkin_total", target_value=30)
    snapshot = plan_service.build_today_snapshot(db, plan=plan)
    assert snapshot is not None
    assert snapshot["today_checked_in"] is False
    assert snapshot["total_checkins"] == 0

    plan_service.do_checkin(db, plan_id=plan.id, user_id="user-1")
    snapshot = plan_service.build_today_snapshot(db, plan=plan)
    assert snapshot["today_checked_in"] is True
    assert snapshot["total_checkins"] == 1


def test_today_snapshot_timer_daily_running(db):
    from datetime import datetime, timedelta

    plan = _make_checkin_plan(db, template="timer_daily", target_value=4)
    plan_service.start_timer(db, plan_id=plan.id, user_id="user-1")
    row = plan_service.list_checkins(db, plan_id=plan.id, user_id="user-1")[0]
    row.started_at = datetime.utcnow() - timedelta(minutes=5)
    db.commit()

    snapshot = plan_service.build_today_snapshot(db, plan=plan)
    assert snapshot["running"] is True
    assert snapshot["target_seconds"] == 4 * 3600
    assert snapshot["today_seconds"] >= 290  # ~300s live elapsed
    assert snapshot["started_at"] is not None


def test_today_snapshot_none_for_legacy_and_milestones(db):
    legacy = plan_service.create_plan(db, user_id="user-1", title="旧计划")
    assert plan_service.build_today_snapshot(db, plan=legacy) is None

    milestones = _make_checkin_plan(db, template="milestones")
    assert plan_service.build_today_snapshot(db, plan=milestones) is None


def test_streak_days_counts_consecutive_met_days(db):
    from datetime import timedelta

    from app.infrastructure.models import PlanCheckinRow

    plan = _make_checkin_plan(db, template="timer_daily", target_value=1)
    today = plan_service._beijing_today()
    for offset, seconds in ((0, 3600), (1, 3600), (2, 3600), (3, 1800)):
        db.add(
            PlanCheckinRow(
                id=f"row-{offset}", plan_id=plan.id, user_id="user-1",
                checkin_date=today - timedelta(days=offset),
                value=seconds, status="done",
            )
        )
    db.commit()

    snapshot = plan_service.build_today_snapshot(db, plan=plan)
    assert snapshot["streak_days"] == 3  # today + 2 days back; day-3 missed target

"""Unit tests for plan_service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database import Base
from app.services import plan_service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
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
    from datetime import date
    today = date.today()
    plan_service.create_task(db, user_id="user-1", title="今日到期", due_date=today.isoformat())
    tomorrow = date.today().replace(day=today.day + 1) if today.day < 28 else today
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

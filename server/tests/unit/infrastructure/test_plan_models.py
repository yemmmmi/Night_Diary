"""Unit tests for Plan and Task ORM models."""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.database import Base
from app.infrastructure.models.plan import PlanRow, TaskRow


@pytest.fixture
def db_session():
    """内存 SQLite 用于隔离测试。"""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_plan_row_basic_fields(db_session):
    """PlanRow 应能持久化基本字段。"""
    plan = PlanRow(
        id="plan-001",
        user_id="user-1",
        title="晚间放松例程",
        motivation="改善睡眠",
        source_refs_json='[{"type":"diary","id":1}]',
        status="active",
        source="agent",
        created_from_conversation_id="conv-1",
    )
    db_session.add(plan)
    db_session.commit()

    fetched = db_session.query(PlanRow).filter_by(id="plan-001").one()
    assert fetched.title == "晚间放松例程"
    assert fetched.source == "agent"
    assert fetched.motivation == "改善睡眠"


def test_task_row_belongs_to_plan(db_session):
    """TaskRow 通过 plan_id 归属 PlanRow。"""
    plan = PlanRow(id="plan-1", user_id="user-1", title="测试计划")
    db_session.add(plan)
    db_session.commit()

    task = TaskRow(
        id="task-1",
        plan_id="plan-1",
        user_id="user-1",
        title="睡前不看手机",
        status="pending",
    )
    db_session.add(task)
    db_session.commit()

    fetched = db_session.query(TaskRow).filter_by(id="task-1").one()
    assert fetched.plan_id == "plan-1"
    assert fetched.status == "pending"


def test_task_row_can_be_standalone(db_session):
    """TaskRow 的 plan_id 可为空（独立 task）。"""
    task = TaskRow(
        id="task-standalone",
        plan_id=None,
        user_id="user-1",
        title="买菜",
        due_date=date(2026, 8, 10),
    )
    db_session.add(task)
    db_session.commit()

    fetched = db_session.query(TaskRow).filter_by(id="task-standalone").one()
    assert fetched.plan_id is None
    assert fetched.due_date == date(2026, 8, 10)


def test_delete_plan_cascades_to_tasks(db_session):
    """删除 Plan 应级联删除其下所有 Tasks。"""
    plan = PlanRow(id="plan-cascade", user_id="user-1", title="测试")
    db_session.add(plan)
    db_session.commit()

    for i in range(3):
        db_session.add(
            TaskRow(
                id=f"task-cascade-{i}",
                plan_id="plan-cascade",
                user_id="user-1",
                title=f"task {i}",
            )
        )
    db_session.commit()

    assert db_session.query(TaskRow).filter_by(plan_id="plan-cascade").count() == 3

    db_session.delete(plan)
    db_session.commit()

    assert db_session.query(TaskRow).filter_by(plan_id="plan-cascade").count() == 0


def test_user_isolation(db_session):
    """不同 user_id 的数据应隔离。"""
    db_session.add(PlanRow(id="plan-a", user_id="user-1", title="用户1的计划"))
    db_session.add(PlanRow(id="plan-b", user_id="user-2", title="用户2的计划"))
    db_session.commit()

    user1_plans = db_session.query(PlanRow).filter_by(user_id="user-1").all()
    assert len(user1_plans) == 1
    assert user1_plans[0].id == "plan-a"

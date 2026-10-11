"""Unit tests for plan_change_service (A3: versioned snapshots + undo)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database import Base, init_db
from app.services import plan_change_service, plan_service
from app.shared.errors import NotFoundError, ValidationError


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


# ── Recording ─────────────────────────────────────────────────────────


def test_create_plan_records_change(db):
    plan = plan_service.create_plan(
        db,
        user_id="user-1",
        title="读书计划",
        conversation_id="conv-1",
        proposal_id="prop-1",
        message_id="msg-1",
    )
    changes = plan_change_service.list_changes(db, user_id="user-1")
    assert len(changes) == 1
    log = changes[0]
    assert log.entity_type == "plan"
    assert log.entity_id == plan.id
    assert log.action == "create"
    assert log.conversation_id == "conv-1"
    assert log.proposal_id == "prop-1"
    assert log.message_id == "msg-1"
    assert log.after_json is not None
    assert log.before_json is None


def test_update_task_records_before_and_after(db):
    task = plan_service.create_task(db, user_id="user-1", title="原任务")
    plan_service.update_task(db, task_id=task.id, user_id="user-1", title="新任务")

    changes = plan_change_service.list_changes(
        db, user_id="user-1", entity_type="task"
    )
    # newest first: update then create
    update_log = changes[0]
    assert update_log.action == "update"
    assert "原任务" in update_log.before_json
    assert "新任务" in update_log.after_json


# ── Undo: create → delete ─────────────────────────────────────────────


def test_undo_created_plan_deletes_it(db):
    plan = plan_service.create_plan(db, user_id="user-1", title="待撤销")
    log = plan_change_service.list_changes(db, user_id="user-1")[0]

    result = plan_change_service.undo_change(db, log_id=log.id, user_id="user-1")
    assert result["restored"] == "deleted"

    with pytest.raises(NotFoundError):
        plan_service.get_plan(db, plan_id=plan.id, user_id="user-1")


def test_undo_created_task_deletes_it(db):
    task = plan_service.create_task(db, user_id="user-1", title="待撤销任务")
    log = plan_change_service.list_changes(
        db, user_id="user-1", entity_type="task"
    )[0]

    result = plan_change_service.undo_change(db, log_id=log.id, user_id="user-1")
    assert result["restored"] == "deleted"
    with pytest.raises(NotFoundError):
        plan_service.get_task(db, task_id=task.id, user_id="user-1")


# ── Undo: update → restore before ─────────────────────────────────────


def test_undo_task_update_restores_fields(db):
    task = plan_service.create_task(db, user_id="user-1", title="原标题")
    plan_service.update_task(db, task_id=task.id, user_id="user-1", title="改后标题")
    update_log = plan_change_service.list_changes(
        db, user_id="user-1", entity_type="task"
    )[0]

    plan_change_service.undo_change(db, log_id=update_log.id, user_id="user-1")
    restored = plan_service.get_task(db, task_id=task.id, user_id="user-1")
    assert restored.title == "原标题"


def test_undo_plan_update_restores_status(db):
    plan = plan_service.create_plan(db, user_id="user-1", title="计划")
    plan_service.update_plan(db, plan_id=plan.id, user_id="user-1", status="archived")
    update_log = plan_change_service.list_changes(
        db, user_id="user-1", entity_type="plan"
    )[0]

    plan_change_service.undo_change(db, log_id=update_log.id, user_id="user-1")
    restored = plan_service.get_plan(db, plan_id=plan.id, user_id="user-1")
    assert restored.status == "active"


# ── Undo: delete → recreate ───────────────────────────────────────────


def test_undo_plan_delete_recreates_plan_with_tasks(db):
    plan = plan_service.create_plan(db, user_id="user-1", title="会被删的计划")
    plan_service.create_task(db, user_id="user-1", plan_id=plan.id, title="子任务")
    plan_service.delete_plan(db, plan_id=plan.id, user_id="user-1")

    delete_log = plan_change_service.list_changes(
        db, user_id="user-1", entity_type="plan"
    )[0]
    assert delete_log.action == "delete"

    result = plan_change_service.undo_change(db, log_id=delete_log.id, user_id="user-1")
    assert result["restored"] == "restored"

    restored = plan_service.get_plan(db, plan_id=plan.id, user_id="user-1")
    assert restored.title == "会被删的计划"
    tasks = plan_service.list_tasks(db, user_id="user-1", plan_id=plan.id)
    assert [t.title for t in tasks] == ["子任务"]


def test_undo_task_delete_recreates_task(db):
    task = plan_service.create_task(
        db, user_id="user-1", title="被删任务", due_date="2026-08-15"
    )
    plan_service.delete_task(db, task_id=task.id, user_id="user-1")
    delete_log = plan_change_service.list_changes(
        db, user_id="user-1", entity_type="task"
    )[0]

    plan_change_service.undo_change(db, log_id=delete_log.id, user_id="user-1")
    restored = plan_service.get_task(db, task_id=task.id, user_id="user-1")
    assert restored.title == "被删任务"
    assert restored.due_date.isoformat() == "2026-08-15"


# ── Idempotency / safety ──────────────────────────────────────────────


def test_undo_twice_raises(db):
    plan_service.create_plan(db, user_id="user-1", title="只撤一次")
    log = plan_change_service.list_changes(db, user_id="user-1")[0]
    plan_change_service.undo_change(db, log_id=log.id, user_id="user-1")
    with pytest.raises(ValidationError):
        plan_change_service.undo_change(db, log_id=log.id, user_id="user-1")


def test_undone_changes_hidden_by_default(db):
    plan_service.create_plan(db, user_id="user-1", title="计划")
    log = plan_change_service.list_changes(db, user_id="user-1")[0]
    plan_change_service.undo_change(db, log_id=log.id, user_id="user-1")

    assert plan_change_service.list_changes(db, user_id="user-1") == []
    visible = plan_change_service.list_changes(
        db, user_id="user-1", include_undone=True
    )
    assert len(visible) == 1 and visible[0].undone is True


# ── Conversation-level undo ───────────────────────────────────────────


def test_undo_conversation_changes_reverts_all(db):
    plan = plan_service.create_plan(
        db, user_id="user-1", title="会话计划", conversation_id="conv-9"
    )
    task = plan_service.create_task(
        db, user_id="user-1", title="会话任务", conversation_id="conv-9"
    )
    other = plan_service.create_task(
        db, user_id="user-1", title="别的任务", conversation_id="conv-other"
    )

    results = plan_change_service.undo_conversation_changes(
        db, user_id="user-1", conversation_id="conv-9"
    )
    assert len(results) == 2

    with pytest.raises(NotFoundError):
        plan_service.get_plan(db, plan_id=plan.id, user_id="user-1")
    with pytest.raises(NotFoundError):
        plan_service.get_task(db, task_id=task.id, user_id="user-1")
    # unrelated change survives
    assert plan_service.get_task(db, task_id=other.id, user_id="user-1").title == "别的任务"


# ── Tenant isolation ──────────────────────────────────────────────────


def test_list_changes_scoped_to_user(db):
    plan_service.create_plan(db, user_id="user-1", title="A")
    plan_service.create_plan(db, user_id="user-2", title="B")

    assert len(plan_change_service.list_changes(db, user_id="user-1")) == 1
    assert len(plan_change_service.list_changes(db, user_id="user-2")) == 1


def test_undo_other_users_change_raises(db):
    plan_service.create_plan(db, user_id="user-1", title="A")
    log = plan_change_service.list_changes(db, user_id="user-1")[0]

    with pytest.raises(NotFoundError):
        plan_change_service.undo_change(db, log_id=log.id, user_id="user-2")


def test_undo_conversation_scoped_to_user(db):
    plan_service.create_plan(
        db, user_id="user-1", title="A", conversation_id="shared-conv"
    )
    plan_service.create_plan(
        db, user_id="user-2", title="B", conversation_id="shared-conv"
    )

    results = plan_change_service.undo_conversation_changes(
        db, user_id="user-2", conversation_id="shared-conv"
    )
    assert len(results) == 1
    # user-1's change is untouched
    assert len(plan_change_service.list_changes(db, user_id="user-1")) == 1
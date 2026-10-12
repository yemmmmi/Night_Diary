"""Unit tests for the scheduled-task service (A4)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import create_db_engine, init_db
from app.infrastructure.scheduled_task_repository import SqliteScheduledTaskStore
from app.services import scheduled_task_service as svc
from app.shared.errors import NotFoundError, ValidationError


class _FakeContainer:
    """Minimal container exposing only what the service needs."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory


@pytest.fixture()
def task_ctx(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'tasks.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _FakeContainer(factory)


@pytest.fixture()
def no_enqueue(monkeypatch):
    """Capture enqueued jobs instead of spawning worker threads."""
    calls: list[tuple] = []

    def _fake(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return "job-id"

    monkeypatch.setattr("app.infrastructure.task_queue.enqueue_task", _fake)
    return calls


def test_create_validates_kind(task_ctx) -> None:
    with pytest.raises(ValidationError):
        svc.create_task(task_ctx, user_id="u1", kind="nope", cron_expr="0 9 * * *")


def test_create_validates_cron(task_ctx) -> None:
    with pytest.raises(ValidationError):
        svc.create_task(task_ctx, user_id="u1", kind="plan_reminder", cron_expr="not cron")


def test_create_computes_next_run(task_ctx) -> None:
    data = svc.create_task(
        task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *"
    )
    assert data["kind"] == "plan_reminder"
    assert data["enabled"] is True
    assert data["next_run_at"] is not None


def test_disabled_create_has_no_next_run(task_ctx) -> None:
    data = svc.create_task(
        task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *", enabled=False
    )
    assert data["next_run_at"] is None


def test_crud_roundtrip(task_ctx) -> None:
    created = svc.create_task(
        task_ctx, user_id="u1", kind="daily_review", cron_expr="0 22 * * *"
    )
    assert [t["id"] for t in svc.list_tasks(task_ctx, user_id="u1")] == [created["id"]]

    updated = svc.update_task(
        task_ctx, created["id"], user_id="u1", cron_expr="30 22 * * *"
    )
    assert updated["cron_expr"] == "30 22 * * *"

    svc.delete_task(task_ctx, created["id"], user_id="u1")
    assert svc.list_tasks(task_ctx, user_id="u1") == []


def test_get_is_user_scoped(task_ctx) -> None:
    created = svc.create_task(
        task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *"
    )
    with pytest.raises(NotFoundError):
        svc.get_task(task_ctx, created["id"], user_id="u2")


def test_delete_unknown_raises(task_ctx) -> None:
    with pytest.raises(NotFoundError):
        svc.delete_task(task_ctx, "missing", user_id="u1")


def test_create_blocked_inside_task_execution(task_ctx) -> None:
    token = svc._TASK_EXECUTION.set(True)
    try:
        with pytest.raises(ValidationError):
            svc.create_task(task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *")
        with pytest.raises(ValidationError):
            svc.update_task(task_ctx, "any", user_id="u1", enabled=False)
    finally:
        svc._TASK_EXECUTION.reset(token)


def test_run_due_dispatches_and_advances(task_ctx, no_enqueue) -> None:
    store = SqliteScheduledTaskStore(task_ctx.session_factory)
    row = store.create(
        user_id="u1",
        kind="plan_reminder",
        cron_expr="0 9 * * *",
        payload_json="{}",
        enabled=True,
        next_run_at=datetime.now() - timedelta(minutes=1),
    )

    dispatched = svc.run_due_tasks(task_ctx)

    assert dispatched == 1
    assert len(no_enqueue) == 1
    assert no_enqueue[0][0] == svc.EXECUTE_PATH
    assert no_enqueue[0][1] == (row.id,)
    assert store.get(row.id).next_run_at > datetime.now()


def test_run_due_skips_disabled(task_ctx, no_enqueue) -> None:
    store = SqliteScheduledTaskStore(task_ctx.session_factory)
    store.create(
        user_id="u1",
        kind="plan_reminder",
        cron_expr="0 9 * * *",
        payload_json="{}",
        enabled=False,
        next_run_at=datetime.now() - timedelta(minutes=1),
    )
    assert svc.run_due_tasks(task_ctx) == 0
    assert no_enqueue == []


def test_run_due_disables_impossible_cron(task_ctx, no_enqueue) -> None:
    store = SqliteScheduledTaskStore(task_ctx.session_factory)
    row = store.create(
        user_id="u1",
        kind="plan_reminder",
        cron_expr="0 0 30 2 *",  # Feb 30 never happens
        payload_json="{}",
        enabled=True,
        next_run_at=datetime.now() - timedelta(minutes=1),
    )

    assert svc.run_due_tasks(task_ctx) == 0
    refreshed = store.get(row.id)
    assert refreshed.enabled is False
    assert refreshed.next_run_at is None


def test_trigger_enqueues_regardless_of_enabled(task_ctx, no_enqueue) -> None:
    created = svc.create_task(
        task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *", enabled=False
    )
    svc.trigger_task(task_ctx, created["id"], user_id="u1")
    assert len(no_enqueue) == 1


def test_list_runs_requires_task(task_ctx) -> None:
    with pytest.raises(NotFoundError):
        svc.list_runs(task_ctx, "missing", user_id="u1")


def test_execute_records_receipt(task_ctx, monkeypatch) -> None:
    monkeypatch.setattr(svc, "_get_container", lambda: task_ctx)
    created = svc.create_task(
        task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *"
    )

    svc.execute_scheduled_task(created["id"])

    runs = svc.list_runs(task_ctx, created["id"], user_id="u1")
    assert runs[0]["status"] == "done"
    assert "待办" in (runs[0]["summary"] or "")
    assert svc.get_task(task_ctx, created["id"], user_id="u1")["last_status"] == "done"
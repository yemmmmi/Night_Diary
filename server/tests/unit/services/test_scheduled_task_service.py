"""Unit tests for the scheduled-task service (A4)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import create_db_engine, init_db
from app.infrastructure.scheduled_task_repository import SqliteScheduledTaskStore
from app.services import result_sink as sinks
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


# ── E3: execution mode ─────────────────────────────────────────────────


def test_default_mode_follows_kind(task_ctx) -> None:
    review = svc.create_task(
        task_ctx, user_id="u1", kind="daily_review", cron_expr="0 22 * * *"
    )
    insight = svc.create_task(
        task_ctx, user_id="u1", kind="weekly_insight", cron_expr="0 20 * * 0"
    )
    reminder = svc.create_task(
        task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *"
    )
    assert review["mode"] == "script"
    assert insight["mode"] == "agent"
    assert reminder["mode"] == "script"
    assert review["sink"] == "inbox"


def test_explicit_mode_is_respected(task_ctx) -> None:
    created = svc.create_task(
        task_ctx,
        user_id="u1",
        kind="daily_review",
        cron_expr="0 22 * * *",
        mode="agent",
    )
    assert created["mode"] == "agent"


def test_rejects_unknown_mode(task_ctx) -> None:
    with pytest.raises(ValidationError):
        svc.create_task(
            task_ctx, user_id="u1", kind="daily_review", cron_expr="0 22 * * *", mode="nope"
        )


def test_rejects_mode_not_allowed_for_kind(task_ctx) -> None:
    with pytest.raises(ValidationError):
        svc.create_task(
            task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *", mode="agent"
        )
    with pytest.raises(ValidationError):
        svc.create_task(
            task_ctx, user_id="u1", kind="weekly_insight", cron_expr="0 20 * * 0", mode="script"
        )


def test_update_can_change_mode(task_ctx) -> None:
    created = svc.create_task(
        task_ctx, user_id="u1", kind="daily_review", cron_expr="0 22 * * *"
    )
    updated = svc.update_task(task_ctx, created["id"], user_id="u1", mode="agent")
    assert updated["mode"] == "agent"
    with pytest.raises(ValidationError):
        svc.update_task(task_ctx, created["id"], user_id="u1", mode="bogus")


def test_rejects_unknown_sink(task_ctx) -> None:
    with pytest.raises(ValidationError):
        svc.create_task(
            task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *", sink="carrier-pigeon"
        )


# ── E4: result sink ────────────────────────────────────────────────────


def test_execute_delivers_to_selected_sink(task_ctx, monkeypatch) -> None:
    monkeypatch.setattr(svc, "_get_container", lambda: task_ctx)
    delivered: list[sinks.TaskResult] = []

    class _SpySink:
        name = "spy"

        def deliver(self, result: sinks.TaskResult) -> None:
            delivered.append(result)

    sinks.register_sink(_SpySink())
    created = svc.create_task(
        task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *", sink="spy"
    )

    svc.execute_scheduled_task(created["id"])

    assert len(delivered) == 1
    assert delivered[0].kind == "plan_reminder"
    assert delivered[0].status == "done"
    assert delivered[0].run_id is not None


def test_sink_failure_does_not_fail_run(task_ctx, monkeypatch) -> None:
    monkeypatch.setattr(svc, "_get_container", lambda: task_ctx)

    class _BadSink:
        name = "exploding"

        def deliver(self, result: sinks.TaskResult) -> None:
            raise RuntimeError("boom")

    sinks.register_sink(_BadSink())
    created = svc.create_task(
        task_ctx, user_id="u1", kind="plan_reminder", cron_expr="0 9 * * *", sink="exploding"
    )

    svc.execute_scheduled_task(created["id"])

    runs = svc.list_runs(task_ctx, created["id"], user_id="u1")
    assert runs[0]["status"] == "done"


# ── E3: agent-mode body ────────────────────────────────────────────────


class _StubLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> object:
        self.prompts.append(prompt)

        class _Msg:
            content = self.reply

        return _Msg()


class _StubFactory:
    def __init__(self, client: _StubLLM) -> None:
        self._client = client

    def create_for_tier(self, db, tier, *, user_id=None):
        return self._client


def test_agent_daily_review_calls_llm(task_ctx) -> None:
    client = _StubLLM("今天你写下两件事，情绪从紧绷慢慢松开。")
    container = _FakeContainer(task_ctx.session_factory)
    container.llm_factory = _StubFactory(client)

    with task_ctx.session_factory() as db:
        text = svc._agent_daily_review(
            container, db, user_id="u1", digest="【2026-10-11 当日摘要】今天有点累"
        )

    assert text == "今天你写下两件事，情绪从紧绷慢慢松开。"
    assert client.prompts and "当日摘要" in client.prompts[0]


def test_agent_daily_review_falls_back_on_error(task_ctx) -> None:
    class _BoomFactory:
        def create_for_tier(self, *args, **kwargs):
            raise RuntimeError("no provider configured")

    container = _FakeContainer(task_ctx.session_factory)
    container.llm_factory = _BoomFactory()

    with task_ctx.session_factory() as db:
        assert svc._agent_daily_review(container, db, user_id="u1", digest="x") == ""


def test_execute_agent_review_uses_reflection(task_ctx, monkeypatch) -> None:
    monkeypatch.setattr(svc, "_get_container", lambda: task_ctx)
    monkeypatch.setattr(
        "app.services.digest_service.format_day_digest",
        lambda db, *, user_id, day: "【摘要】今天有点累",
    )
    monkeypatch.setattr(svc, "_agent_daily_review", lambda *a, **k: "夜记的回信")
    created = svc.create_task(
        task_ctx, user_id="u1", kind="daily_review", cron_expr="0 22 * * *", mode="agent"
    )

    svc.execute_scheduled_task(created["id"])

    runs = svc.list_runs(task_ctx, created["id"], user_id="u1")
    assert runs[0]["summary"] == "夜记的回信"
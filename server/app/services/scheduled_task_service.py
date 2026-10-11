"""Scheduled-task service (A4) — user-orchestrable recurring tasks.

Design (Hermes lessons A4):

- **Definitions live in the DB**: a cron expression plus a task ``kind``
  (daily review / weekly insight / plan reminder) and a free-form payload.
- **Scheduler and worker are decoupled**: :func:`run_due_tasks` only *selects*
  due tasks and enqueues them on the task queue; the actual work happens in
  :func:`execute_scheduled_task`, a picklable RQ entry point.
- **Failures degrade to logs**: a bad cron expression or a failing task body
  is recorded as a failed run and never breaks the scheduler loop.
- **No re-entrancy**: :func:`create_task` / :func:`update_task` refuse to run
  while inside a task execution context (:data:`_TASK_EXECUTION`), so a task
  can never spawn further tasks ("任务创建工具必须在任务执行上下文中禁用").
"""

from __future__ import annotations

import json
import logging
import threading
from contextvars import ContextVar
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.domain.schedule.cron import next_run_after, validate_cron
from app.infrastructure.scheduled_task_repository import SqliteScheduledTaskStore
from app.shared.errors import NotFoundError, ValidationError

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

#: RQ entry point (dotted path so it works on an RQ worker and in the
#: threading fallback).
EXECUTE_PATH = "app.services.scheduled_task_service.execute_scheduled_task"

#: Supported task kinds → human label.
TASK_KINDS: dict[str, str] = {
    "daily_review": "每日回顾",
    "weekly_insight": "每周洞察",
    "plan_reminder": "计划提醒",
}

#: Per-thread/task flag set while a task body runs; blocks task creation.
_TASK_EXECUTION: ContextVar[bool] = ContextVar("scheduled_task_execution", default=False)

_container: Any = None
_container_lock = threading.Lock()


def in_task_execution() -> bool:
    """Whether the current context is executing a scheduled task."""
    return _TASK_EXECUTION.get()


def _get_container() -> ServiceContainer | None:
    """Process-wide lazy container for the RQ entry point (built once)."""
    global _container
    with _container_lock:
        if _container is None:
            from app.services.container import ServiceContainer

            try:
                _container = ServiceContainer.create_core()
            except Exception as exc:
                logger.warning("scheduled task container build failed: %s", exc)
                return None
        return _container


def _store(container: ServiceContainer) -> SqliteScheduledTaskStore:
    return SqliteScheduledTaskStore(container.session_factory)


def _task_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "cron_expr": row.cron_expr,
        "payload": json.loads(row.payload_json or "{}"),
        "enabled": bool(row.enabled),
        "next_run_at": row.next_run_at,
        "last_run_at": row.last_run_at,
        "last_status": row.last_status,
        "created_at": row.created_at,
    }


def _run_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "kind": row.kind,
        "status": row.status,
        "summary": row.summary,
        "error": row.error,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }


# ── CRUD ───────────────────────────────────────────────────────────────


def create_task(
    container: ServiceContainer,
    *,
    user_id: str,
    kind: str,
    cron_expr: str,
    payload: dict[str, Any] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    if in_task_execution():
        raise ValidationError("任务执行上下文中不允许创建定时任务")
    if kind not in TASK_KINDS:
        raise ValidationError(f"未知的定时任务类型: {kind}")
    try:
        normalized = validate_cron(cron_expr)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    next_run = next_run_after(normalized, datetime.now()) if enabled else None
    row = _store(container).create(
        user_id=user_id,
        kind=kind,
        cron_expr=normalized,
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        enabled=enabled,
        next_run_at=next_run,
    )
    return _task_dict(row)


def list_tasks(container: ServiceContainer, *, user_id: str) -> list[dict[str, Any]]:
    return [_task_dict(row) for row in _store(container).list_for_user(user_id)]


def get_task(container: ServiceContainer, task_id: str, *, user_id: str) -> dict[str, Any]:
    row = _store(container).get(task_id, user_id=user_id)
    if row is None:
        raise NotFoundError(resource="定时任务", resource_id=task_id)
    return _task_dict(row)


def update_task(
    container: ServiceContainer,
    task_id: str,
    *,
    user_id: str,
    cron_expr: str | None = None,
    payload: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    if in_task_execution():
        raise ValidationError("任务执行上下文中不允许修改定时任务")
    store = _store(container)
    existing = store.get(task_id, user_id=user_id)
    if existing is None:
        raise NotFoundError(resource="定时任务", resource_id=task_id)

    new_cron = existing.cron_expr
    if cron_expr is not None:
        try:
            new_cron = validate_cron(cron_expr)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
    new_enabled = existing.enabled if enabled is None else enabled

    recompute = cron_expr is not None or enabled is not None
    next_run: Any = None
    if recompute:
        next_run = next_run_after(new_cron, datetime.now()) if new_enabled else None

    row = store.update(
        task_id,
        user_id=user_id,
        cron_expr=new_cron if cron_expr is not None else None,
        payload_json=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
        enabled=enabled,
        next_run_at=next_run if recompute else _UNCHANGED,
    )
    assert row is not None  # existence checked above
    return _task_dict(row)


def delete_task(container: ServiceContainer, task_id: str, *, user_id: str) -> None:
    if not _store(container).delete(task_id, user_id=user_id):
        raise NotFoundError(resource="定时任务", resource_id=task_id)


def list_runs(
    container: ServiceContainer, task_id: str, *, user_id: str, limit: int = 20
) -> list[dict[str, Any]]:
    store = _store(container)
    if store.get(task_id, user_id=user_id) is None:
        raise NotFoundError(resource="定时任务", resource_id=task_id)
    return [_run_dict(row) for row in store.list_runs(task_id, user_id=user_id, limit=limit)]


# ── Dispatch ───────────────────────────────────────────────────────────


def trigger_task(container: ServiceContainer, task_id: str, *, user_id: str) -> dict[str, Any]:
    """Run a task immediately (manual trigger), regardless of ``enabled``."""
    row = _store(container).get(task_id, user_id=user_id)
    if row is None:
        raise NotFoundError(resource="定时任务", resource_id=task_id)
    from app.infrastructure.task_queue import enqueue_task

    enqueue_task(EXECUTE_PATH, row.id)
    return _task_dict(row)


def run_due_tasks(
    container: ServiceContainer,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> int:
    """Enqueue every due task and advance its ``next_run_at``.

    Only *selects and enqueues* — the actual work runs in the worker. A task
    whose cron expression can no longer produce a future run is disabled so
    it stops being selected.
    """
    store = _store(container)
    now = now or datetime.now()
    dispatched = 0
    from app.infrastructure.task_queue import enqueue_task

    for task in store.list_due(now, limit=limit):
        try:
            nxt = next_run_after(task.cron_expr, now)
        except ValueError as exc:
            logger.warning("Disabling task %s: %s", task.id, exc)
            store.update(task.id, user_id=task.user_id, enabled=False, next_run_at=None)
            continue
        store.set_next_run(task.id, nxt)
        enqueue_task(EXECUTE_PATH, task.id)
        dispatched += 1
    return dispatched


# ── Execution ──────────────────────────────────────────────────────────


def execute_scheduled_task(task_id: str) -> None:
    """RQ entry point — run one task and record its receipt.

    Takes only a primitive so it is picklable; the container is rebuilt
    lazily. Best-effort: any failure is recorded as a failed run.
    """
    container = _get_container()
    if container is None:
        return
    store = _store(container)
    task = store.get(task_id)
    if task is None:
        return

    run_id = store.record_run_started(
        task_id=task.id, user_id=task.user_id, kind=task.kind
    )
    token = _TASK_EXECUTION.set(True)
    try:
        payload = json.loads(task.payload_json or "{}")
        with container.session_factory() as db:
            summary = _run_body(db, container, task.kind, payload, task.user_id)
        store.finish_run(run_id, status="done", summary=summary)
        store.mark_last(task.id, status="done", last_run_at=datetime.now())
    except Exception as exc:
        logger.warning("Scheduled task %s failed: %s", task_id, exc, exc_info=True)
        store.finish_run(run_id, status="failed", error=str(exc))
        store.mark_last(task.id, status="failed", last_run_at=datetime.now())
    finally:
        _TASK_EXECUTION.reset(token)


def _run_body(
    db: Session,
    container: ServiceContainer,
    kind: str,
    payload: dict[str, Any],
    user_id: str,
) -> str:
    """Run the task body for ``kind`` and return a short receipt summary."""
    if kind == "daily_review":
        from app.services.digest_service import format_day_digest

        day = date.today()
        text = format_day_digest(db, user_id=user_id, day=day).strip()
        return text or f"{day.isoformat()} 还没有可回顾的记录。"

    if kind == "weekly_insight":
        from app.services import weekly_service
        from app.shared.errors import WeeklyReportExistsError

        try:
            row = weekly_service.generate_weekly_report(db, container, user_id=user_id)
        except WeeklyReportExistsError:
            return "本周的周信已经生成过了。"
        return f"已生成 {row.period_start.isoformat()} 起的一周信笺。"

    if kind == "plan_reminder":
        from app.services import plan_service

        tasks = plan_service.get_today_tasks(db, user_id=user_id)
        if not tasks:
            return "今天没有待办任务。"
        titles = "、".join((getattr(t, "title", "") or "未命名") for t in tasks[:10])
        return f"今天有 {len(tasks)} 项待办：{titles}"

    raise ValueError(f"未知的定时任务类型: {kind}")


# Sentinel for "leave next_run_at unchanged" in update_task.
_UNCHANGED: object = object()


__all__ = [
    "EXECUTE_PATH",
    "TASK_KINDS",
    "create_task",
    "delete_task",
    "execute_scheduled_task",
    "get_task",
    "in_task_execution",
    "list_runs",
    "list_tasks",
    "run_due_tasks",
    "trigger_task",
    "update_task",
]
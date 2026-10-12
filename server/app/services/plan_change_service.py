"""Versioned snapshots of plan/task changes with undo (A3).

Hermes snapshots destructive operations and can roll them back in one step; 夜记
previously applied every ``PlanModifyCard`` confirmation as a direct PATCH/DELETE
with no undo path. This module records a ``before``/``after`` JSON snapshot for
each plan/task mutation (see :class:`~app.infrastructure.models.PlanChangeLogRow`)
and replays the ``before`` snapshot to undo a change.

Undo semantics:

* ``create`` → the created entity is deleted.
* ``update`` → the ``before`` fields are written back onto the entity.
* ``delete`` → the entity is recreated from ``before`` (a plan is recreated
  together with its tasks).

Changes are append-only and best-effort: recording never breaks the primary
mutation, and an already-undone row cannot be replayed twice.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import PlanChangeLogRow, PlanRow, TaskRow
from app.shared.errors import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

#: Scalar columns captured for a plan snapshot (tasks are nested separately).
_PLAN_FIELDS = (
    "id",
    "user_id",
    "title",
    "motivation",
    "source_refs_json",
    "status",
    "source",
    "created_from_conversation_id",
    "recurrence",
    "target_value",
    "target_unit",
    "target_period",
    "template",
)

#: Scalar columns captured for a task snapshot (dates handled separately).
_TASK_FIELDS = (
    "id",
    "plan_id",
    "user_id",
    "title",
    "note",
    "link",
    "source_links_json",
    "status",
    "source",
    "created_from_conversation_id",
    "actual_value",
)


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _task_snapshot(task: TaskRow) -> dict[str, Any]:
    data: dict[str, Any] = {field: getattr(task, field) for field in _TASK_FIELDS}
    data["due_date"] = task.due_date.isoformat() if task.due_date else None
    data["completed_at"] = task.completed_at.isoformat() if task.completed_at else None
    return data


def snapshot_task(task: TaskRow) -> dict[str, Any]:
    """Serializable snapshot of a task's current state."""
    return _task_snapshot(task)


def snapshot_plan(db: Session, plan: PlanRow, *, include_tasks: bool = True) -> dict[str, Any]:
    """Serializable snapshot of a plan (optionally including its tasks)."""
    data: dict[str, Any] = {field: getattr(plan, field) for field in _PLAN_FIELDS}
    if include_tasks:
        tasks = list(db.scalars(select(TaskRow).where(TaskRow.plan_id == plan.id)))
        data["tasks"] = [_task_snapshot(task) for task in tasks]
    return data


def record_change(
    db: Session,
    *,
    user_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    proposal_id: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
) -> PlanChangeLogRow:
    """Persist a change-log row (caller-owned transaction)."""
    row = PlanChangeLogRow(
        id=_new_id(),
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_json=(
            json.dumps(before, ensure_ascii=False, default=str) if before is not None else None
        ),
        after_json=(
            json.dumps(after, ensure_ascii=False, default=str) if after is not None else None
        ),
        proposal_id=proposal_id,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def safe_record(db: Session, **kwargs: Any) -> None:
    """Best-effort :func:`record_change` — a logging failure never blocks a write."""
    try:
        record_change(db, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("plan change log write failed (non-fatal): %s", exc)


def list_changes(
    db: Session,
    *,
    user_id: str,
    conversation_id: str | None = None,
    entity_type: str | None = None,
    include_undone: bool = False,
    limit: int = 50,
) -> list[PlanChangeLogRow]:
    """Recent changes for a user, newest first."""
    stmt = select(PlanChangeLogRow).where(PlanChangeLogRow.user_id == user_id)
    if conversation_id:
        stmt = stmt.where(PlanChangeLogRow.conversation_id == conversation_id)
    if entity_type:
        stmt = stmt.where(PlanChangeLogRow.entity_type == entity_type)
    if not include_undone:
        stmt = stmt.where(PlanChangeLogRow.undone.is_(False))
    stmt = stmt.order_by(
        PlanChangeLogRow.created_at.desc(), PlanChangeLogRow.id.desc()
    ).limit(limit)
    return list(db.scalars(stmt))


def get_change(db: Session, *, log_id: str, user_id: str) -> PlanChangeLogRow:
    row = db.get(PlanChangeLogRow, log_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError(resource="plan_change", resource_id=log_id)
    return row


def undo_change(db: Session, *, log_id: str, user_id: str) -> dict[str, Any]:
    """Replay a single change's ``before`` snapshot."""
    log = get_change(db, log_id=log_id, user_id=user_id)
    if log.undone:
        raise ValidationError("该变更已撤销")
    before = json.loads(log.before_json) if log.before_json else None
    restored = (
        _replay_task(db, log, before)
        if log.entity_type == "task"
        else _replay_plan(db, log, before)
    )
    log.undone = True
    log.undone_at = _now_utc()
    db.commit()
    return {
        "id": log.id,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "action": log.action,
        "restored": restored,
    }


def undo_conversation_changes(
    db: Session, *, user_id: str, conversation_id: str, limit: int = 200
) -> list[dict[str, Any]]:
    """Undo every pending change linked to a conversation (newest first)."""
    changes = list_changes(
        db, user_id=user_id, conversation_id=conversation_id, limit=limit
    )
    results: list[dict[str, Any]] = []
    for log in changes:
        try:
            results.append(undo_change(db, log_id=log.id, user_id=user_id))
        except (NotFoundError, ValidationError) as exc:
            logger.warning("skip undo of change id=%s: %s", log.id, exc)
    return results


# ── Replay helpers ────────────────────────────────────────────────────


def _apply(row: Any, data: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in data:
            setattr(row, field, data[field])


def _restore_task(db: Session, data: dict[str, Any]) -> TaskRow | None:
    task_id = data.get("id")
    if not task_id:
        return None
    row = db.get(TaskRow, task_id)
    if row is None:
        row = TaskRow(id=task_id)
        db.add(row)
    _apply(row, data, _TASK_FIELDS)
    row.due_date = date.fromisoformat(data["due_date"]) if data.get("due_date") else None
    row.completed_at = (
        datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
    )
    return row


def _replay_plan(db: Session, log: PlanChangeLogRow, before: dict[str, Any] | None) -> str:
    if log.action == "create":
        row = db.get(PlanRow, log.entity_id)
        if row is not None and row.user_id == log.user_id:
            db.delete(row)
            db.commit()
        return "deleted"
    if before is None:
        raise ValidationError("快照缺失, 无法撤销")

    row = db.get(PlanRow, log.entity_id)
    if log.action == "delete":
        if row is None:
            row = PlanRow(id=log.entity_id)
            db.add(row)
        _apply(row, before, _PLAN_FIELDS)
        db.commit()
        for task_data in before.get("tasks", []):
            _restore_task(db, task_data)
        db.commit()
        return "restored"

    # update
    if row is None:
        raise NotFoundError(resource="plan", resource_id=log.entity_id)
    _apply(row, before, _PLAN_FIELDS)
    db.commit()
    db.refresh(row)
    return "restored"


def _replay_task(db: Session, log: PlanChangeLogRow, before: dict[str, Any] | None) -> str:
    if log.action == "create":
        row = db.get(TaskRow, log.entity_id)
        if row is not None and row.user_id == log.user_id:
            db.delete(row)
            db.commit()
        return "deleted"
    if before is None:
        raise ValidationError("快照缺失, 无法撤销")

    if log.action == "delete":
        _restore_task(db, before)
        db.commit()
        return "restored"

    row = db.get(TaskRow, log.entity_id)
    if row is None:
        raise NotFoundError(resource="task", resource_id=log.entity_id)
    _apply(row, before, _TASK_FIELDS)
    row.due_date = date.fromisoformat(before["due_date"]) if before.get("due_date") else None
    row.completed_at = (
        datetime.fromisoformat(before["completed_at"]) if before.get("completed_at") else None
    )
    db.commit()
    db.refresh(row)
    return "restored"


__all__ = [
    "get_change",
    "list_changes",
    "record_change",
    "safe_record",
    "snapshot_plan",
    "snapshot_task",
    "undo_change",
    "undo_conversation_changes",
]
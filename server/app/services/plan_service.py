"""Business logic for plans and tasks (V3 P2).

All functions enforce user_id scoping for multi-tenant isolation.
Caller (API layer) is responsible for authentication; service layer
trusts the user_id passed in.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import PlanRow, TaskRow
from app.shared.errors import NotFoundError

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex


# ── Plan operations ───────────────────────────────────────────────────


def create_plan(
    db: Session,
    *,
    user_id: str,
    title: str,
    motivation: str | None = None,
    source_refs: list[dict[str, Any]] | None = None,
    source: str = "manual",
    created_from_conversation_id: str | None = None,
) -> PlanRow:
    row = PlanRow(
        id=_new_id(),
        user_id=user_id,
        title=title,
        motivation=motivation,
        source_refs_json=json.dumps(source_refs or [], ensure_ascii=False),
        status="active",
        source=source,
        created_from_conversation_id=created_from_conversation_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("Created plan id=%s user=%s source=%s", row.id, user_id, source)
    return row


def list_plans(
    db: Session, *, user_id: str, status: str | None = None
) -> list[PlanRow]:
    stmt = select(PlanRow).where(PlanRow.user_id == user_id)
    if status:
        stmt = stmt.where(PlanRow.status == status)
    stmt = stmt.order_by(PlanRow.created_at.desc())
    return list(db.scalars(stmt))


def get_plan(db: Session, *, plan_id: str, user_id: str) -> PlanRow:
    row = db.get(PlanRow, plan_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError(resource="plan", resource_id=plan_id)
    return row


def update_plan(
    db: Session, *, plan_id: str, user_id: str, **fields: Any
) -> PlanRow:
    row = get_plan(db, plan_id=plan_id, user_id=user_id)
    for key, value in fields.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_plan(db: Session, *, plan_id: str, user_id: str) -> None:
    row = get_plan(db, plan_id=plan_id, user_id=user_id)
    db.delete(row)
    db.commit()


# ── Task operations ───────────────────────────────────────────────────


def create_task(
    db: Session,
    *,
    user_id: str,
    title: str,
    plan_id: str | None = None,
    note: str | None = None,
    due_date: str | None = None,
    source: str = "manual",
    created_from_conversation_id: str | None = None,
) -> TaskRow:
    parsed_due = date.fromisoformat(due_date) if due_date else None
    row = TaskRow(
        id=_new_id(),
        plan_id=plan_id,
        user_id=user_id,
        title=title,
        note=note,
        due_date=parsed_due,
        status="pending",
        source=source,
        created_from_conversation_id=created_from_conversation_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_tasks(
    db: Session,
    *,
    user_id: str,
    plan_id: str | None = None,
    status: str | None = None,
) -> list[TaskRow]:
    stmt = select(TaskRow).where(TaskRow.user_id == user_id)
    if plan_id:
        stmt = stmt.where(TaskRow.plan_id == plan_id)
    if status:
        stmt = stmt.where(TaskRow.status == status)
    stmt = stmt.order_by(TaskRow.created_at.desc())
    return list(db.scalars(stmt))


def get_task(db: Session, *, task_id: str, user_id: str) -> TaskRow:
    row = db.get(TaskRow, task_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError(resource="task", resource_id=task_id)
    return row


def update_task_status(
    db: Session, *, task_id: str, user_id: str, status: str
) -> TaskRow:
    row = get_task(db, task_id=task_id, user_id=user_id)
    row.status = status
    if status == "done":
        row.completed_at = datetime.utcnow()
    else:
        row.completed_at = None
    db.commit()
    db.refresh(row)
    return row


def update_task(
    db: Session, *, task_id: str, user_id: str, **fields: Any
) -> TaskRow:
    row = get_task(db, task_id=task_id, user_id=user_id)
    for key, value in fields.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_task(db: Session, *, task_id: str, user_id: str) -> None:
    row = get_task(db, task_id=task_id, user_id=user_id)
    db.delete(row)
    db.commit()


def get_today_tasks(db: Session, *, user_id: str) -> list[TaskRow]:
    """Today's actionable tasks: due today OR pending without due_date.

    Excludes done/skipped.
    """
    today = date.today()
    stmt = (
        select(TaskRow)
        .where(TaskRow.user_id == user_id)
        .where(TaskRow.status == "pending")
        .where(
            (TaskRow.due_date == today)
            | (TaskRow.due_date.is_(None))
        )
        .order_by(TaskRow.due_date.asc().nullslast(), TaskRow.created_at.asc())
    )
    return list(db.scalars(stmt))

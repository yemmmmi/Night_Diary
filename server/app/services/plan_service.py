"""Business logic for plans and tasks (V3 P2).

All functions enforce user_id scoping for multi-tenant isolation.
Caller (API layer) is responsible for authentication; service layer
trusts the user_id passed in.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import PlanCheckinRow, PlanRow, TaskRow
from app.shared.errors import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

_BEIJING_TZ = timezone(timedelta(hours=8))


def _new_id() -> str:
    return uuid.uuid4().hex


def _beijing_today() -> date:
    """Check-in day boundary follows Beijing time (product convention)."""
    return datetime.now(_BEIJING_TZ).date()


def _now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
    recurrence: str | None = None,
    target_value: float | None = None,
    target_unit: str | None = None,
    target_period: str | None = None,
    template: str | None = None,
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
        recurrence=recurrence,
        target_value=target_value,
        target_unit=target_unit,
        target_period=target_period,
        template=template,
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
    link: str | None = None,
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
        link=link,
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
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[TaskRow]:
    stmt = select(TaskRow).where(TaskRow.user_id == user_id)
    if plan_id:
        stmt = stmt.where(TaskRow.plan_id == plan_id)
    if status:
        stmt = stmt.where(TaskRow.status == status)
    if date_from is not None:
        stmt = stmt.where(TaskRow.due_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(TaskRow.due_date <= date_to)
    stmt = stmt.order_by(TaskRow.created_at.desc())
    return list(db.scalars(stmt))


def get_task(db: Session, *, task_id: str, user_id: str) -> TaskRow:
    row = db.get(TaskRow, task_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError(resource="task", resource_id=task_id)
    return row


def update_task_status(
    db: Session,
    *,
    task_id: str,
    user_id: str,
    status: str,
    container: Any | None = None,
) -> TaskRow:
    row = get_task(db, task_id=task_id, user_id=user_id)
    old_status = row.status
    row.status = status
    if status == "done":
        row.completed_at = datetime.utcnow()
    else:
        row.completed_at = None
    db.commit()
    db.refresh(row)

    if (
        container is not None
        and old_status != status
        and status in ("done", "skipped")
    ):
        _persist_task_memory(db, row, container, user_id)

    return row


def _persist_task_memory(
    db: Session, task: TaskRow, container: Any, user_id: str
) -> None:
    """将任务状态变更写入 episodic memory (best-effort, 失败不阻塞).

    ``ServiceContainer`` does not expose a ``memory_gateway`` attribute, so we
    construct one via :meth:`MemoryGateway.from_container`. The caller (API
    layer) is responsible for calling ``container.ensure_memory`` first so the
    underlying ``episodic_memory`` / ``long_term_memory`` layers are loaded;
    otherwise ``persist_atom`` silently no-ops (returns ``False``).
    """
    from app.services.memory_gateway import MemoryGateway
    from app.services.normalizer import ContentNormalizer

    try:
        plan_title = None
        if task.plan_id:
            plan = db.get(PlanRow, task.plan_id)
            plan_title = plan.title if plan else None

        atom = ContentNormalizer.from_task(
            task_title=task.title,
            task_note=task.note,
            plan_title=plan_title,
            status=task.status,
            user_id=user_id,
        )
        gateway = MemoryGateway.from_container(container)
        gateway.persist_atom(atom)
    except Exception as exc:
        logger.warning("Task memory persist failed (non-fatal): %s", exc)


def update_task(
    db: Session, *, task_id: str, user_id: str, **fields: Any
) -> TaskRow:
    row = get_task(db, task_id=task_id, user_id=user_id)
    for key, value in fields.items():
        # Coerce due_date strings to date objects so the ORM Date column
        # accepts them (mirrors create_task's parsing). SQL backends like
        # SQLite reject raw ISO strings for Date columns.
        if key == "due_date" and isinstance(value, str):
            value = date.fromisoformat(value)
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
        # MySQL 不支持 NULLS LAST；布尔表达式排序在 SQLite/MySQL 均可移植：
        # 有 due_date（今天）排前，无 due_date 排后。
        .order_by(TaskRow.due_date.is_(None), TaskRow.due_date.asc(), TaskRow.created_at.asc())
    )
    return list(db.scalars(stmt))


# ── Skill-template check-ins (PR8) ────────────────────────────────────


def _today_row(db: Session, *, plan_id: str, user_id: str, day: date) -> PlanCheckinRow | None:
    return db.scalar(
        select(PlanCheckinRow).where(
            PlanCheckinRow.plan_id == plan_id,
            PlanCheckinRow.user_id == user_id,
            PlanCheckinRow.checkin_date == day,
        )
    )


def _running_elapsed(row: PlanCheckinRow) -> float:
    if row.status != "running" or row.started_at is None:
        return 0.0
    return max(0.0, (_now_utc() - row.started_at).total_seconds())


def _close_stale_running(db: Session, *, user_id: str) -> None:
    """Close running rows from previous days — the day has ended."""
    today = _beijing_today()
    stale = list(
        db.scalars(
            select(PlanCheckinRow).where(
                PlanCheckinRow.user_id == user_id,
                PlanCheckinRow.status == "running",
                PlanCheckinRow.checkin_date < today,
            )
        )
    )
    if not stale:
        return
    now = _now_utc()
    for row in stale:
        if row.started_at:
            row.value = float(row.value or 0) + max(
                0.0, (now - row.started_at).total_seconds()
            )
        row.status = "done"
        row.ended_at = now
    db.commit()


def do_checkin(db: Session, *, plan_id: str, user_id: str) -> PlanCheckinRow:
    """checkin_total: one check-in per Beijing day, progress +1."""
    plan = get_plan(db, plan_id=plan_id, user_id=user_id)
    if plan.template != "checkin_total":
        raise ValidationError("该计划不支持每日打卡")

    _close_stale_running(db, user_id=user_id)
    today = _beijing_today()
    row = _today_row(db, plan_id=plan_id, user_id=user_id, day=today)
    if row is None:
        row = PlanCheckinRow(
            id=_new_id(),
            plan_id=plan_id,
            user_id=user_id,
            checkin_date=today,
            value=1,
            status="done",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        _maybe_complete_total_plan(db, plan=plan)
    return row


def _maybe_complete_total_plan(db: Session, *, plan: PlanRow) -> None:
    if plan.target_value is None or plan.status != "active":
        return
    total = (
        db.query(PlanCheckinRow)
        .filter(
            PlanCheckinRow.plan_id == plan.id,
            PlanCheckinRow.user_id == plan.user_id,
        )
        .count()
    )
    if total >= plan.target_value:
        plan.status = "completed"
        db.commit()
        db.refresh(plan)


def start_timer(db: Session, *, plan_id: str, user_id: str) -> PlanCheckinRow:
    """timer_daily: begin (or resume) today's timing session."""
    plan = get_plan(db, plan_id=plan_id, user_id=user_id)
    if plan.template != "timer_daily":
        raise ValidationError("该计划不支持计时")

    _close_stale_running(db, user_id=user_id)
    today = _beijing_today()
    row = _today_row(db, plan_id=plan_id, user_id=user_id, day=today)
    if row is None:
        row = PlanCheckinRow(
            id=_new_id(),
            plan_id=plan_id,
            user_id=user_id,
            checkin_date=today,
            value=0,
            status="running",
            started_at=_now_utc(),
        )
        db.add(row)
    elif row.status != "running":
        row.status = "running"
        row.started_at = _now_utc()
    db.commit()
    db.refresh(row)
    return row


def stop_timer(db: Session, *, plan_id: str, user_id: str) -> PlanCheckinRow:
    """timer_daily: manually stop today's running session (never auto)."""
    plan = get_plan(db, plan_id=plan_id, user_id=user_id)
    if plan.template != "timer_daily":
        raise ValidationError("该计划不支持计时")

    today = _beijing_today()
    row = _today_row(db, plan_id=plan_id, user_id=user_id, day=today)
    if row is None or row.status != "running":
        raise ValidationError("计时未开始")

    now = _now_utc()
    if row.started_at:
        row.value = float(row.value or 0) + max(
            0.0, (now - row.started_at).total_seconds()
        )
    row.status = "done"
    row.ended_at = now
    row.started_at = now
    db.commit()
    db.refresh(row)
    return row


def list_checkins(
    db: Session, *, plan_id: str, user_id: str, limit: int = 90
) -> list[PlanCheckinRow]:
    get_plan(db, plan_id=plan_id, user_id=user_id)  # ownership check
    stmt = (
        select(PlanCheckinRow)
        .where(PlanCheckinRow.plan_id == plan_id, PlanCheckinRow.user_id == user_id)
        .order_by(PlanCheckinRow.checkin_date.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def _streak_days(rows: list[PlanCheckinRow], *, target_seconds: float, today: date) -> int:
    """Consecutive days (ending today, if met) reaching the daily target."""
    by_date = {row.checkin_date: float(row.value or 0) for row in rows}
    streak = 0
    if by_date.get(today, 0) >= target_seconds:
        streak = 1
    day = today - timedelta(days=1)
    while by_date.get(day, 0) >= target_seconds:
        streak += 1
        day = day - timedelta(days=1)
    return streak


def build_today_snapshot(db: Session, *, plan: PlanRow) -> dict[str, Any] | None:
    """Progress snapshot for skill-template plans (None for legacy/milestones)."""
    if plan.template not in ("checkin_total", "timer_daily"):
        return None

    _close_stale_running(db, user_id=plan.user_id)
    today = _beijing_today()
    rows = list_checkins(db, plan_id=plan.id, user_id=plan.user_id)
    today_row = next((r for r in rows if r.checkin_date == today), None)

    if plan.template == "checkin_total":
        return {
            "checkin_date": today.isoformat(),
            "today_checked_in": today_row is not None,
            "total_checkins": len(rows),
        }

    target_seconds = plan.target_value * 3600 if plan.target_value else None
    today_seconds = float(today_row.value or 0) if today_row else 0.0
    running = bool(today_row and today_row.status == "running")
    if running and today_row is not None:
        today_seconds += _running_elapsed(today_row)
    streak = 0
    if target_seconds:
        streak = _streak_days(rows, target_seconds=target_seconds, today=today)
        if running and today_seconds >= target_seconds and streak == 0:
            streak = 1
    return {
        "checkin_date": today.isoformat(),
        "today_seconds": round(today_seconds),
        "running": running,
        "started_at": (
            today_row.started_at.isoformat()
            if running and today_row and today_row.started_at
            else None
        ),
        "target_seconds": target_seconds,
        "streak_days": streak,
    }

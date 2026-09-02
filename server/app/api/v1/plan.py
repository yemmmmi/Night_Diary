"""Plan and Task REST API routes (V3 P2).

All routes require authentication and enforce user_id scoping via the
service layer. Plans and tasks created here may have source="agent" when
originating from an accepted Agent proposal (created_from_conversation_id
links back to the originating conversation for audit).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy.orm import Session

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.schemas import (
    CheckinCreateRequest,
    CheckinResponse,
    PlanCreateRequest,
    PlanResponse,
    PlanUpdateRequest,
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
    TodayProgressSnapshot,
)
from app.infrastructure.models import PlanCheckinRow, PlanRow, TaskRow
from app.services import plan_service

router = APIRouter(prefix="/plans", tags=["plan"])
tasks_router = APIRouter(prefix="/tasks", tags=["task"])


def _task_to_response(row: TaskRow) -> TaskResponse:
    return TaskResponse(
        id=row.id,
        plan_id=row.plan_id,
        title=row.title,
        note=row.note,
        link=row.link,
        due_date=row.due_date.isoformat() if row.due_date else None,
        status=row.status,
        source=row.source,
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        actual_value=row.actual_value,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


def _checkin_to_response(row: PlanCheckinRow) -> CheckinResponse:
    return CheckinResponse(
        id=row.id,
        plan_id=row.plan_id,
        checkin_date=row.checkin_date.isoformat(),
        started_at=row.started_at.isoformat() if row.started_at else None,
        ended_at=row.ended_at.isoformat() if row.ended_at else None,
        value=row.value,
        status=row.status,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


def _plan_to_response(
    row: PlanRow,
    db: Session | None = None,
    tasks: list[TaskRow] | None = None,
) -> PlanResponse:
    snapshot = (
        plan_service.build_today_snapshot(db, plan=row)
        if db is not None and row.template in ("checkin_total", "timer_daily")
        else None
    )
    today_progress = TodayProgressSnapshot(**snapshot) if snapshot else None
    return PlanResponse(
        id=row.id,
        title=row.title,
        motivation=row.motivation,
        source_refs=json.loads(row.source_refs_json or "[]"),
        status=row.status,
        source=row.source,
        tasks=[_task_to_response(t) for t in (tasks if tasks is not None else row.tasks)],
        recurrence=row.recurrence,
        target_value=row.target_value,
        target_unit=row.target_unit,
        target_period=row.target_period,
        template=row.template,
        today_progress=today_progress,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


# ── Plan CRUD ─────────────────────────────────────────────────────────


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(body: PlanCreateRequest, db: DbDep, user: CurrentUserDep) -> PlanResponse:
    """Create a plan with optional embedded tasks (atomic)."""
    plan = plan_service.create_plan(
        db,
        user_id=str(user.id),
        title=body.title,
        motivation=body.motivation,
        source_refs=[r.model_dump() for r in body.source_refs],
        source=body.source,
        created_from_conversation_id=body.created_from_conversation_id,
        recurrence=body.recurrence,
        target_value=body.target_value,
        target_unit=body.target_unit,
        target_period=body.target_period,
        template=body.template,
    )
    created_tasks: list[TaskRow] = []
    for task_body in body.tasks:
        task = plan_service.create_task(
            db,
            user_id=str(user.id),
            plan_id=plan.id,
            title=task_body.title,
            note=task_body.note,
            link=task_body.link,
            due_date=task_body.due_date,
            source=task_body.source,
            created_from_conversation_id=task_body.created_from_conversation_id,
        )
        created_tasks.append(task)
    return _plan_to_response(plan, db, created_tasks)


@router.get("", response_model=list[PlanResponse])
def list_plans(
    db: DbDep,
    user: CurrentUserDep,
    plan_status: str | None = Query(default=None, alias="status"),
) -> list[PlanResponse]:
    plans = plan_service.list_plans(db, user_id=str(user.id), status=plan_status)
    return [_plan_to_response(p, db) for p in plans]


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: str, db: DbDep, user: CurrentUserDep) -> PlanResponse:
    plan = plan_service.get_plan(db, plan_id=plan_id, user_id=str(user.id))
    return _plan_to_response(plan, db)


@router.patch("/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: str, body: PlanUpdateRequest, db: DbDep, user: CurrentUserDep
) -> PlanResponse:
    plan = plan_service.update_plan(
        db, plan_id=plan_id, user_id=str(user.id), **body.model_dump(exclude_unset=True)
    )
    return _plan_to_response(plan, db)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: str, db: DbDep, user: CurrentUserDep) -> None:
    plan_service.delete_plan(db, plan_id=plan_id, user_id=str(user.id))


# ── Skill-template check-ins (PR8) ────────────────────────────────────


@router.post("/{plan_id}/checkin", response_model=CheckinResponse)
def check_in(
    plan_id: str,
    body: CheckinCreateRequest,
    db: DbDep,
    user: CurrentUserDep,
) -> CheckinResponse:
    """checkin_total: daily check-in / timer_daily: start|stop the timer."""
    if body.action == "start":
        row = plan_service.start_timer(db, plan_id=plan_id, user_id=str(user.id))
    elif body.action == "stop":
        row = plan_service.stop_timer(db, plan_id=plan_id, user_id=str(user.id))
    else:
        row = plan_service.do_checkin(db, plan_id=plan_id, user_id=str(user.id))
    return _checkin_to_response(row)


@router.get("/{plan_id}/checkins", response_model=list[CheckinResponse])
def list_checkins(
    plan_id: str,
    db: DbDep,
    user: CurrentUserDep,
    limit: int = Query(default=90, ge=1, le=365),
) -> list[CheckinResponse]:
    rows = plan_service.list_checkins(
        db, plan_id=plan_id, user_id=str(user.id), limit=limit
    )
    return [_checkin_to_response(r) for r in rows]


# ── Task routes ───────────────────────────────────────────────────────


@tasks_router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreateRequest, db: DbDep, user: CurrentUserDep) -> TaskResponse:
    task = plan_service.create_task(
        db,
        user_id=str(user.id),
        plan_id=body.plan_id,
        title=body.title,
        note=body.note,
        due_date=body.due_date,
        source=body.source,
        created_from_conversation_id=body.created_from_conversation_id,
    )
    return _task_to_response(task)


@tasks_router.get("", response_model=list[TaskResponse])
def list_tasks(
    db: DbDep,
    user: CurrentUserDep,
    plan_id: str | None = Query(default=None),
    task_status: str | None = Query(default=None, alias="status"),
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> list[TaskResponse]:
    tasks = plan_service.list_tasks(
        db,
        user_id=str(user.id),
        plan_id=plan_id,
        status=task_status,
        date_from=date_from,
        date_to=date_to,
    )
    return [_task_to_response(t) for t in tasks]


@tasks_router.get("/today", response_model=list[TaskResponse])
def get_today_tasks(db: DbDep, user: CurrentUserDep) -> list[TaskResponse]:
    """Today's actionable tasks: due today OR pending without due_date."""
    tasks = plan_service.get_today_tasks(db, user_id=str(user.id))
    return [_task_to_response(t) for t in tasks]


@tasks_router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    body: TaskUpdateRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> TaskResponse:
    fields = body.model_dump(exclude_unset=True)
    if "status" in fields:
        # Task completion must trigger episodic memory write-back (closed-loop
        # for source=task). ``ensure_memory`` lazily loads the three memory
        # layers; without it ``episodic_memory`` is None and the write no-ops.
        container.ensure_memory(user_id=str(user.id))
        task = plan_service.update_task_status(
            db,
            task_id=task_id,
            user_id=str(user.id),
            status=fields.pop("status"),
            container=container,
        )
        if fields:
            task = plan_service.update_task(
                db, task_id=task_id, user_id=str(user.id), **fields
            )
    else:
        task = plan_service.update_task(
            db, task_id=task_id, user_id=str(user.id), **fields
        )
    return _task_to_response(task)


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, db: DbDep, user: CurrentUserDep) -> None:
    plan_service.delete_task(db, task_id=task_id, user_id=str(user.id))

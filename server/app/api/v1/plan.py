"""Plan and Task REST API routes (V3 P2).

All routes require authentication and enforce user_id scoping via the
service layer. Plans and tasks created here may have source="agent" when
originating from an accepted Agent proposal (created_from_conversation_id
links back to the originating conversation for audit).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, status

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.schemas import (
    PlanCreateRequest,
    PlanResponse,
    PlanUpdateRequest,
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
)
from app.infrastructure.models import PlanRow, TaskRow
from app.services import plan_service

router = APIRouter(prefix="/plans", tags=["plan"])
tasks_router = APIRouter(prefix="/tasks", tags=["task"])


def _task_to_response(row: TaskRow) -> TaskResponse:
    return TaskResponse(
        id=row.id,
        plan_id=row.plan_id,
        title=row.title,
        note=row.note,
        due_date=row.due_date.isoformat() if row.due_date else None,
        status=row.status,
        source=row.source,
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


def _plan_to_response(row: PlanRow, tasks: list[TaskRow] | None = None) -> PlanResponse:
    return PlanResponse(
        id=row.id,
        title=row.title,
        motivation=row.motivation,
        source_refs=json.loads(row.source_refs_json or "[]"),
        status=row.status,
        source=row.source,
        tasks=[_task_to_response(t) for t in (tasks if tasks is not None else row.tasks)],
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
    )
    created_tasks: list[TaskRow] = []
    for task_body in body.tasks:
        task = plan_service.create_task(
            db,
            user_id=str(user.id),
            plan_id=plan.id,
            title=task_body.title,
            note=task_body.note,
            due_date=task_body.due_date,
            source=task_body.source,
            created_from_conversation_id=task_body.created_from_conversation_id,
        )
        created_tasks.append(task)
    return _plan_to_response(plan, created_tasks)


@router.get("", response_model=list[PlanResponse])
def list_plans(
    db: DbDep,
    user: CurrentUserDep,
    plan_status: str | None = Query(default=None, alias="status"),
) -> list[PlanResponse]:
    plans = plan_service.list_plans(db, user_id=str(user.id), status=plan_status)
    return [_plan_to_response(p) for p in plans]


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: str, db: DbDep, user: CurrentUserDep) -> PlanResponse:
    plan = plan_service.get_plan(db, plan_id=plan_id, user_id=str(user.id))
    return _plan_to_response(plan)


@router.patch("/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: str, body: PlanUpdateRequest, db: DbDep, user: CurrentUserDep
) -> PlanResponse:
    plan = plan_service.update_plan(
        db, plan_id=plan_id, user_id=str(user.id), **body.model_dump(exclude_unset=True)
    )
    return _plan_to_response(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: str, db: DbDep, user: CurrentUserDep) -> None:
    plan_service.delete_plan(db, plan_id=plan_id, user_id=str(user.id))


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
) -> list[TaskResponse]:
    tasks = plan_service.list_tasks(
        db, user_id=str(user.id), plan_id=plan_id, status=task_status
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

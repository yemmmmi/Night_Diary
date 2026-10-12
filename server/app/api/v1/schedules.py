"""Scheduled-task REST API (A4).

User-orchestrable recurring tasks: a cron expression plus a task ``kind``
(daily review / weekly insight / plan reminder). All routes require auth and
scope to the current user via the service layer. A task may also be triggered
on demand; execution receipts are readable per task.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ContainerDep, CurrentUserDep
from app.api.schemas import (
    ScheduledTaskCreateRequest,
    ScheduledTaskKindResponse,
    ScheduledTaskResponse,
    ScheduledTaskRunResponse,
    ScheduledTaskUpdateRequest,
)
from app.services import scheduled_task_service as svc

router = APIRouter(prefix="/schedules", tags=["schedule"])


def _to_response(data: dict[str, Any]) -> ScheduledTaskResponse:
    mode = data.get("mode", "script")
    return ScheduledTaskResponse(
        **data,
        kind_label=svc.TASK_KINDS.get(data["kind"], data["kind"]),
        mode_label=svc.TASK_MODES.get(mode, mode),
    )


@router.get("/kinds", response_model=list[ScheduledTaskKindResponse])
def list_kinds() -> list[ScheduledTaskKindResponse]:
    """The task kinds the UI can offer (kind → label + supported modes)."""
    return [
        ScheduledTaskKindResponse(
            kind=k,
            label=v,
            default_mode=svc.KIND_DEFAULT_MODE[k],
            allowed_modes=sorted(svc.KIND_ALLOWED_MODES[k]),
        )
        for k, v in svc.TASK_KINDS.items()
    ]


@router.get("", response_model=list[ScheduledTaskResponse])
def list_schedules(
    container: ContainerDep, user: CurrentUserDep
) -> list[ScheduledTaskResponse]:
    return [_to_response(t) for t in svc.list_tasks(container, user_id=str(user.id))]


@router.post("", response_model=ScheduledTaskResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: ScheduledTaskCreateRequest, container: ContainerDep, user: CurrentUserDep
) -> ScheduledTaskResponse:
    data = svc.create_task(
        container,
        user_id=str(user.id),
        kind=body.kind,
        cron_expr=body.cron_expr,
        payload=body.payload,
        enabled=body.enabled,
        mode=body.mode,
        sink=body.sink,
    )
    return _to_response(data)


@router.get("/{task_id}", response_model=ScheduledTaskResponse)
def get_schedule(
    task_id: str, container: ContainerDep, user: CurrentUserDep
) -> ScheduledTaskResponse:
    return _to_response(svc.get_task(container, task_id, user_id=str(user.id)))


@router.patch("/{task_id}", response_model=ScheduledTaskResponse)
def update_schedule(
    task_id: str,
    body: ScheduledTaskUpdateRequest,
    container: ContainerDep,
    user: CurrentUserDep,
) -> ScheduledTaskResponse:
    data = svc.update_task(
        container,
        task_id,
        user_id=str(user.id),
        cron_expr=body.cron_expr,
        payload=body.payload,
        enabled=body.enabled,
        mode=body.mode,
        sink=body.sink,
    )
    return _to_response(data)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_schedule(
    task_id: str, container: ContainerDep, user: CurrentUserDep
) -> Response:
    svc.delete_task(container, task_id, user_id=str(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/trigger", response_model=ScheduledTaskResponse)
def trigger_schedule(
    task_id: str, container: ContainerDep, user: CurrentUserDep
) -> ScheduledTaskResponse:
    """Run a task immediately, regardless of its enabled flag."""
    return _to_response(svc.trigger_task(container, task_id, user_id=str(user.id)))


@router.get("/{task_id}/runs", response_model=list[ScheduledTaskRunResponse])
def list_runs(
    task_id: str,
    container: ContainerDep,
    user: CurrentUserDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ScheduledTaskRunResponse]:
    runs = svc.list_runs(container, task_id, user_id=str(user.id), limit=limit)
    return [ScheduledTaskRunResponse(**run) for run in runs]
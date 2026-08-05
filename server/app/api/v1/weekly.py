"""周报（"周记"）API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.mappers import weekly_to_response
from app.api.schemas import WeeklyReportResponse
from app.services import weekly_service
from app.shared.errors import WeeklyReportNotFoundError

router = APIRouter(prefix="/weekly", tags=["weekly"])


@router.post("", response_model=WeeklyReportResponse, status_code=status.HTTP_201_CREATED)
def generate_weekly(
    db: DbDep, user: CurrentUserDep, container: ContainerDep
) -> WeeklyReportResponse:
    row = weekly_service.generate_weekly_report(db, container, user_id=str(user.id))
    return weekly_to_response(row)


@router.post("/regenerate", response_model=WeeklyReportResponse)
def regenerate_weekly(
    db: DbDep, user: CurrentUserDep, container: ContainerDep
) -> WeeklyReportResponse:
    row = weekly_service.regenerate_weekly_report(db, container, user_id=str(user.id))
    return weekly_to_response(row)


@router.get("", response_model=list[WeeklyReportResponse])
def list_weekly(
    db: DbDep,
    user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> list[WeeklyReportResponse]:
    rows = weekly_service.list_reports(db, user_id=str(user.id), skip=skip, limit=limit)
    return [weekly_to_response(row) for row in rows]


@router.get("/latest", response_model=WeeklyReportResponse)
def latest_weekly(db: DbDep, user: CurrentUserDep) -> WeeklyReportResponse:
    row = weekly_service.get_latest_report(db, user_id=str(user.id))
    return weekly_to_response(row)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_weekly(report_id: int, db: DbDep, user: CurrentUserDep) -> Response:
    if not weekly_service.delete_report(db, user_id=str(user.id), report_id=report_id):
        raise WeeklyReportNotFoundError(report_id=report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Diary API routes."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.mappers import diary_to_response
from app.api.schemas import DiaryCreateRequest, DiaryResponse, DiaryUpdateRequest
from app.services import diary_service

router = APIRouter(prefix="/diary", tags=["diary"])


@router.get("/entries", response_model=list[DiaryResponse])
def list_entries(
    db: DbDep,
    user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
) -> list[DiaryResponse]:
    rows = diary_service.list_entries(
        db,
        user_id=str(user.id),
        skip=skip,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
    )
    return [diary_to_response(row) for row in rows]


@router.post("/entries", response_model=DiaryResponse, status_code=status.HTTP_201_CREATED)
def create_entry(
    body: DiaryCreateRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> DiaryResponse:
    row = diary_service.create_entry(
        db,
        user_id=str(user.id),
        content=body.content,
        entry_date=body.date,
        weather=body.weather,
        collection_manager=container.diary_collection,
    )
    return diary_to_response(row)


@router.get("/entries/{diary_id}", response_model=DiaryResponse)
def get_entry(diary_id: int, db: DbDep, user: CurrentUserDep) -> DiaryResponse:
    row = diary_service.get_entry(db, diary_id, user_id=str(user.id))
    return diary_to_response(row)


@router.put("/entries/{diary_id}", response_model=DiaryResponse)
def update_entry(
    diary_id: int,
    body: DiaryUpdateRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> DiaryResponse:
    row = diary_service.update_entry(
        db,
        diary_id,
        user_id=str(user.id),
        content=body.content,
        weather=body.weather,
        collection_manager=container.diary_collection,
    )
    return diary_to_response(row)


@router.delete(
    "/entries/{diary_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_entry(
    diary_id: int,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> Response:
    diary_service.delete_entry(
        db,
        diary_id,
        user_id=str(user.id),
        collection_manager=container.diary_collection,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

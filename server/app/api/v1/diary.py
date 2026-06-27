"""Diary API routes."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ContainerDep, DbDep
from app.api.mappers import diary_to_response
from app.api.schemas import DiaryCreateRequest, DiaryResponse, DiaryUpdateRequest
from app.services import diary_service

router = APIRouter(prefix="/diary", tags=["diary"])


@router.get("/entries", response_model=list[DiaryResponse])
def list_entries(
    db: DbDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> list[DiaryResponse]:
    rows = diary_service.list_entries(db, skip=skip, limit=limit)
    return [diary_to_response(row) for row in rows]


@router.post("/entries", response_model=DiaryResponse, status_code=status.HTTP_201_CREATED)
def create_entry(
    body: DiaryCreateRequest,
    db: DbDep,
    container: ContainerDep,
) -> DiaryResponse:
    row = diary_service.create_entry(
        db,
        content=body.content,
        entry_date=body.date,
        weather=body.weather,
        collection_manager=container.diary_collection,
    )
    return diary_to_response(row)


@router.get("/entries/{diary_id}", response_model=DiaryResponse)
def get_entry(diary_id: int, db: DbDep) -> DiaryResponse:
    row = diary_service.get_entry(db, diary_id)
    return diary_to_response(row)


@router.put("/entries/{diary_id}", response_model=DiaryResponse)
def update_entry(
    diary_id: int,
    body: DiaryUpdateRequest,
    db: DbDep,
    container: ContainerDep,
) -> DiaryResponse:
    row = diary_service.update_entry(
        db,
        diary_id,
        content=body.content,
        weather=body.weather,
        collection_manager=container.diary_collection,
    )
    return diary_to_response(row)


@router.delete("/entries/{diary_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_entry(diary_id: int, db: DbDep, container: ContainerDep) -> Response:
    diary_service.delete_entry(db, diary_id, collection_manager=container.diary_collection)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

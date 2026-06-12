"""Tag API routes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import DbDep
from app.api.mappers import tag_to_response
from app.api.schemas import TagCreateRequest, TagResponse
from app.services import tag_service

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagResponse])
def list_tags(db: DbDep) -> list[TagResponse]:
    rows = tag_service.list_tags(db)
    return [tag_to_response(row) for row in rows]


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(body: TagCreateRequest, db: DbDep) -> TagResponse:
    row = tag_service.create_tag(db, name=body.name, color=body.color)
    return tag_to_response(row)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_tag(tag_id: int, db: DbDep) -> Response:
    tag_service.delete_tag(db, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/seed-mood", response_model=list[TagResponse])
def seed_mood_tags(db: DbDep) -> list[TagResponse]:
    rows = tag_service.seed_mood_tags(db)
    return [tag_to_response(row) for row in rows]

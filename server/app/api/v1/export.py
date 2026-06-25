"""Export/Import API routes for full user data migration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ContainerDep, DbDep
from app.services import export_service

router = APIRouter(tags=["export"])


@router.get("/export/all")
def export_all(db: DbDep) -> dict[str, Any]:
    """Export all user data as a JSON dict.

    Returns diary entries (with tags + analyses), memory cards,
    episodic memories, and long-term profile.
    """
    return export_service.export_all(db)


class ImportRequest(BaseModel):
    """Request body for JSON import. Accepts the same format as export_all output."""

    data: dict[str, Any]


@router.post("/import/json")
def import_json(body: ImportRequest, db: DbDep, container: ContainerDep) -> dict[str, Any]:
    """Import user data from JSON, replacing all existing data.

    Clears existing diaries, tags, analyses, memory cards, and memories,
    then rebuilds from the provided JSON. ChromaDB vector index is
    rebuilt for each imported diary entry.
    """
    summary = export_service.import_all(
        db,
        body.data,
        collection_manager=container.diary_collection,
    )
    return {"status": "ok", "imported": summary}

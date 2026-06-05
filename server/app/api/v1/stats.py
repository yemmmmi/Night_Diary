"""Statistics API routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbDep
from app.api.schemas import StatsResponse
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
def get_stats(db: DbDep) -> StatsResponse:
    return StatsResponse(**stats_service.get_stats(db))

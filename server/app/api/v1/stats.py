"""统计 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep
from app.api.schemas import StatsResponse
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
def get_stats(db: DbDep, user: CurrentUserDep) -> StatsResponse:
    return StatsResponse(**stats_service.get_stats(db, user_id=str(user.id)))

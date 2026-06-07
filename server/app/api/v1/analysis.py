"""Analysis API routes."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ContainerDep, DbDep
from app.api.mappers import analysis_to_response
from app.api.schemas import AnalysisResponse
from app.services import analysis_service, diary_service

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/{diary_id}", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def trigger_analysis(diary_id: int, db: DbDep, container: ContainerDep) -> AnalysisResponse:
    row = analysis_service.trigger_analysis(db, diary_id, container)
    entry = diary_service.get_entry(db, diary_id)
    return analysis_to_response(row, ai_ans=entry.ai_ans)


@router.get("/{diary_id}", response_model=AnalysisResponse)
def get_analysis(diary_id: int, db: DbDep) -> AnalysisResponse:
    row = analysis_service.get_analysis(db, diary_id)
    entry = diary_service.get_entry(db, diary_id)
    return analysis_to_response(row, ai_ans=entry.ai_ans)

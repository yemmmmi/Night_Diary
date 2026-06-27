"""Analysis API routes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import ContainerDep, DbDep
from app.api.mappers import analysis_to_response
from app.api.schemas import AnalysisResponse, AnalysisTriggerRequest
from app.domain.agents.prompts import build_style_fragment
from app.services import analysis_service, diary_service
from app.shared.errors import AnalysisNotFoundError

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/{diary_id}", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def trigger_analysis(
    diary_id: int,
    db: DbDep,
    container: ContainerDep,
    request: AnalysisTriggerRequest | None = None,
) -> AnalysisResponse:
    req = request or AnalysisTriggerRequest()
    style_fragment = build_style_fragment(req.replier_preset, req.replier_persona)
    row, mem_count = analysis_service.trigger_analysis(
        db, diary_id, container, style_fragment=style_fragment
    )
    entry = diary_service.get_entry(db, diary_id)
    return analysis_to_response(row, ai_ans=entry.ai_ans, db=db, referenced_memory_count=mem_count)


@router.post("/{diary_id}/regenerate", response_model=AnalysisResponse)
def regenerate_analysis(
    diary_id: int,
    db: DbDep,
    container: ContainerDep,
    request: AnalysisTriggerRequest | None = None,
) -> AnalysisResponse:
    req = request or AnalysisTriggerRequest()
    style_fragment = build_style_fragment(req.replier_preset, req.replier_persona)
    row, mem_count = analysis_service.regenerate_analysis(
        db, diary_id, container, style_fragment=style_fragment
    )
    entry = diary_service.get_entry(db, diary_id)
    return analysis_to_response(row, ai_ans=entry.ai_ans, db=db, referenced_memory_count=mem_count)


@router.get("/{diary_id}", response_model=AnalysisResponse)
def get_analysis(diary_id: int, db: DbDep) -> AnalysisResponse:
    row = analysis_service.get_analysis(db, diary_id)
    entry = diary_service.get_entry(db, diary_id)
    return analysis_to_response(row, ai_ans=entry.ai_ans, db=db)


@router.delete("/{diary_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_analysis(diary_id: int, db: DbDep) -> Response:
    if not analysis_service.delete_analysis_for_diary(db, diary_id):
        raise AnalysisNotFoundError(diary_id=diary_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

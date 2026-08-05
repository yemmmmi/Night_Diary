"""分析 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
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
    user: CurrentUserDep,
    http_request: Request,
    request: AnalysisTriggerRequest | None = None,
) -> AnalysisResponse:
    req = request or AnalysisTriggerRequest()
    style_fragment = build_style_fragment(req.replier_preset, req.replier_persona)
    trace_id = http_request.headers.get("X-Trace-Id")
    row, mem_count = analysis_service.trigger_analysis(
        db,
        diary_id,
        container,
        user_id=str(user.id),
        style_fragment=style_fragment,
        trace_id=trace_id,
    )
    entry = diary_service.get_entry(db, diary_id, user_id=str(user.id))
    return analysis_to_response(
        row,
        reply=entry.reply,
        db=db,
        referenced_memory_count=mem_count,
        user_id=str(user.id),
    )


@router.post("/{diary_id}/regenerate", response_model=AnalysisResponse)
def regenerate_analysis(
    diary_id: int,
    db: DbDep,
    container: ContainerDep,
    user: CurrentUserDep,
    request: AnalysisTriggerRequest | None = None,
) -> AnalysisResponse:
    req = request or AnalysisTriggerRequest()
    style_fragment = build_style_fragment(req.replier_preset, req.replier_persona)
    row, mem_count = analysis_service.regenerate_analysis(
        db, diary_id, container, user_id=str(user.id), style_fragment=style_fragment
    )
    entry = diary_service.get_entry(db, diary_id, user_id=str(user.id))
    return analysis_to_response(
        row,
        reply=entry.reply,
        db=db,
        referenced_memory_count=mem_count,
        user_id=str(user.id),
    )


@router.get("/{diary_id}", response_model=AnalysisResponse)
def get_analysis(diary_id: int, db: DbDep, user: CurrentUserDep) -> AnalysisResponse:
    row = analysis_service.get_analysis(db, diary_id, user_id=str(user.id))
    entry = diary_service.get_entry(db, diary_id, user_id=str(user.id))
    return analysis_to_response(
        row,
        reply=entry.reply,
        db=db,
        user_id=str(user.id),
    )


@router.delete("/{diary_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_analysis(diary_id: int, db: DbDep, user: CurrentUserDep) -> Response:
    if not analysis_service.delete_analysis_for_diary(db, diary_id, user_id=str(user.id)):
        raise AnalysisNotFoundError(diary_id=diary_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Feedback API routes."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ContainerDep, DbDep
from app.api.mappers import feedback_to_response
from app.api.schemas import FeedbackCreateRequest, FeedbackResponse
from app.services import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/{analysis_id}", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    analysis_id: int,
    body: FeedbackCreateRequest,
    db: DbDep,
    container: ContainerDep,
) -> FeedbackResponse:
    thompson = feedback_service.build_thompson_sampler(container.style_preference_store)
    row = feedback_service.submit_feedback(
        db,
        analysis_id=analysis_id,
        feedback_type=body.feedback_type,
        reason=body.reason,
        response_style=body.response_style,
        thompson=thompson,
    )
    return feedback_to_response(row)

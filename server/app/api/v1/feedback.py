"""Feedback API routes."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.mappers import feedback_to_response
from app.api.schemas import (
    ConversationFeedbackCreateRequest,
    FeedbackCreateRequest,
    FeedbackResponse,
)
from app.services import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/{analysis_id}", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    analysis_id: int,
    body: FeedbackCreateRequest,
    db: DbDep,
    container: ContainerDep,
    user: CurrentUserDep,
) -> FeedbackResponse:
    row = feedback_service.submit_feedback(
        db,
        user_id=str(user.id),
        analysis_id=analysis_id,
        feedback_type=body.feedback_type,
        reason=body.reason,
        response_style=body.response_style,
    )
    return feedback_to_response(row)


@router.post(
    "/conversation/{conversation_id}",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_conversation_feedback(
    conversation_id: str,
    body: ConversationFeedbackCreateRequest,
    db: DbDep,
    container: ContainerDep,
    user: CurrentUserDep,
) -> FeedbackResponse:
    """Submit feedback for a conversation reply (scene 2)."""
    row = feedback_service.submit_conversation_feedback(
        db,
        user_id=str(user.id),
        conversation_id=conversation_id,
        feedback_type=body.feedback_type,
        reason=body.reason,
        response_style=body.response_style,
    )
    return feedback_to_response(row)

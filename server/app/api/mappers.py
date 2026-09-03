from __future__ import annotations

import json
from typing import Any

from app.api.schemas import (
    ConversationResponse,
    DiaryResponse,
    FeedbackResponse,
    MessageResponse,
    ModelResponse,
    TagResponse,
    WeeklyReportResponse,
)
from app.infrastructure.models.conversation import ChatMessageRow, ConversationRow
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.feedback_record import FeedbackRow
from app.infrastructure.models.model_provider import ModelProviderRow
from app.infrastructure.models.tag import TagRow
from app.infrastructure.models.weekly_report import WeeklyReportRow
from app.services import model_service


def diary_to_response(row: DiaryEntryRow) -> DiaryResponse:
    return DiaryResponse(
        id=row.id,
        content=row.content,
        date=row.date,
        weather=row.weather,
        reply=row.reply,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def tag_to_response(row: TagRow) -> TagResponse:
    return TagResponse.model_validate(row)


def feedback_to_response(row: FeedbackRow) -> FeedbackResponse:
    return FeedbackResponse.model_validate(row)


def model_to_response(row: ModelProviderRow) -> ModelResponse:
    return ModelResponse(**model_service.model_to_public_dict(row))


def card_to_response(row: Any) -> dict[str, Any]:
    """Convert MemoryCardRow to dict (for CardResponse.model_validate)."""
    from app.services.card_service import row_to_dict

    return row_to_dict(row)


def weekly_to_response(row: WeeklyReportRow) -> WeeklyReportResponse:
    return WeeklyReportResponse(
        id=row.id,
        period_start=row.period_start,
        period_end=row.period_end,
        content=row.content,
        diary_count=row.diary_count,
        card_count=row.card_count,
        avg_mood=row.avg_mood,
        token_cost=row.token_cost,
        execution_tier=row.execution_tier,
        created_at=row.created_at,
        plan_executions=json.loads(row.plan_executions_json or "[]"),
        week_tasks=json.loads(row.week_tasks_json or "[]"),
    )


def conversation_to_response(row: ConversationRow) -> ConversationResponse:
    return ConversationResponse.model_validate(row)


def message_to_response(row: ChatMessageRow) -> MessageResponse:
    diary_ids: list[int] | None = None
    memory_ids: list[str] | None = None
    card_ids: list[str] | None = None
    plan_ids: list[str] | None = None
    skill_result: dict[str, Any] | None = None
    if row.retrieved_diary_ids:
        try:
            diary_ids = json.loads(row.retrieved_diary_ids)
        except (json.JSONDecodeError, TypeError):
            diary_ids = None
    if row.retrieved_memory_ids:
        try:
            memory_ids = json.loads(row.retrieved_memory_ids)
        except (json.JSONDecodeError, TypeError):
            memory_ids = None
    if row.attached_card_ids:
        try:
            card_ids = json.loads(row.attached_card_ids)
        except (json.JSONDecodeError, TypeError):
            card_ids = None
    if row.attached_plan_ids:
        try:
            plan_ids = json.loads(row.attached_plan_ids)
        except (json.JSONDecodeError, TypeError):
            plan_ids = None
    if row.skill_result:
        try:
            parsed = json.loads(row.skill_result)
            if isinstance(parsed, dict):
                skill_result = parsed
        except (json.JSONDecodeError, TypeError):
            skill_result = None
    return MessageResponse(
        id=row.id,
        conversation_id=row.conversation_id,
        role=row.role,
        content=row.content,
        retrieved_diary_ids=diary_ids,
        retrieved_memory_ids=memory_ids,
        attached_card_ids=card_ids,
        attached_plan_ids=plan_ids,
        skill_result=skill_result,
        created_at=row.created_at,
    )

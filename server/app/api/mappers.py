from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.api.schemas import (
    AnalysisResponse,
    DiaryResponse,
    FeedbackResponse,
    ModelResponse,
    TagBrief,
    TagResponse,
    WeeklyReportResponse,
)
from app.infrastructure.models.analysis import AnalysisRow
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
        ai_ans=row.ai_ans,
        created_at=row.created_at,
        updated_at=row.updated_at,
        tags=[TagBrief.model_validate(tag) for tag in row.tags],
    )


def analysis_to_response(
    row: AnalysisRow,
    *,
    ai_ans: str | None = None,
    db: Session | None = None,
) -> AnalysisResponse:
    model_name: str | None = None
    if db is not None and row.execution_tier:
        provider = model_service.get_active_provider_for_tier(db, row.execution_tier)
        if provider is None and row.execution_tier != "default":
            provider = model_service.get_active_provider_for_tier(db, "default")
        if provider is not None:
            model_name = provider.model_name

    status_detail: str | None = None
    if row.agent_mode == "fallback" and row.log:
        status_detail = row.log.removeprefix("[Fallback] ").removeprefix("[降级] ").strip()

    return AnalysisResponse(
        id=row.id,
        diary_id=row.diary_id,
        created_at=row.created_at,
        token_cost=row.token_cost,
        cache_hit_tokens=row.cache_hit_tokens,
        cache_miss_tokens=row.cache_miss_tokens,
        output_tokens=row.output_tokens,
        agent_mode=row.agent_mode,
        execution_tier=row.execution_tier,
        activated_agents=row.activated_agents,
        ai_ans=ai_ans,
        model_name=model_name,
        status_detail=status_detail,
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
    return WeeklyReportResponse.model_validate(row)

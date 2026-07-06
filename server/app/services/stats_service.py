"""Aggregate statistics for the stats API endpoint."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.infrastructure.models.analysis import AnalysisRow
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.llm_call_log import LlmCallLogRow


def get_stats(db: Session, *, user_id: str) -> dict[str, int]:
    diary_count = db.query(DiaryEntryRow).filter(DiaryEntryRow.user_id == user_id).count()
    # AnalysisRow has no user_id column — join through DiaryEntryRow to scope.
    analysis_count = (
        db.query(AnalysisRow)
        .join(DiaryEntryRow, AnalysisRow.diary_id == DiaryEntryRow.id)
        .filter(DiaryEntryRow.user_id == user_id)
        .count()
    )
    total_token_cost = int(
        db.query(func.coalesce(func.sum(AnalysisRow.token_cost), 0))
        .join(DiaryEntryRow, AnalysisRow.diary_id == DiaryEntryRow.id)
        .filter(DiaryEntryRow.user_id == user_id)
        .scalar()
        or 0
    )
    llm_call_count = db.query(LlmCallLogRow).filter(LlmCallLogRow.user_id == user_id).count()
    total_tokens_in = int(
        db.query(func.coalesce(func.sum(LlmCallLogRow.tokens_in), 0))
        .filter(LlmCallLogRow.user_id == user_id)
        .scalar()
        or 0
    )
    total_tokens_out = int(
        db.query(func.coalesce(func.sum(LlmCallLogRow.tokens_out), 0))
        .filter(LlmCallLogRow.user_id == user_id)
        .scalar()
        or 0
    )
    return {
        "diary_count": diary_count,
        "analysis_count": analysis_count,
        "total_token_cost": total_token_cost,
        "llm_call_count": llm_call_count,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
    }

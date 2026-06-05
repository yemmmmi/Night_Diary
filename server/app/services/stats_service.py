"""Aggregate statistics for the stats API endpoint."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.infrastructure.models.analysis import AnalysisRow
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.llm_call_log import LlmCallLogRow


def get_stats(db: Session) -> dict[str, int]:
    diary_count = db.query(DiaryEntryRow).count()
    analysis_count = db.query(AnalysisRow).count()
    total_token_cost = int(
        db.query(func.coalesce(func.sum(AnalysisRow.token_cost), 0)).scalar() or 0
    )
    llm_call_count = db.query(LlmCallLogRow).count()
    total_tokens_in = int(
        db.query(func.coalesce(func.sum(LlmCallLogRow.tokens_in), 0)).scalar() or 0
    )
    total_tokens_out = int(
        db.query(func.coalesce(func.sum(LlmCallLogRow.tokens_out), 0)).scalar() or 0
    )
    return {
        "diary_count": diary_count,
        "analysis_count": analysis_count,
        "total_token_cost": total_token_cost,
        "llm_call_count": llm_call_count,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
    }

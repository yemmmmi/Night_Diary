"""Analysis orchestration — diary lookup → AI router → persist result."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.domain.memory.types import EpisodicEntry
from app.infrastructure.models.analysis import AnalysisRow
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.services import diary_service
from app.services.ai.router import ExecutionPlanner
from app.shared.emotion_estimator import EmotionEstimator

if TYPE_CHECKING:
    from app.services.container import ServiceContainer
from app.shared.errors import (
    AnalysisNotFoundError,
    AnalysisUnchangedError,
    DiaryAlreadyExistsError,
    DiaryNotFoundError,
)

logger = logging.getLogger(__name__)

# Module-level estimator — lightweight, stateless, safe to share.
_emotion_estimator = EmotionEstimator()

# Importance threshold for diary-derived episodic entries.  Diary entries are
# the primary content of the product, so they default above the 0.5 store
# threshold to ensure they are actually persisted (not filtered out).
_DIARY_EPISODIC_IMPORTANCE = 0.6


def _build_context(entry: DiaryEntryRow, recent_entries: list[DiaryEntryRow]) -> dict[str, str]:
    return {
        "current_content": entry.content or "",
        "tags_context": diary_service.format_tags_context(entry.tags),
        "history_summary": diary_service.format_history_summary(
            recent_entries,
            exclude_id=entry.id,
        ),
        "weather_info": entry.weather or "未获取天气信息",
    }


def _persist_analysis(
    db: Session,
    *,
    entry: DiaryEntryRow,
    result: Any,
) -> AnalysisRow:
    analysis = AnalysisRow(
        diary_id=entry.id,
        created_at=datetime.utcnow(),
        token_cost=result.token_cost,
        cache_hit_tokens=result.cache_hit_tokens,
        cache_miss_tokens=result.cache_miss_tokens,
        output_tokens=result.output_tokens,
        log=result.thk_log,
        diary_length=len(entry.content or ""),
        agent_mode=result.agent_mode,
        execution_tier=result.execution_tier,
        activated_agents=result.activated_agents,
    )
    db.add(analysis)
    entry.ai_ans = result.ai_ans
    db.commit()
    db.refresh(analysis)
    return analysis


def _sync_diary_to_memory(
    entry: DiaryEntryRow,
    ai_ans: str,
    container: ServiceContainer,
) -> None:
    """Persist a diary-derived event into episodic memory and trigger promotion.

    This bridges the gap identified in the memory-pipeline analysis: diary
    analyses were read by the multi-agent system but never written back.  We
    extract a short event summary + emotion label from the diary content, store
    it as an episodic entry, then ask the long-term layer to promote any
    recurring patterns into the user profile.

    Failures are logged and swallowed — memory is a best-effort enhancement,
    not a hard dependency of the analysis flow.
    """
    episodic = getattr(container, "episodic_memory", None)
    long_term = getattr(container, "long_term_memory", None)
    if episodic is None:
        logger.debug("Episodic memory unavailable; skip sync for diary_id=%s", entry.id)
        return

    content = entry.content or ""
    estimate = _emotion_estimator.estimate(content)

    # Build a concise event summary from the diary content.
    event_summary = content.strip().replace("\n", " ")[:120]
    if len(content.strip()) > 120:
        event_summary += "…"

    episodic_entry = EpisodicEntry(
        event=event_summary,
        emotion=estimate.label,
        ai_suggestion=(ai_ans or "")[:200],
        user_feedback="none",
        timestamp=datetime.utcnow().timestamp(),
        diary_ids=[str(entry.id)],
        importance=_DIARY_EPISODIC_IMPORTANCE,
        entry_id="",
    )

    try:
        stored = episodic.store(episodic_entry)
        if stored:
            logger.info(
                "Diary synced to episodic memory: diary_id=%s emotion=%s",
                entry.id,
                estimate.label,
            )
        else:
            logger.debug(
                "Episodic entry below threshold, not stored: diary_id=%s",
                entry.id,
            )
    except Exception as exc:
        logger.warning("Failed to store episodic entry for diary_id=%s: %s", entry.id, exc)
        return

    # Trigger long-term profile promotion from all episodic entries.
    if long_term is not None and stored:
        try:
            all_entries = list(episodic._entries)
            long_term.promote_from_episodic(
                user_id=episodic._user_id,
                episodic_entries=all_entries,
            )
            logger.debug("Long-term profile promotion completed for diary_id=%s", entry.id)
        except Exception as exc:
            logger.warning("Profile promotion failed for diary_id=%s: %s", entry.id, exc)


def create_analysis(
    db: Session,
    diary_id: int,
    *,
    planner: ExecutionPlanner,
    container: ServiceContainer | None = None,
) -> AnalysisRow:
    entry = db.query(DiaryEntryRow).filter(DiaryEntryRow.id == diary_id).first()
    if entry is None:
        raise DiaryNotFoundError(diary_id=diary_id)

    existing = db.query(AnalysisRow).filter(AnalysisRow.diary_id == diary_id).first()
    if existing is not None:
        raise DiaryAlreadyExistsError()

    recent_entries = diary_service.get_recent_entries(db)
    context = _build_context(entry, recent_entries)
    result = planner.execute(
        diary_id=diary_id,
        context=context,
        content=entry.content or "",
    )
    analysis = _persist_analysis(db, entry=entry, result=result)
    logger.info(
        "分析创建成功: diary_id=%d analysis_id=%d tokens=%d tier=%s",
        diary_id,
        analysis.id,
        analysis.token_cost or 0,
        analysis.execution_tier,
    )
    # Best-effort: sync diary event into episodic memory + trigger profile promotion.
    if container is not None:
        _sync_diary_to_memory(entry, result.ai_ans, container)
    return analysis


def get_analysis(db: Session, diary_id: int) -> AnalysisRow:
    analysis = db.query(AnalysisRow).filter(AnalysisRow.diary_id == diary_id).first()
    if analysis is None:
        raise AnalysisNotFoundError(diary_id=diary_id)
    return analysis


def get_analysis_by_id(db: Session, analysis_id: int) -> AnalysisRow:
    analysis = db.query(AnalysisRow).filter(AnalysisRow.id == analysis_id).first()
    if analysis is None:
        raise AnalysisNotFoundError(analysis_id=analysis_id)
    return analysis


def update_analysis(
    db: Session,
    diary_id: int,
    *,
    planner: ExecutionPlanner,
    container: ServiceContainer | None = None,
) -> AnalysisRow:
    entry = db.query(DiaryEntryRow).filter(DiaryEntryRow.id == diary_id).first()
    if entry is None:
        raise DiaryNotFoundError(diary_id=diary_id)

    existing = db.query(AnalysisRow).filter(AnalysisRow.diary_id == diary_id).first()
    if existing is None:
        raise AnalysisNotFoundError(diary_id=diary_id)

    current_length = len(entry.content or "")
    if existing.diary_length is not None and existing.diary_length == current_length:
        raise AnalysisUnchangedError()

    recent_entries = diary_service.get_recent_entries(db)
    context = _build_context(entry, recent_entries)
    result = planner.execute(
        diary_id=diary_id,
        context=context,
        content=entry.content or "",
    )

    existing.created_at = datetime.utcnow()
    existing.token_cost = result.token_cost
    existing.cache_hit_tokens = result.cache_hit_tokens
    existing.cache_miss_tokens = result.cache_miss_tokens
    existing.output_tokens = result.output_tokens
    existing.log = result.thk_log
    existing.diary_length = current_length
    existing.agent_mode = result.agent_mode
    existing.execution_tier = result.execution_tier
    existing.activated_agents = result.activated_agents
    entry.ai_ans = result.ai_ans

    db.commit()
    db.refresh(existing)
    logger.info("分析更新成功: diary_id=%d analysis_id=%d", diary_id, existing.id)
    # Best-effort: sync updated diary event into episodic memory + trigger promotion.
    if container is not None:
        _sync_diary_to_memory(entry, result.ai_ans, container)
    return existing


def delete_analysis(db: Session, analysis_id: int) -> bool:
    analysis = db.query(AnalysisRow).filter(AnalysisRow.id == analysis_id).first()
    if analysis is None:
        return False

    entry = db.query(DiaryEntryRow).filter(DiaryEntryRow.id == analysis.diary_id).first()
    if entry is not None:
        entry.ai_ans = None

    db.delete(analysis)
    db.commit()
    logger.info("分析删除成功: analysis_id=%d", analysis_id)
    return True


def delete_analysis_for_diary(db: Session, diary_id: int) -> bool:
    """Remove analysis (and diary ai_ans) for a diary entry."""
    analysis = db.query(AnalysisRow).filter(AnalysisRow.diary_id == diary_id).first()
    if analysis is None:
        return False
    return delete_analysis(db, analysis.id)


def regenerate_analysis(
    db: Session,
    diary_id: int,
    container: ServiceContainer,
) -> AnalysisRow:
    """Force a fresh AI reply — replaces any existing analysis."""
    delete_analysis_for_diary(db, diary_id)
    planner = container.build_execution_planner(db)
    return create_analysis(db, diary_id, planner=planner, container=container)


def trigger_analysis(db: Session, diary_id: int, container: ServiceContainer) -> AnalysisRow:
    """End-to-end entry: build planner from container and create analysis."""
    planner = container.build_execution_planner(db)
    return create_analysis(db, diary_id, planner=planner, container=container)


def rerun_analysis(db: Session, diary_id: int, container: ServiceContainer) -> AnalysisRow:
    """Re-run analysis when diary content changed."""
    planner = container.build_execution_planner(db)
    return update_analysis(db, diary_id, planner=planner, container=container)

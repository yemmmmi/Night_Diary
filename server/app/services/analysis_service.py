"""Analysis orchestration — diary lookup → AI router → persist result."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.infrastructure.models.analysis import AnalysisRow
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.services import diary_service
from app.services.ai.router import ExecutionPlanner
from app.shared.pipeline_trace import (
    PipelineTrace,
    reset_trace,
    set_trace,
    trace_span,
)
from app.shared.trace_persistence import persist_trace, publish_trace_complete_sync

if TYPE_CHECKING:
    from app.services.container import ServiceContainer
from app.shared.errors import (
    AnalysisNotFoundError,
    AnalysisUnchangedError,
    DiaryAlreadyExistsError,
    DiaryNotFoundError,
)

logger = logging.getLogger(__name__)


def _episodic_user_id(container: ServiceContainer) -> str:
    """Get the user_id from the container's episodic memory, or 'default'."""
    episodic = getattr(container, "episodic_memory", None)
    if episodic is not None:
        return str(getattr(episodic, "user_id", "default"))
    return "default"


# Importance threshold for diary-derived episodic entries.  Diary entries are
# the primary content of the product, so they default above the 0.5 store
# threshold to ensure they are actually persisted (not filtered out).
_DIARY_EPISODIC_IMPORTANCE = 0.6


def _build_context(
    db: Session, entry: DiaryEntryRow, recent_entries: list[DiaryEntryRow], *, user_id: str
) -> dict[str, str]:
    return {
        "current_content": entry.content or "",
        "tags_context": diary_service.format_emotion_context(db, entry, user_id=user_id),
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
        created_at=datetime.now(UTC),
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
    entry.reply = result.reply
    db.commit()
    db.refresh(analysis)
    return analysis


def _sync_diary_to_memory(
    entry: DiaryEntryRow,
    reply: str,
    container: ServiceContainer,
) -> None:
    """Persist a diary-derived event into episodic memory via MemoryGateway.

    Uses the :class:`ContentNormalizer` to produce a ``UnifiedMemoryAtom``
    and then :meth:`MemoryGateway.persist_atom` for the unified write path.
    This ensures structured fields (tags, mood_score, emotions) survive the
    journey into episodic storage, where the long-term promoter can detect
    recurring topics via tags instead of raw text matching.

    Failures are logged and swallowed — memory is a best-effort enhancement,
    not a hard dependency of the analysis flow.
    """
    from app.services.memory_gateway import MemoryGateway
    from app.services.normalizer import ContentNormalizer

    gw = MemoryGateway.from_container(container)
    if gw._episodic is None:
        logger.debug("Episodic memory unavailable; skip sync for diary_id=%s", entry.id)
        return

    atom = ContentNormalizer.from_diary(
        entry,
        reply=reply,
        user_id=_episodic_user_id(container),
    )

    try:
        stored = gw.persist_atom(atom)
        if stored:
            logger.info(
                "Diary synced to episodic memory: diary_id=%s emotion=%s tags=%s",
                entry.id,
                atom.emotion,
                atom.tags,
            )
        else:
            logger.debug(
                "Episodic entry below threshold, not stored: diary_id=%s",
                entry.id,
            )
    except Exception as exc:
        logger.warning("Failed to store episodic entry for diary_id=%s: %s", entry.id, exc)

    # ── Entity extraction sidecar (best-effort, fire-and-forget) ──
    # Diary content is the richest source of entities (persons, places, topics).
    # Extract asynchronously so it never blocks the analysis flow.
    try:
        from app.domain.agents.entity_extractor import schedule_entity_extraction

        schedule_entity_extraction(
            container,
            user_id=_episodic_user_id(container),
            conversation_id=str(entry.id),
            text=entry.content or "",
            source_label="diary",
        )
        logger.debug("Diary entity extraction scheduled: diary_id=%s", entry.id)
    except Exception as exc:
        logger.warning(
            "Diary entity extraction scheduling failed (non-blocking): diary_id=%s %s",
            entry.id,
            exc,
        )


def create_analysis(
    db: Session,
    diary_id: int,
    *,
    user_id: str,
    planner: ExecutionPlanner,
    container: ServiceContainer | None = None,
    style_fragment: str | None = None,
) -> tuple[AnalysisRow, int]:
    """Create analysis and return (row, referenced_memory_count)."""
    entry = (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.id == diary_id, DiaryEntryRow.user_id == user_id)
        .first()
    )
    if entry is None:
        raise DiaryNotFoundError(diary_id=diary_id)

    # diary_id is already validated to belong to the user above, so the
    # analysis query by diary_id is implicitly user-scoped.
    existing = db.query(AnalysisRow).filter(AnalysisRow.diary_id == diary_id).first()
    if existing is not None:
        raise DiaryAlreadyExistsError()

    recent_entries = diary_service.get_recent_entries(db, user_id=user_id)
    context = _build_context(db, entry, recent_entries, user_id=user_id)
    with trace_span(
        "S2_routing",
        "路由决策",
        input_snapshot={"diary_id": diary_id, "content_len": len(entry.content or "")},
    ) as span:
        result = planner.execute(
            diary_id=diary_id,
            context=context,
            content=entry.content or "",
            style_fragment=style_fragment,
        )
        if span:
            span.set_output(
                {"tier": result.execution_tier, "agent_mode": result.agent_mode}
            )
    with trace_span(
        "S6_persist",
        "持久化分析结果",
        input_snapshot={"diary_id": diary_id},
    ) as span:
        analysis = _persist_analysis(db, entry=entry, result=result)
        if span:
            span.set_output({"analysis_id": analysis.id})
    logger.info(
        "分析创建成功: diary_id=%d analysis_id=%d tokens=%d tier=%s",
        diary_id,
        analysis.id,
        analysis.token_cost or 0,
        analysis.execution_tier,
    )
    # Best-effort: sync diary event into episodic memory + trigger profile promotion.
    if container is not None:
        with trace_span(
            "S7_memory",
            "记忆同步",
            input_snapshot={"diary_id": diary_id},
        ) as span:
            _sync_diary_to_memory(entry, result.reply, container)
            if span:
                span.set_output({"synced": True})
    return analysis, result.referenced_memory_count


def get_analysis(db: Session, diary_id: int, *, user_id: str) -> AnalysisRow:
    analysis = (
        db.query(AnalysisRow)
        .join(DiaryEntryRow, AnalysisRow.diary_id == DiaryEntryRow.id)
        .filter(AnalysisRow.diary_id == diary_id, DiaryEntryRow.user_id == user_id)
        .first()
    )
    if analysis is None:
        raise AnalysisNotFoundError(diary_id=diary_id)
    return analysis


def get_analysis_by_id(db: Session, analysis_id: int, *, user_id: str) -> AnalysisRow:
    analysis = (
        db.query(AnalysisRow)
        .join(DiaryEntryRow, AnalysisRow.diary_id == DiaryEntryRow.id)
        .filter(AnalysisRow.id == analysis_id, DiaryEntryRow.user_id == user_id)
        .first()
    )
    if analysis is None:
        raise AnalysisNotFoundError(analysis_id=analysis_id)
    return analysis


def update_analysis(
    db: Session,
    diary_id: int,
    *,
    user_id: str,
    planner: ExecutionPlanner,
    container: ServiceContainer | None = None,
    style_fragment: str | None = None,
) -> tuple[AnalysisRow, int]:
    """Update analysis and return (row, referenced_memory_count)."""
    entry = (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.id == diary_id, DiaryEntryRow.user_id == user_id)
        .first()
    )
    if entry is None:
        raise DiaryNotFoundError(diary_id=diary_id)

    # diary_id is already validated to belong to the user above, so the
    # analysis query by diary_id is implicitly user-scoped.
    existing = db.query(AnalysisRow).filter(AnalysisRow.diary_id == diary_id).first()
    if existing is None:
        raise AnalysisNotFoundError(diary_id=diary_id)

    current_length = len(entry.content or "")
    if existing.diary_length is not None and existing.diary_length == current_length:
        raise AnalysisUnchangedError()

    recent_entries = diary_service.get_recent_entries(db, user_id=user_id)
    context = _build_context(db, entry, recent_entries, user_id=user_id)
    result = planner.execute(
        diary_id=diary_id,
        context=context,
        content=entry.content or "",
        style_fragment=style_fragment,
    )

    existing.created_at = datetime.now(UTC)
    existing.token_cost = result.token_cost
    existing.cache_hit_tokens = result.cache_hit_tokens
    existing.cache_miss_tokens = result.cache_miss_tokens
    existing.output_tokens = result.output_tokens
    existing.log = result.thk_log
    existing.diary_length = current_length
    existing.agent_mode = result.agent_mode
    existing.execution_tier = result.execution_tier
    existing.activated_agents = result.activated_agents
    entry.reply = result.reply

    db.commit()
    db.refresh(existing)
    logger.info("分析更新成功: diary_id=%d analysis_id=%d", diary_id, existing.id)
    # Best-effort: sync updated diary event into episodic memory + trigger promotion.
    if container is not None:
        _sync_diary_to_memory(entry, result.reply, container)
    return existing, result.referenced_memory_count


def delete_analysis(db: Session, analysis_id: int, *, user_id: str) -> bool:
    analysis = (
        db.query(AnalysisRow)
        .join(DiaryEntryRow, AnalysisRow.diary_id == DiaryEntryRow.id)
        .filter(AnalysisRow.id == analysis_id, DiaryEntryRow.user_id == user_id)
        .first()
    )
    if analysis is None:
        return False

    entry = (
        db.query(DiaryEntryRow)
        .filter(
            DiaryEntryRow.id == analysis.diary_id,
            DiaryEntryRow.user_id == user_id,
        )
        .first()
    )
    if entry is not None:
        entry.reply = None

    db.delete(analysis)
    db.commit()
    logger.info("分析删除成功: analysis_id=%d", analysis_id)
    return True


def delete_analysis_for_diary(db: Session, diary_id: int, *, user_id: str) -> bool:
    """Remove analysis (and diary reply) for a diary entry."""
    analysis = (
        db.query(AnalysisRow)
        .join(DiaryEntryRow, AnalysisRow.diary_id == DiaryEntryRow.id)
        .filter(AnalysisRow.diary_id == diary_id, DiaryEntryRow.user_id == user_id)
        .first()
    )
    if analysis is None:
        return False
    return delete_analysis(db, analysis.id, user_id=user_id)


def regenerate_analysis(
    db: Session,
    diary_id: int,
    container: ServiceContainer,
    *,
    user_id: str,
    style_fragment: str | None = None,
) -> tuple[AnalysisRow, int]:
    """Force a fresh AI reply — replaces any existing analysis."""
    delete_analysis_for_diary(db, diary_id, user_id=user_id)
    planner = container.build_execution_planner(db, user_id=user_id)
    return create_analysis(
        db,
        diary_id,
        user_id=user_id,
        planner=planner,
        container=container,
        style_fragment=style_fragment,
    )


def trigger_analysis(
    db: Session,
    diary_id: int,
    container: ServiceContainer,
    *,
    user_id: str,
    style_fragment: str | None = None,
    trace_id: str | None = None,
) -> tuple[AnalysisRow, int]:
    """End-to-end entry: build planner from container and create analysis.

    When *trace_id* is provided (developer mode), a :class:`PipelineTrace` is
    created and set in the context so that nested ``trace_span`` calls record
    their stages.  The trace is finalized, persisted, and published in the
    ``finally`` block — all best-effort.
    """
    trace: PipelineTrace | None = None
    token = None
    if trace_id:
        trace = PipelineTrace(
            trace_id=trace_id, scenario="diary_reply", user_id=user_id
        )
        token = set_trace(trace)
    try:
        planner = container.build_execution_planner(db, user_id=user_id)
        result = create_analysis(
            db,
            diary_id,
            user_id=user_id,
            planner=planner,
            container=container,
            style_fragment=style_fragment,
        )
        if trace is not None:
            trace.end()
        return result
    except Exception:
        if trace is not None:
            trace.end(status="error")
        raise
    finally:
        if trace is not None:
            persist_trace(db, trace, ref_id=str(diary_id))
            try:
                publish_trace_complete_sync(trace)
            except Exception:
                pass
            if token is not None:
                reset_trace(token)


def rerun_analysis(
    db: Session,
    diary_id: int,
    container: ServiceContainer,
    *,
    user_id: str,
    style_fragment: str | None = None,
) -> tuple[AnalysisRow, int]:
    """Re-run analysis when diary content changed."""
    planner = container.build_execution_planner(db, user_id=user_id)
    return update_analysis(
        db,
        diary_id,
        user_id=user_id,
        planner=planner,
        container=container,
        style_fragment=style_fragment,
    )

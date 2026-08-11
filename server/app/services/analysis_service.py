"""Analysis orchestration — diary lookup → AI router → persist result."""

from __future__ import annotations

import asyncio
import contextlib
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
from app.shared.token_utils import estimate_tokens
from app.shared.trace_persistence import persist_trace, publish_trace_complete_sync

if TYPE_CHECKING:
    from app.domain.agents.graph import MultiAgentGraph
    from app.domain.agents.state import MultiAgentState
    from app.services.container import ServiceContainer
from app.shared.errors import (
    AIServiceUnavailableError,
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

    # Extract plain data before committing — ORM attributes expire on commit
    # (expire_on_commit=True), so we capture the content string now to avoid
    # a lazy reload during the LLM call below.
    content_text = entry.content or ""

    # Release the DB connection back to the pool before the long-running LLM
    # network call. The session remains usable — it will re-acquire a
    # connection on the next query (in _persist_analysis).
    db.commit()

    with trace_span(
        "S2_routing",
        "路由决策",
        input_snapshot={"diary_id": diary_id, "content_len": len(content_text)},
    ) as span:
        result = planner.execute(
            diary_id=diary_id,
            context=context,
            content=content_text,
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

    # Extract plain data before committing — ORM attributes expire on commit.
    content_text = entry.content or ""

    # Release the DB connection before the long-running LLM call.
    db.commit()

    result = planner.execute(
        diary_id=diary_id,
        context=context,
        content=content_text,
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
    planner = container.build_execution_planner(user_id=user_id)
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

    Uses **upsert** semantics: if an analysis already exists for this diary,
    it is deleted and recreated.  This avoids ``UNIQUE constraint`` failures
    when the frontend re-triggers analysis on a diary that was previously
    analyzed (e.g. after editing the diary content).

    When *trace_id* is provided (developer mode), a :class:`PipelineTrace` is
    created and set in the context so that nested ``trace_span`` calls record
    their stages.  The trace is finalized, persisted, and published in the
    ``finally`` block — all best-effort.

    Trace persistence uses a **separate session** so that a failed analysis
    commit does not corrupt the session used for trace storage.
    """
    trace: PipelineTrace | None = None
    token = None
    if trace_id:
        trace = PipelineTrace(
            trace_id=trace_id, scenario="diary_reply", user_id=user_id
        )
        token = set_trace(trace)
    try:
        # Upsert: if an analysis already exists, remove it first so that
        # create_analysis doesn't hit a UNIQUE constraint violation.
        existing = db.query(AnalysisRow).filter(AnalysisRow.diary_id == diary_id).first()
        if existing is not None:
            delete_analysis_for_diary(db, diary_id, user_id=user_id)

        planner = container.build_execution_planner(user_id=user_id)
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
            # Use a separate session so that a failed analysis commit
            # (which leaves the request session in a rolled-back state)
            # does not prevent trace persistence.
            try:
                trace_db = container.session()
                try:
                    persist_trace(trace_db, trace, ref_id=str(diary_id))
                finally:
                    trace_db.close()
            except Exception as exc:
                logger.warning("Trace persistence failed: %s", exc)
            with contextlib.suppress(Exception):
                publish_trace_complete_sync(trace)
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
    planner = container.build_execution_planner(user_id=user_id)
    return update_analysis(
        db,
        diary_id,
        user_id=user_id,
        planner=planner,
        container=container,
        style_fragment=style_fragment,
    )


# ── V3 P4 Task 3: streaming analysis (Scene-1) ─────────────────────────


async def _prepare_analysis_graph(
    db: Session,
    container: ServiceContainer,
    diary_id: int,
    user_id: str,
) -> tuple[MultiAgentGraph, MultiAgentState]:
    """Build the multi-agent ``graph`` + initial ``state`` for diary analysis.

    Extracted from the graph/state setup that ``create_analysis`` reaches via
    ``ExecutionPlanner.execute -> run_multi_agent``. Kept as a standalone
    helper so the streaming path (``trigger_analysis_streaming``) can build
    the same inputs without going through the sync planner, and so future
    refactors can collapse ``create_analysis`` onto this helper without
    duplicating the wiring.

    Mirrors :func:`run_multi_agent` for everything that happens *before*
    ``graph.invoke``: diary lookup, episodic context load, long-term profile
    hydration, working-memory seeding, and initial state construction. The
    post-``invoke`` working-memory sync stays in :func:`run_multi_agent`
    because it needs the final state, which the streaming path materialises
    lazily via :meth:`MultiAgentGraph.invoke_streaming`.
    """
    from app.services.ai.multi_agent_executor import _load_episodic_context

    entry = (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.id == diary_id, DiaryEntryRow.user_id == user_id)
        .first()
    )
    if entry is None:
        raise DiaryNotFoundError(diary_id=diary_id)

    content_text = entry.content or ""

    # Release the DB connection back to the pool before any long-running LLM
    # call. The session stays usable (re-acquires a connection on next query,
    # e.g. in _persist_analysis_streaming).
    db.commit()

    graph = container.build_multi_agent_graph(user_id=user_id)
    if graph is None:
        # No LLM configured — degrade the same way the sync planner does.
        raise AIServiceUnavailableError("Multi-agent graph unavailable (no LLM configured)")

    episodic = getattr(container, "episodic_memory", None)
    long_term = getattr(container, "long_term_memory", None)
    working_memory = getattr(container, "working_memory", None)

    episodic_context = _load_episodic_context(episodic, query=content_text)
    long_term_profile: dict[str, Any] = {}
    if long_term is not None:
        try:
            long_term_profile = long_term.get_profile("default").model_dump()
        except Exception as exc:
            logger.warning("Long-term memory load failed: %s", exc)

    if working_memory is not None:
        from app.domain.memory.types import UserProfile

        working_memory.load_context(
            str(diary_id),
            UserProfile.model_validate(long_term_profile) if long_term_profile else UserProfile(),
        )
        ctx = working_memory.context
        if ctx is not None:
            working_memory.update_context(
                ctx,
                {"diary_content": content_text, "long_term_profile": long_term_profile},
            )

    state: MultiAgentState = {
        "diary_id": str(diary_id),
        "diary_content": content_text,
        "style_fragment": "",
        "intent": "",
        "tier": "",
        "token_budget": 0,
        "activated_agents": [],
        "activated_skills": [],
        "episodic_context": episodic_context,
        "long_term_profile": long_term_profile,
        "compressed_history": "",
        "retrieval_context": "",
        "empathy_response": "",
        "insight_response": "",
        "final_response": "",
        "total_tokens_used": 0,
        "agent_mode": "multi_agent",
        "cache_hit_tokens": 0,
        "cache_miss_tokens": 0,
        "output_tokens": 0,
        "errors": [],
    }
    return graph, state


def _persist_analysis_streaming(
    db: Session,
    *,
    diary_id: int,
    user_id: str,
    reply_text: str,
    token_cost: int,
) -> None:
    """Persist a streaming analysis result to ``AnalysisRow`` (best-effort).

    Streaming-mode counterpart of :func:`_persist_analysis`. Unlike the sync
    path, the worker outputs / tier / token breakdown are not surfaced to the
    caller (the streaming API only yields reply tokens), so we record the
    reply on the diary entry, write an ``AnalysisRow`` with an estimated
    token cost (real tokenizer is deferred to P5), and mark ``agent_mode``
    as ``streaming`` for observability.

    Uses upsert semantics: an existing analysis for this diary is replaced
    first, matching :func:`trigger_analysis`'s contract.
    """
    entry = (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.id == diary_id, DiaryEntryRow.user_id == user_id)
        .first()
    )
    if entry is None:
        logger.warning(
            "Streaming persist skipped: diary_id=%s not found for user_id=%s",
            diary_id,
            user_id,
        )
        return

    existing = db.query(AnalysisRow).filter(AnalysisRow.diary_id == diary_id).first()
    if existing is not None:
        db.delete(existing)
        db.flush()

    analysis = AnalysisRow(
        diary_id=entry.id,
        created_at=datetime.now(UTC),
        token_cost=token_cost,
        cache_hit_tokens=0,
        cache_miss_tokens=0,
        output_tokens=0,
        log="[Streaming] agent_mode=streaming",
        diary_length=len(entry.content or ""),
        agent_mode="streaming",
        execution_tier="streaming",
        activated_agents="",
    )
    db.add(analysis)
    entry.reply = reply_text
    db.commit()
    db.refresh(analysis)
    logger.info(
        "Streaming analysis persisted: diary_id=%d analysis_id=%d tokens=%d",
        diary_id,
        analysis.id,
        token_cost,
    )


# Streaming fallback shown to the user when the LLM/graph fails mid-stream.
# Half-width punctuation avoids RUF001 (ambiguous unicode) on app/services/**.
_STREAMING_FALLBACK_FEEDBACK = "抱歉, 分析暂时不可用, 请稍后重试。"


async def trigger_analysis_streaming(
    db: Session,
    container: ServiceContainer,
    *,
    diary_id: int,
    user_id: str,
    trace_id: str,
) -> None:
    """Scene-1 streaming analysis with P1 terminating guarantee.

    Pipeline:
        ``_prepare_analysis_graph`` -> ``run_multi_agent_streaming`` ->
        publish SSE events -> ``_persist_analysis_streaming``.

    The ``try``/``except``/``finally`` structure guarantees that a
    ``REPLY_END`` event is **always** published (P1 terminating-reply
    contract) — on normal completion, on LLM failure, on user cancel, and as
    an ultimate fallback in ``finally``. Persistence also runs in the
    ``finally`` block so the ``AnalysisRow`` is written even if the frontend
    disconnects mid-stream.
    """
    from app.services.ai.multi_agent_executor import run_multi_agent_streaming
    from app.shared.streaming_events import (
        publish_reply_end,
        publish_reply_start,
        publish_text_delta,
        publish_text_end,
    )

    reply_started = False
    reply_end_sent = False
    final_reply_text = ""
    estimated_tokens = 0

    try:
        graph, state = await _prepare_analysis_graph(db, container, diary_id, user_id)

        await publish_reply_start(trace_id, intent="scene1_streaming")
        reply_started = True

        async for token in run_multi_agent_streaming(graph=graph, state=state):
            if isinstance(token, str) and token:
                final_reply_text += token
                await publish_text_delta(trace_id, token)

        estimated_tokens = estimate_tokens(final_reply_text)
        await publish_text_end(trace_id)
        await publish_reply_end(trace_id)
        reply_end_sent = True

    except asyncio.CancelledError:
        # User-initiated abort — clean shutdown, no fallback text needed.
        if reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="cancelled")
            reply_end_sent = True
        raise
    except Exception as exc:
        logger.exception("Scene-1 streaming failed: %s", exc)
        if not reply_started:
            with contextlib.suppress(Exception):
                await publish_reply_start(trace_id, intent="error")
            reply_started = True
        with contextlib.suppress(Exception):
            await publish_text_delta(trace_id, _STREAMING_FALLBACK_FEEDBACK)
            final_reply_text = _STREAMING_FALLBACK_FEEDBACK
        with contextlib.suppress(Exception):
            await publish_reply_end(trace_id, error=str(exc))
        reply_end_sent = True
    finally:
        # Persist (guaranteed write even if the frontend disconnects).
        if final_reply_text:
            with contextlib.suppress(Exception):
                _persist_analysis_streaming(
                    db,
                    diary_id=diary_id,
                    user_id=user_id,
                    reply_text=final_reply_text,
                    token_cost=estimated_tokens,
                )
        # Ultimate fallback: guarantee REPLY_END.
        if trace_id and reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="finalized")

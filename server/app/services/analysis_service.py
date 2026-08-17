"""Analysis orchestration — diary lookup → AI router → persist result."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.infrastructure.models.analysis import AnalysisRow
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.task_queue import enqueue_task
from app.services import diary_service
from app.services.ai.router import ExecutionPlanner, AnalysisResult
from app.shared.pipeline_trace import (
    PipelineTrace,
    reset_trace,
    set_trace,
    trace_span,
)
from app.shared.token_utils import estimate_tokens
from app.shared.trace_persistence import persist_trace, publish_trace_complete_sync

if TYPE_CHECKING:
    from app.services.container import ServiceContainer
    from app.shared.digest import CardDigest, DiaryDigest
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
        intent=getattr(result, "intent", "") or None,
    )
    db.add(analysis)
    entry.reply = result.reply
    db.commit()
    db.refresh(analysis)
    return analysis


# ── V3 tree-hole: scene-1 daily path ────────────────────────────────────
# The daily reply is a brief "tree-hole" acknowledgment (1-3 sentences) plus
# a structured day digest; deep conversation belongs to scene 2. The legacy
# multi-agent graph stays for weekly reports (weekly_service reuses
# ExecutionPlanner directly).


def _entry_day(entry: DiaryEntryRow) -> date:
    """The digest day for an entry: diary date, else creation date."""
    if entry.date is not None:
        return entry.date
    if entry.created_at is not None and hasattr(entry.created_at, "date"):
        return entry.created_at.date()
    return datetime.now(UTC).date()


def _day_card_digests(db: Session, user_id: str, day: date) -> list[Any]:
    """Aggregate the day's cards into digest ``cards`` entries (zero LLM)."""
    from app.services.digest_service import cards_to_digest, load_day_cards

    return cards_to_digest(load_day_cards(db, user_id=user_id, day=day))


def _treehole_llm(planner: ExecutionPlanner | None, container: Any) -> Any:
    """Resolve the LLM for the tree-hole call (planner first, then container)."""
    if planner is not None:
        llm = planner.llm_for_tier("light")
        if llm is not None:
            return llm
    if container is not None:
        resolver = getattr(container, "_llm_for_tier", None)
        if callable(resolver):
            try:
                return resolver("light", agent_name="treehole")
            except Exception as exc:
                logger.warning("treehole llm resolve failed: %s", exc)
    return None


def _treehole_tracer(container: Any) -> Any:
    return getattr(container, "llm_tracer", None)


def _run_async_sync(coro: Any) -> Any:
    """Run a coroutine from a sync context (mirrors run_multi_agent)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        if loop.is_closed():
            raise RuntimeError
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _run_treehole_analysis(
    db: Session,
    planner: ExecutionPlanner,
    container: Any,
    entry: DiaryEntryRow,
    content_text: str,
    *,
    user_id: str,
) -> tuple[AnalysisResult, "DiaryDigest"]:
    """Run the scene-1 tree-hole path (sync wrapper for the sync callers).

    Returns ``(AnalysisResult, DiaryDigest)``. Crisis diaries short-circuit
    to the safe template before any LLM call; LLM failure degrades to rules.
    """
    from app.services.ai.treehole import (
        classify_intent,
        detect_crisis,
        fallback_treehole,
        run_treehole,
    )
    from app.shared.digest import DiaryDigest

    day = _entry_day(entry)
    cards = _day_card_digests(db, user_id, day)

    async def _inner() -> tuple[AnalysisResult, DiaryDigest]:
        intent_result = await classify_intent(content_text, tracer=_treehole_tracer(container))
        intent = intent_result.intent_category
        confidence = float(intent_result.confidence)

        if detect_crisis(content_text):
            from app.shared.crisis_guard import get_crisis_guard

            safe = get_crisis_guard().safe_response
            outcome = fallback_treehole(
                content=content_text,
                day=day,
                intent="crisis_signal",
                confidence=1.0,
                diary_tags=[],
                cards=cards,
                emotion_label="crisis",
                emotion_score=-1.0,
                mood=0.0,
            )
            result = AnalysisResult(
                reply=safe,
                token_cost=0,
                cache_hit_tokens=0,
                cache_miss_tokens=0,
                output_tokens=0,
                thk_log="[Tree-hole] crisis short-circuit (safe template)",
                agent_mode="treehole-crisis",
                execution_tier="crisis",
                activated_agents="",
                referenced_memory_count=0,
                intent="crisis_signal",
            )
            return result, outcome.digest

        llm = _treehole_llm(planner, container)
        tags = [t.name for t in entry.tags if t.name] if entry.tags else []
        if llm is None:
            outcome = fallback_treehole(
                content=content_text,
                day=day,
                intent=intent,
                confidence=confidence,
                diary_tags=tags,
                cards=cards,
            )
        else:
            outcome = await run_treehole(
                content=content_text,
                day=day,
                llm=llm,
                tracer=_treehole_tracer(container),
                intent_result=intent_result,
                diary_tags=tags,
                cards=cards,
                model=getattr(llm, "model", ""),
            )
        result = AnalysisResult(
            reply=outcome.reply,
            token_cost=outcome.token_cost,
            cache_hit_tokens=0,
            cache_miss_tokens=0,
            output_tokens=0,
            thk_log=outcome.log,
            agent_mode="treehole",
            execution_tier="treehole",
            activated_agents="",
            referenced_memory_count=0,
            intent=outcome.intent or intent,
        )
        return result, outcome.digest

    return _run_async_sync(_inner())


def _persist_digest_for_analysis(
    db: Session,
    container: Any,
    *,
    entry: DiaryEntryRow,
    digest: "DiaryDigest",
    user_id: str,
) -> None:
    """Upsert the day digest (staged in the same transaction as the analysis)."""
    from app.services.digest_service import upsert_digest

    upsert_digest(db, user_id=user_id, day=_entry_day(entry), digest=digest)


def _sync_diary_to_memory(
    entry: DiaryEntryRow,
    reply: str,
    container: ServiceContainer,
) -> None:
    """Persist a diary-derived event into episodic memory via MemoryGateway.

    Uses the :class:`ContentNormalizer` to produce a ``UnifiedMemoryAtom``
    and then schedules :meth:`MemoryGateway.persist_atom` via
    :func:`enqueue_task` (fire-and-forget) for the unified write path.
    This ensures structured fields (tags, mood_score, emotions) survive the
    journey into episodic storage, where the long-term promoter can detect
    recurring topics via tags instead of raw text matching.

    The write is dispatched off the request thread: ``persist_atom`` opens
    its own DB session via the episodic store's ``session_factory`` and runs
    to completion in a background worker. Failures are logged and swallowed
    — memory is a best-effort enhancement, not a hard dependency of the
    analysis flow.
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
        # Fire-and-forget: persist_atom opens its own session via the
        # episodic store's session_factory (thread-safe), so dispatching it
        # off the request thread eliminates 50-300ms of tail latency from
        # episodic store + DB persist + long-term profile promotion.
        enqueue_task(gw.persist_atom, atom)
        logger.debug(
            "Diary episodic write dispatched: diary_id=%s emotion=%s tags=%s",
            entry.id,
            atom.emotion,
            atom.tags,
        )
    except Exception as exc:
        logger.warning("Failed to dispatch episodic write for diary_id=%s: %s", entry.id, exc)

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
        "S2_treehole",
        "树洞分析与摘要提取",
        input_snapshot={"diary_id": diary_id, "content_len": len(content_text)},
    ) as span:
        result, digest = _run_treehole_analysis(
            db, planner, container, entry, content_text, user_id=user_id
        )
        if span:
            span.set_output({"intent": result.intent, "agent_mode": result.agent_mode})
    with trace_span(
        "S6_persist",
        "持久化分析结果",
        input_snapshot={"diary_id": diary_id},
    ) as span:
        # Stage the day digest in the same transaction as the analysis row
        # (the commit inside _persist_analysis flushes both).
        _persist_digest_for_analysis(db, container, entry=entry, digest=digest, user_id=user_id)
        analysis = _persist_analysis(db, entry=entry, result=result)
        if span:
            span.set_output({"analysis_id": analysis.id})
    logger.info(
        "分析创建成功: diary_id=%d analysis_id=%d tokens=%d mode=%s",
        diary_id,
        analysis.id,
        analysis.token_cost or 0,
        analysis.agent_mode,
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
                # Memory write is dispatched fire-and-forget via enqueue_task,
                # so this span now records only the scheduling latency (µs),
                # not the full episodic store + DB persist + promotion.
                span.set_output({"dispatched": True})
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

    result, digest = _run_treehole_analysis(
        db, planner, container, entry, content_text, user_id=user_id
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
    existing.intent = result.intent or None
    entry.reply = result.reply

    _persist_digest_for_analysis(db, container, entry=entry, digest=digest, user_id=user_id)
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
        trace = PipelineTrace(trace_id=trace_id, scenario="diary_reply", user_id=user_id)
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


def _finalize_streaming_memory_write(
    db: Session,
    container: ServiceContainer,
    *,
    diary_id: int,
    user_id: str,
    reply_text: str,
    trace_id: str,
) -> None:
    """V3 P7: run the FinalizeMiddleware write-back after a streaming analysis.

    Fixes the P7-discovered gap: the sync paths (``create_analysis`` /
    ``update_analysis``) persist the diary event into episodic memory via
    ``_sync_diary_to_memory``, but ``trigger_analysis_streaming`` never did.
    The middleware hook unifies the write-back pattern with scene 2 and is
    best-effort (failures are logged, never propagated).
    """
    from app.shared.middleware import MiddlewareContext, build_default_pipeline

    entry = (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.id == diary_id, DiaryEntryRow.user_id == user_id)
        .first()
    )
    if entry is None:
        return

    build_default_pipeline().run_on_reply(
        MiddlewareContext(
            scenario="diary_reply",
            user_id=user_id,
            content=entry.content or "",
            trace_id=trace_id,
            diary_id=str(diary_id),
            reply_text=reply_text,
            container=container,
            always_persist=True,
            extra={"entry": entry},
        )
    )


def _split_reply_chunks(text: str, chunk_size: int = 12) -> list[str]:
    """Split the short reply into chunks for SSE streaming (keeps punctuation)."""
    import re

    if not text:
        return []
    sentences = re.split(r"(?<=[。！？\n.!?])", text)
    chunks: list[str] = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        while len(sent) > chunk_size:
            chunks.append(sent[:chunk_size])
            sent = sent[chunk_size:]
        if sent:
            chunks.append(sent)
    return chunks


async def trigger_analysis_streaming(
    db: Session,
    container: ServiceContainer,
    *,
    diary_id: int,
    user_id: str,
    trace_id: str,
) -> None:
    """Scene-1 tree-hole streaming with P1 terminating guarantee.

    Pipeline:
        classify (rule) -> crisis check -> single tree-hole LLM call ->
        publish SSE chunks -> persist reply + day digest.

    Crisis diaries short-circuit to the safe template (single chunk, never
    streamed from the LLM). The ``try``/``except``/``finally`` structure
    guarantees ``REPLY_END`` is **always** published; persistence + digest
    upsert run in ``finally`` so data survives a frontend disconnect.
    """
    from app.services.ai.treehole import (
        classify_intent,
        detect_crisis,
        fallback_treehole,
        run_treehole,
    )
    from app.services.digest_service import upsert_digest
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
    digest = None
    day = None

    try:
        entry = (
            db.query(DiaryEntryRow)
            .filter(DiaryEntryRow.id == diary_id, DiaryEntryRow.user_id == user_id)
            .first()
        )
        if entry is None:
            raise DiaryNotFoundError(diary_id=diary_id)
        content_text = entry.content or ""
        day = _entry_day(entry)
        cards = _day_card_digests(db, user_id, day)
        tags = [t.name for t in entry.tags if t.name] if entry.tags else []

        intent_result = await classify_intent(content_text, tracer=_treehole_tracer(container))
        intent = intent_result.intent_category

        # ── Crisis path: safe template as a single chunk (never LLM) ──
        if detect_crisis(content_text):
            from app.shared.crisis_guard import get_crisis_guard

            safe = get_crisis_guard().safe_response
            await publish_reply_start(trace_id, intent="crisis_signal")
            reply_started = True
            await publish_text_delta(trace_id, safe)
            final_reply_text = safe
            await publish_text_end(trace_id)
            await publish_reply_end(trace_id)
            reply_end_sent = True
            outcome = fallback_treehole(
                content=content_text,
                day=day,
                intent="crisis_signal",
                confidence=1.0,
                diary_tags=[],
                cards=cards,
                emotion_label="crisis",
                emotion_score=-1.0,
                mood=0.0,
            )
            digest = outcome.digest
            return

        # ── Normal path: single tree-hole call, stream the short reply ──
        llm = _treehole_llm(None, container)
        if llm is None:
            outcome = fallback_treehole(
                content=content_text,
                day=day,
                intent=intent,
                confidence=float(intent_result.confidence),
                diary_tags=tags,
                cards=cards,
            )
        else:
            outcome = await run_treehole(
                content=content_text,
                day=day,
                llm=llm,
                tracer=_treehole_tracer(container),
                intent_result=intent_result,
                diary_tags=tags,
                cards=cards,
                model=getattr(llm, "model", ""),
            )
        digest = outcome.digest
        estimated_tokens = outcome.token_cost or estimate_tokens(outcome.reply)

        await publish_reply_start(trace_id, intent=intent)
        reply_started = True
        for chunk in _split_reply_chunks(outcome.reply):
            final_reply_text += chunk
            await publish_text_delta(trace_id, chunk)
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
            # V3 tree-hole: upsert the day digest (same transaction).
            if digest is not None and day is not None:
                with contextlib.suppress(Exception):
                    upsert_digest(db, user_id=user_id, day=day, digest=digest)
                    db.commit()
            # V3 P7: FinalizeMiddleware — episodic memory write-back.
            with contextlib.suppress(Exception):
                _finalize_streaming_memory_write(
                    db,
                    container,
                    diary_id=diary_id,
                    user_id=user_id,
                    reply_text=final_reply_text,
                    trace_id=trace_id,
                )
        # Ultimate fallback: guarantee REPLY_END.
        if trace_id and reply_started and not reply_end_sent:
            with contextlib.suppress(Exception):
                await publish_reply_end(trace_id, error="finalized")

"""Day-level digest worker — rebuild the daily digest for typed diary entries.

PR9 contract:

- Triggered (async, via :func:`enqueue_task`) whenever a typed diary entry is
  created / updated / deleted by the user (manual writing or the Record skill).
- The digest's ``diary`` section is the **aggregate extraction of ALL typed
  entries of that day** (ordered by ``created_at``), so repeated triggers are
  idempotent and the "last-writer-wins" hazard is gone.
- The ``cards`` section is preserved verbatim from the existing digest — card
  writes keep owning it via ``refresh_cards_section``.
- Extraction reuses the tree-hole pipeline (:func:`run_treehole`) with its
  reply output ignored; crisis diaries short-circuit to the safe template and
  LLM unavailability degrades to rule extraction (``fallback_treehole``).
- After persisting, the source entry is dispatched to episodic memory via
  ``_sync_diary_to_memory`` (project hard constraint: diary analysis must
  write episodic memory and trigger long-term profile promotion).

The RQ entry point takes only picklable primitives; the container is rebuilt
per run (``create_core`` is cheap, SQLite + tracers only). In threading
fallback mode the caller may pass a live container to avoid a rebuild.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.shared.digest import DiaryDigest

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

_in_flight: set[tuple[str, str]] = set()
_in_flight_lock = threading.Lock()

_CONTENT_SEPARATOR = "\n---\n"

_session_factory: Any = None
_session_factory_lock = threading.Lock()


def _parse_day(day: str) -> date:
    return datetime.strptime(day, "%Y-%m-%d").date()


def _get_session_factory() -> Any:
    """Process-wide lazy session factory (built once, reused across runs)."""
    global _session_factory
    with _session_factory_lock:
        if _session_factory is None:
            from app.services.container import ServiceContainer

            _session_factory = ServiceContainer.create_core().session_factory
        return _session_factory


def _build_container() -> ServiceContainer | None:
    from app.services.container import ServiceContainer

    try:
        return ServiceContainer.create_core()
    except Exception as exc:
        logger.warning("digest worker container build failed: %s", exc)
        return None


def _aggregate_day_entries(db: Session, *, user_id: str, day: date) -> list[Any]:
    from app.infrastructure.models.diary_entry import DiaryEntryRow

    rows = (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.user_id == user_id, DiaryEntryRow.date == day)
        .order_by(DiaryEntryRow.created_at)
        .all()
    )
    return rows


def run_day_digest_refresh(user_id: str, day: str, diary_id: int) -> None:
    """Rebuild the ``(user_id, day)`` digest from all typed entries of the day.

    RQ entry point — takes only picklable primitives. Best-effort throughout:
    any failure is logged and swallowed (the digest consumer already falls
    back to full-text rendering).
    """
    from app.services.digest_service import get_digest, upsert_digest

    try:
        day_date = _parse_day(day)
    except ValueError:
        logger.warning("digest worker: invalid day %r for user %s", day, user_id)
        return

    container = _build_container()
    try:
        session = _get_session_factory()()
    except Exception as exc:
        logger.warning("digest worker session factory failed: %s", exc)
        _release_in_flight(user_id, day)
        return
    try:
        entries = _aggregate_day_entries(session, user_id=user_id, day=day_date)
        existing = get_digest(session, user_id=user_id, day=day_date)
        cards = existing.cards if existing is not None else []

        if not entries:
            _clear_diary_section(session, user_id=user_id, day=day_date, cards=cards)
            return

        from app.services.ai.treehole import detect_crisis, fallback_treehole, run_treehole

        content_text = _CONTENT_SEPARATOR.join((e.content or "") for e in entries if e.content)
        entry_for_memory = next((e for e in entries if e.id == diary_id), None)

        if detect_crisis(content_text):
            outcome = fallback_treehole(
                content=content_text,
                day=day_date,
                intent="crisis_signal",
                confidence=1.0,
                diary_tags=[],
                cards=cards,
                emotion_label="crisis",
                emotion_score=-1.0,
                mood=0.0,
            )
            digest = outcome.digest
        else:
            llm = _resolve_llm(container)
            if llm is None:
                outcome = fallback_treehole(
                    content=content_text,
                    day=day_date,
                    intent="",
                    confidence=0.0,
                    diary_tags=_entry_tags(entries),
                    cards=cards,
                )
                digest = outcome.digest
            else:
                import asyncio

                outcome = asyncio.run(
                    run_treehole(
                        content=content_text,
                        day=day_date,
                        llm=llm,
                        diary_tags=_entry_tags(entries),
                        cards=cards,
                    )
                )
                digest = outcome.digest

        _apply_card_preservation(session, user_id=user_id, day=day_date, digest=digest)
        upsert_digest(session, user_id=user_id, day=day_date, digest=digest)
        session.commit()
        logger.info(
            "Day digest rebuilt: user_id=%s date=%s entries=%d source=%s",
            user_id,
            day,
            len(entries),
            digest.source,
        )

        if container is not None and entry_for_memory is not None:
            _dispatch_memory_sync(entry_for_memory, container, digest)
    except Exception as exc:
        session.rollback()
        logger.warning(
            "Day digest refresh failed (non-blocking): user_id=%s day=%s diary_id=%s error=%s",
            user_id,
            day,
            diary_id,
            exc,
            exc_info=True,
        )
    finally:
        session.close()
        _release_in_flight(user_id, day)


def _resolve_llm(container: ServiceContainer | None) -> Any:
    if container is None:
        return None
    try:
        return container._llm_for_tier("light", agent_name="digest_worker")
    except Exception as exc:
        logger.warning("digest worker LLM resolve failed: %s", exc)
        return None


def _entry_tags(entries: list[Any]) -> list[str]:
    tags: list[str] = []
    for entry in entries:
        if not entry.tags:
            continue
        for tag in entry.tags:
            name = getattr(tag, "name", "")
            if name and name not in tags:
                tags.append(name)
    return tags[:20]


def _clear_diary_section(
    db: Session, *, user_id: str, day: date, cards: list[Any]
) -> None:
    """No typed entries left — reset the diary section, keep cards intact."""
    from app.services.digest_service import upsert_digest

    digest = DiaryDigest(
        digest_type="basic",
        date=day,
        source="card",
        cards=list(cards),
    )
    upsert_digest(db, user_id=user_id, day=day, digest=digest)
    db.commit()
    logger.info("Day digest diary section cleared: user_id=%s date=%s", user_id, day)


def _apply_card_preservation(db: Session, *, user_id: str, day: date, digest: DiaryDigest) -> None:
    """Carry over the stored ``cards`` section into the freshly extracted digest.

    ``run_treehole``/``fallback_treehole`` already receive the day's cards as
    input, but in rule-fallback mode the cards list may be dropped; this pass
    guarantees the section survives every rebuild. Only the *card-aware*
    source combination is recomputed — the extraction mode itself ("llm" vs
    "rule") comes from the tree-hole pipeline and is never overridden here.
    """
    from app.services.digest_service import get_digest

    if digest.cards:
        return
    stored = get_digest(db, user_id=user_id, day=day)
    if stored is not None and stored.cards:
        digest.cards = stored.cards
    if digest.source == "llm" and digest.cards:
        digest.source = "card+llm"


def _dispatch_memory_sync(entry: Any, container: ServiceContainer, digest: DiaryDigest) -> None:
    """Dispatch the episodic-memory write for the triggering entry (best-effort)."""
    try:
        from app.services.analysis_service import _sync_diary_to_memory

        _sync_diary_to_memory(entry, "", container, digest=digest)
    except Exception as exc:
        logger.warning(
            "Digest worker memory dispatch failed: diary_id=%s error=%s", entry.id, exc
        )


def schedule_day_digest_refresh(
    user_id: str,
    day: str,
    diary_id: int,
    container: ServiceContainer | None = None,
) -> str | None:
    """Schedule an async day-digest rebuild, with in-flight deduplication.

    Called from request threads (diary_service); must never raise. Returns
    the job id / thread name (or ``None`` when skipped or failed to enqueue).
    """
    key = (user_id, day)
    with _in_flight_lock:
        if key in _in_flight:
            logger.debug("Digest refresh already scheduled for %s %s", user_id, day)
            return None
        _in_flight.add(key)
    try:
        from app.infrastructure.task_queue import enqueue_task

        return enqueue_task(
            "app.services.digest_worker.run_day_digest_refresh",
            user_id,
            day,
            diary_id,
        )
    except Exception as exc:
        logger.warning("Digest refresh enqueue failed: %s %s %s", user_id, day, exc)
        with _in_flight_lock:
            _in_flight.discard(key)
        return None


def _release_in_flight(user_id: str, day: str) -> None:
    """Release the in-flight key — called by the worker when its run ends.

    The key intentionally lives from *schedule* until *worker completion*
    (not just enqueue): a second diary saved while the worker is running
    would produce a stale aggregate. The safety valve is that stale keys
    block only digest rebuilds, never user flows, and the next write on a
    later day (or process restart) clears the state.
    """
    with _in_flight_lock:
        _in_flight.discard((user_id, day))


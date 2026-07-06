"""MemoryGateway — unified read/write entry point for both conversation scenes.

Scene 1 (single diary analysis) and Scene 2 (multi-turn conversation) both
delegate memory access through this gateway.  The gateway encapsulates:

* **Read**: load episodic entries (query-relevant), long-term profile, and
  working memory context in one call.
* **Write**: store episodic entries, trigger long-term promotion, and update
  working memory — all best-effort (failures are logged, never raised).

The gateway is intentionally thin: it delegates to the existing
:class:`EpisodicMemory`, :class:`LongTermMemory`, and :class:`WorkingMemory`
without adding a new persistence layer.  Its value is **contract consolidation**:
both scenes call the same methods, so memory access patterns stay consistent
and testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from app.domain.memory.atom import UnifiedMemoryAtom
from app.domain.memory.types import EpisodicEntry
from app.shared.pipeline_trace import trace_span

if TYPE_CHECKING:
    from app.domain.memory.episodic import EpisodicMemory
    from app.domain.memory.long_term import LongTermMemory
    from app.domain.memory.working import WorkingMemory
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)


class SessionType(StrEnum):
    """Distinguishes the two conversation scenarios."""

    DIARY = "diary"  # Scene 1: single diary, single analysis turn
    CHAT = "chat"  # Scene 2: multi-turn conversation


@dataclass(frozen=True, slots=True)
class LoadedMemory:
    """Read result: everything a session needs from the memory stack."""

    episodic_context: list[dict[str, Any]] = field(default_factory=list)
    profile: dict[str, Any] = field(default_factory=dict)
    profile_style: str = ""
    profile_topics: list[str] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)


class MemoryGateway:
    """Unified memory read/write facade for both conversation scenes."""

    def __init__(
        self,
        episodic: EpisodicMemory | None = None,
        long_term: LongTermMemory | None = None,
        working: WorkingMemory | None = None,
    ) -> None:
        self._episodic = episodic
        self._long_term = long_term
        self._working = working

    # ──────────────── Read ────────────────

    def load(
        self,
        *,
        query: str,
        session_type: SessionType,
        top_k: int = 5,
        user_id: str = "default",
    ) -> LoadedMemory:
        """Load episodic entries + long-term profile in one call.

        *query* is always passed to :meth:`retrieve_relevant` so the relevance
        boost from the char-Jaccard fix (Task 1) actually fires.
        """
        episodic_context: list[dict[str, Any]] = []
        memory_ids: list[str] = []
        profile: dict[str, Any] = {}
        profile_style = ""
        profile_topics: list[str] = []

        if self._episodic is not None:
            try:
                entries = self._episodic.retrieve_relevant(query=query, top_k=top_k)
                episodic_context = [
                    {
                        "event_summary": e.event_summary,
                        "emotion": e.emotion,
                        "reply_insight": e.reply_insight,
                        "timestamp": e.timestamp,
                        "tags": e.tags,
                        "mood_score": e.mood_score,
                        "source": e.source,
                    }
                    for e in entries
                ]
                memory_ids = [e.entry_id for e in entries if e.entry_id]
            except Exception as exc:
                logger.warning("MemoryGateway: episodic load failed: %s", exc)

        if self._long_term is not None:
            try:
                p = self._long_term.get_profile(user_id)
                profile = p.model_dump()
                profile_style = p.preferred_response_style or ""
                profile_topics = list(p.recurring_topics or [])
            except Exception as exc:
                logger.warning("MemoryGateway: long-term load failed: %s", exc)

        return LoadedMemory(
            episodic_context=episodic_context,
            profile=profile,
            profile_style=profile_style,
            profile_topics=profile_topics,
            memory_ids=memory_ids,
        )

    # ──────────────── Write ────────────────

    def persist_episodic(
        self,
        *,
        event_summary: str,
        emotion: str,
        reply_insight: str = "",
        source: str = "diary",
        diary_ids: list[str] | None = None,
        importance: float = 0.5,
        user_id: str = "default",
        tags: list[str] | None = None,
        mood_score: float = 0.5,
        emotions: list[str] | None = None,
        event_date: str | None = None,
    ) -> bool:
        """Store an episodic entry and trigger long-term promotion.

        Returns ``True`` if the entry was stored, ``False`` if it was below
        threshold or memory is unavailable.  Never raises.
        """
        if self._episodic is None:
            logger.debug("MemoryGateway: episodic unavailable, skip store")
            return False

        # ── Dirty memory prevention gate (P2-8) ──
        from app.domain.memory.gate import should_persist

        with trace_span(
            "S8_memory_check",
            "记忆四维检查",
            input_snapshot={
                "emotion": emotion,
                "mood_score": mood_score,
                "importance": importance,
            },
        ) as span:
            existing = self._episodic.get_entries() if self._episodic else []
            should = should_persist(
                event_summary=event_summary,
                emotion=emotion,
                mood_score=mood_score,
                importance=importance,
                content=event_summary,
                existing_entries=existing,
            )
            if span:
                span.set_output({"should_persist": should})

        if not should:
            logger.debug(
                "Memory gate rejected write: source=%s summary=%s", source, event_summary[:50]
            )
            return False

        with trace_span(
            "S9_memory_write",
            "记忆写入",
            input_snapshot={"source": source, "event_summary": event_summary[:50]},
        ) as span:
            entry = EpisodicEntry(
                event_summary=event_summary[:121],
                emotion=emotion,
                reply_insight=reply_insight[:200],
                source=source,
                timestamp=datetime.now(UTC).timestamp(),
                diary_ids=diary_ids or [],
                importance=importance,
                entry_id="",
                tags=tags or [],
                mood_score=mood_score,
                emotions=emotions or [],
                event_date=event_date,
            )

            try:
                stored = self._episodic.store(entry)
                if not stored:
                    if span:
                        span.set_output({"stored": False})
                    logger.debug("MemoryGateway: entry below threshold, not stored")
                    return False
            except Exception as exc:
                if span:
                    span.set_output({"stored": False, "error": str(exc)})
                logger.warning("MemoryGateway: episodic store failed: %s", exc)
                return False

            # Best-effort long-term promotion.
            if self._long_term is not None:
                try:
                    all_entries = self._episodic.get_entries()
                    self._long_term.promote_from_episodic(user_id=user_id, episodic_entries=all_entries)
                except Exception as exc:
                    logger.warning("MemoryGateway: profile promotion failed: %s", exc)

            if span:
                span.set_output({"stored": True})
            return True

    def persist_atom(self, atom: UnifiedMemoryAtom) -> bool:
        """Persist a :class:`UnifiedMemoryAtom` to episodic memory.

        This is the preferred write path for all three content sources.
        It converts the atom to an ``EpisodicEntry`` with structured fields
        and delegates to :meth:`persist_episodic`.
        """
        return self.persist_episodic(
            event_summary=atom.event_summary,
            emotion=atom.emotion,
            reply_insight=atom.reply_insight,
            source=atom.source,
            diary_ids=[str(atom.diary_id)] if atom.diary_id else [],
            importance=atom.importance,
            user_id=atom.user_id,
            tags=atom.tags,
            mood_score=atom.mood_score,
            emotions=atom.emotions,
            event_date=atom.event_date.isoformat() if atom.event_date else None,
        )

    @staticmethod
    def from_container(container: ServiceContainer) -> MemoryGateway:
        """Create a gateway from the service container."""
        return MemoryGateway(
            episodic=getattr(container, "episodic_memory", None),
            long_term=getattr(container, "long_term_memory", None),
            working=getattr(container, "working_memory", None),
        )


__all__ = ["LoadedMemory", "MemoryGateway", "SessionType", "UnifiedMemoryAtom"]

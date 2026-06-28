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

from app.domain.memory.types import EpisodicEntry

if TYPE_CHECKING:
    from app.domain.memory.episodic import EpisodicMemory
    from app.domain.memory.long_term import LongTermMemory
    from app.domain.memory.working import WorkingMemory
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)


class SessionType(StrEnum):
    """Distinguishes the two conversation scenarios."""

    DIARY = "diary"   # Scene 1: single diary, single analysis turn
    CHAT = "chat"     # Scene 2: multi-turn conversation


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
                        "event": e.event,
                        "emotion": e.emotion,
                        "ai_suggestion": e.ai_suggestion,
                        "timestamp": e.timestamp,
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
        event: str,
        emotion: str,
        ai_suggestion: str = "",
        diary_ids: list[str] | None = None,
        importance: float = 0.5,
        user_id: str = "default",
    ) -> bool:
        """Store an episodic entry and trigger long-term promotion.

        Returns ``True`` if the entry was stored, ``False`` if it was below
        threshold or memory is unavailable.  Never raises.
        """
        if self._episodic is None:
            logger.debug("MemoryGateway: episodic unavailable, skip store")
            return False

        entry = EpisodicEntry(
            event=event[:120],
            emotion=emotion,
            ai_suggestion=ai_suggestion[:200],
            user_feedback="none",
            timestamp=datetime.now(UTC).timestamp(),
            diary_ids=diary_ids or [],
            importance=importance,
            entry_id="",
        )

        try:
            stored = self._episodic.store(entry)
            if not stored:
                logger.debug("MemoryGateway: entry below threshold, not stored")
                return False
        except Exception as exc:
            logger.warning("MemoryGateway: episodic store failed: %s", exc)
            return False

        # Best-effort long-term promotion.
        if self._long_term is not None:
            try:
                all_entries = list(self._episodic._entries)
                self._long_term.promote_from_episodic(user_id=user_id, episodic_entries=all_entries)
            except Exception as exc:
                logger.warning("MemoryGateway: profile promotion failed: %s", exc)

        return True

    @staticmethod
    def from_container(container: ServiceContainer) -> MemoryGateway:
        """Create a gateway from the service container."""
        return MemoryGateway(
            episodic=getattr(container, "episodic_memory", None),
            long_term=getattr(container, "long_term_memory", None),
            working=getattr(container, "working_memory", None),
        )


__all__ = ["LoadedMemory", "MemoryGateway", "SessionType"]

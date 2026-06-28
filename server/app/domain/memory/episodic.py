"""Episodic memory — in-process deque with optional SQLite persistence.

Example::

    from app.infrastructure.database import create_db_engine, create_session_factory, init_db
    from app.infrastructure.memory_repository import SqliteEpisodicMemoryStore
    from app.domain.memory.episodic import EpisodicMemory
    from app.domain.memory.types import EpisodicEntry

    engine = create_db_engine("sqlite:////tmp/night-diary-test/episodic.db")
    init_db(engine)
    store = SqliteEpisodicMemoryStore(create_session_factory(engine))
    memory = EpisodicMemory(store=store, user_id="default")
    memory.load()

    entry = EpisodicEntry(
        event="失眠",
        emotion="焦虑",
        ai_suggestion="尝试放松呼吸",
        timestamp=time.time(),
        importance=0.8,
        diary_ids=["d01"],
    )
    memory.store(entry)
    hits = memory.retrieve_relevant(query="睡眠", top_k=3)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from collections.abc import Callable

from app.domain.memory.types import EpisodicEntry, EpisodicMemoryStore

logger = logging.getLogger(__name__)

SimilarityFn = Callable[[str, str], float]

#: Weight of query relevance when blending with importance * decay.
#: final_score = time_score * (1.0 + relevance * RELEVANCE_WEIGHT)
#: At 1.0, a perfectly relevant entry doubles its base score -- enough to
#: overcome a moderate importance gap (e.g. 0.6 relevant > 0.7 irrelevant)
#: while still preserving the importance-decay ordering when relevance is 0.
RELEVANCE_WEIGHT = 1.0


def char_jaccard(left: str, right: str) -> float:
    """Character-level Jaccard overlap for short Chinese text.

    Episodic ``event`` labels are typically 2-4 characters ("失眠", "加班").
    Word-level jieba tokenisation treats these as single tokens, yielding zero
    overlap between semantically related labels like "失眠" and "睡眠".
    Character-level matching catches the shared "眠" character.
    """
    left_chars = {c for c in left if c.strip()}
    right_chars = {c for c in right if c.strip()}
    if not left_chars or not right_chars:
        return 0.0
    intersection = left_chars & right_chars
    union = left_chars | right_chars
    return len(intersection) / len(union)


class EpisodicMemory:
    """Process-local episodic memory backed by ``deque`` with SQLite persistence."""

    MAX_ENTRIES = 100
    IMPORTANCE_THRESHOLD = 0.5
    DECAY_HALF_LIFE = 7 * 24 * 3600

    def __init__(
        self,
        *,
        store: EpisodicMemoryStore | None = None,
        user_id: str = "default",
        persist: bool = True,
        similarity: SimilarityFn | None = None,
    ) -> None:
        self._store = store
        self._user_id = user_id
        self._persist = persist and store is not None
        self._entries: deque[EpisodicEntry] = deque()
        # Lazy import to avoid jieba load cost when no query is ever passed.
        self._similarity = similarity

    def load(self) -> None:
        """Load persisted entries into the in-process deque."""
        if self._store is None:
            return

        loaded = self._store.load_entries(self._user_id)
        self._entries.clear()
        for entry in loaded:
            if self._effective_score(entry, time.time()) >= self.IMPORTANCE_THRESHOLD:
                self._entries.append(entry)
        self._enforce_capacity()

    def store(self, entry: EpisodicEntry) -> bool:
        """Store an episodic entry when importance exceeds the threshold."""
        if entry.importance <= self.IMPORTANCE_THRESHOLD:
            logger.debug(
                "Skip episodic store: importance=%.2f <= %.2f",
                entry.importance,
                self.IMPORTANCE_THRESHOLD,
            )
            return False

        if not entry.entry_id:
            entry = entry.model_copy(update={"entry_id": uuid.uuid4().hex})

        self._entries.append(entry)
        self.upsert(entry)
        self._enforce_capacity()
        return True

    def upsert(self, entry: EpisodicEntry) -> None:
        """Persist a single entry to SQLite."""
        if not self._persist or self._store is None:
            return
        self._store.upsert_entry(self._user_id, entry)

    def retrieve_relevant(
        self,
        query: str = "",
        top_k: int = 5,
        now: float | None = None,
    ) -> list[EpisodicEntry]:
        """Return top entries ranked by importance * decay, boosted by query relevance.

        When *query* is non-empty, entries whose ``event`` text overlaps with the
        query receive a multiplicative boost (up to ``1 + RELEVANCE_WEIGHT``).
        Entries that don't overlap keep their base score, so relevance affects
        ranking order but never lowers a qualified entry below its natural
        importance-decay position.
        """
        if now is None:
            now = time.time()

        self.purge_stale(now=now)

        use_relevance = bool(query and query.strip())
        sim_fn = self._resolve_similarity() if use_relevance else None

        scored: list[tuple[float, EpisodicEntry]] = []
        for entry in self._entries:
            base = self._effective_score(entry, now)
            if base < self.IMPORTANCE_THRESHOLD:
                continue
            final = base
            if sim_fn is not None:
                relevance = sim_fn(query, entry.event)
                final = base * (1.0 + relevance * RELEVANCE_WEIGHT)
            scored.append((final, entry))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def _resolve_similarity(self) -> SimilarityFn:
        """Return the configured similarity function, defaulting to char Jaccard."""
        if self._similarity is not None:
            return self._similarity
        return char_jaccard

    def evict_lowest(self, now: float | None = None) -> int:
        """Evict stale entries and enforce the LRU capacity limit."""
        if now is None:
            now = time.time()

        removed = self.purge_stale(now=now)
        removed += self._enforce_capacity()
        return removed

    def purge_stale(self, now: float | None = None) -> int:
        """Remove entries whose effective score dropped below the threshold."""
        if now is None:
            now = time.time()

        stale_ids: list[str] = []
        kept: deque[EpisodicEntry] = deque()
        for entry in self._entries:
            if self._effective_score(entry, now) >= self.IMPORTANCE_THRESHOLD:
                kept.append(entry)
            elif entry.entry_id:
                stale_ids.append(entry.entry_id)

        removed = len(self._entries) - len(kept)
        self._entries = kept

        if stale_ids and self._persist and self._store is not None:
            self._store.delete_entries(self._user_id, stale_ids)

        return removed

    def _compute_decay(self, timestamp: float, now: float) -> float:
        elapsed = max(0.0, now - timestamp)
        return float(0.5 ** (elapsed / self.DECAY_HALF_LIFE))

    def _effective_score(self, entry: EpisodicEntry, now: float) -> float:
        return entry.importance * self._compute_decay(entry.timestamp, now)

    def _enforce_capacity(self) -> int:
        removed = 0
        while len(self._entries) > self.MAX_ENTRIES:
            oldest = min(
                self._entries,
                key=lambda entry: (entry.timestamp, entry.entry_id),
            )
            self._entries.remove(oldest)
            removed += 1
            if oldest.entry_id and self._persist and self._store is not None:
                self._store.delete_entries(self._user_id, [oldest.entry_id])

        if removed:
            logger.info(
                "Episodic LRU eviction: removed=%d remaining=%d user_id=%s",
                removed,
                len(self._entries),
                self._user_id,
            )
        return removed

    @property
    def size(self) -> int:
        return len(self._entries)

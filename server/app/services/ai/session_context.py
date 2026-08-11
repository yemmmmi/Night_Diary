"""SessionContext — conversation-level state management for scene 2.

Replaces the previous pattern of reloading full chat history from DB on every
turn. Instead, SessionContext maintains a compressed sliding window that grows
across turns and is automatically trimmed when it exceeds the token budget.

A process-level registry (:func:`get_or_create`) caches active sessions by
``conversation_id`` so repeated turns hit memory, not the DB.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.domain.agents.context_compressor import ContextCompressor
from app.shared.token_utils import estimate_tokens

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

#: Maximum tokens for the compressed chat history window.
MAX_HISTORY_TOKENS = 1200

#: Messages shorter than this are not worth compressing individually.
MIN_MESSAGE_LENGTH = 20


@dataclass
class UsageAccumulator:
    """Accumulates token usage across turns within a session."""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0
    turn_count: int = 0

    def add(self, token_info: dict[str, int]) -> None:
        self.total_tokens += int(token_info.get("total_tokens_used", 0))
        self.prompt_tokens += int(token_info.get("prompt_tokens", 0))
        self.completion_tokens += int(token_info.get("completion_tokens", 0))
        self.cache_hit_tokens += int(token_info.get("cache_hit_tokens", 0))
        self.turn_count += 1

    def summary(self) -> dict[str, int]:
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cache_hit_tokens": self.cache_hit_tokens,
            "turn_count": self.turn_count,
        }


@dataclass
class SessionContext:
    """Per-conversation state held in memory across turns.

    Attributes:
        conversation_id: The conversation this context belongs to.
        compressed_history: Sliding-window compressed chat history.
        profile_style: Cached preferred_response_style from long-term profile.
        profile_topics: Cached recurring_topics from long-term profile.
        usage: Token usage accumulator across all turns.
        pinned_diary_ids: Diary entries pinned for this session.
    """

    conversation_id: str
    compressed_history: str = ""
    profile_style: str = ""
    profile_topics: list[str] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)
    pinned_diary_ids: list[int] = field(default_factory=list)
    _turn_messages: list[dict[str, str]] = field(default_factory=list)

    def add_turn(self, user_message: str, reply: str) -> None:
        """Append a user+assistant turn and compress if over budget."""
        self._turn_messages.append({"role": "user", "content": user_message})
        self._turn_messages.append({"role": "assistant", "content": reply})

        # Build raw history text
        raw = self._format_raw_history()
        tokens = estimate_tokens(raw)

        if tokens > MAX_HISTORY_TOKENS:
            self._compress_history(raw)
        else:
            self.compressed_history = raw

        self._persist_to_l2()

    def get_history(self) -> str:
        """Return the current compressed history (or raw if short enough)."""
        if self.compressed_history:
            return self.compressed_history
        if self._turn_messages:
            return self._format_raw_history()
        return "（暂无历史）"

    def accumulate_usage(self, token_info: dict[str, int]) -> None:
        """Add this turn's token usage to the session accumulator."""
        self.usage.add(token_info)
        self._persist_to_l2()

    def to_snapshot(self) -> dict[str, Any]:
        """Serialize session state for Redis persistence (L2 cache)."""
        return {
            "conversation_id": self.conversation_id,
            "compressed_history": self.compressed_history,
            "profile_style": self.profile_style,
            "profile_topics": list(self.profile_topics),
            "usage": self.usage.summary(),
            "pinned_diary_ids": list(self.pinned_diary_ids),
            # Only keep recent turn messages (older ones are in compressed_history)
            "turn_messages": list(self._turn_messages[-20:]),
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> SessionContext:
        """Reconstruct a SessionContext from a Redis snapshot."""
        ctx = cls(
            conversation_id=data.get("conversation_id", ""),
            compressed_history=data.get("compressed_history", ""),
            profile_style=data.get("profile_style", ""),
            profile_topics=list(data.get("profile_topics", [])),
            pinned_diary_ids=list(data.get("pinned_diary_ids", [])),
        )
        usage_data = data.get("usage", {})
        ctx.usage = UsageAccumulator(
            total_tokens=usage_data.get("total_tokens", 0),
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            cache_hit_tokens=usage_data.get("cache_hit_tokens", 0),
            turn_count=usage_data.get("turn_count", 0),
        )
        ctx._turn_messages = list(data.get("turn_messages", []))
        return ctx

    def _persist_to_l2(self) -> None:
        """Best-effort persist snapshot to Redis (L2). Called after state mutations."""
        try:
            from app.infrastructure.redis_client import cache_set

            cache_set(
                _session_key(self.conversation_id),
                self.to_snapshot(),
                ttl_seconds=_SESSION_TTL_SECONDS,
            )
        except Exception as exc:
            logger.debug("SessionContext L2 persist failed (best-effort): %s", exc)

    def _format_raw_history(self) -> str:
        lines: list[str] = []
        for msg in self._turn_messages:
            role = "用户" if msg["role"] == "user" else "回信者"
            content = msg["content"].strip().replace("\n", " ")
            lines.append(f"{role}：{content}")
        return "\n".join(lines)

    def _compress_history(self, raw: str) -> None:
        """Use ContextCompressor to rank and compress history by relevance.

        P2-9 upgrade: sliding window + layered summary.
        - Keep the most recent 2 turns verbatim (sliding window)
        - Compress older turns via ContextCompressor (layered summary)
        - If compression still exceeds budget, overflow oldest entries
          to episodic memory via MemoryGateway (best-effort)
        """
        try:
            # ── Sliding window: keep last 2 turns verbatim ──
            recent_turns = self._turn_messages[-4:]  # last 2 turns (user+reply each)
            older_turns = self._turn_messages[:-4]

            recent_text = "\n".join(
                f"{'用户' if m['role'] == 'user' else '回信者'}：{m['content'].strip()}"
                for m in recent_turns
            )

            if not older_turns:
                # Only recent turns — still might be long, truncate
                self.compressed_history = recent_text[: MAX_HISTORY_TOKENS * 2]
                return

            # ── Layered summary: compress older turns ──
            compressor = ContextCompressor(max_tokens=MAX_HISTORY_TOKENS)
            recent_query = ""
            for msg in reversed(self._turn_messages):
                if msg["role"] == "user":
                    recent_query = msg["content"]
                    break

            older_candidates = [
                {"content": f"{'用户' if m['role'] == 'user' else '回信者'}：{m['content']}"}
                for m in older_turns
            ]
            compressed_older = compressor.compress(recent_query, candidates=older_candidates)

            # Combine: compressed older + verbatim recent
            combined_parts: list[str] = []
            if compressed_older:
                combined_parts.append("【较早对话摘要】\n" + compressed_older)
            combined_parts.append("【最近对话】\n" + recent_text)
            self.compressed_history = "\n\n".join(combined_parts)

            # ── Episodic overflow: if still too long, overflow to memory ──
            combined_tokens = estimate_tokens(self.compressed_history)
            if combined_tokens > MAX_HISTORY_TOKENS and older_turns:
                self._overflow_to_episodic(older_turns)
                # Truncate to budget
                self.compressed_history = self.compressed_history[: MAX_HISTORY_TOKENS * 2]

            logger.debug(
                "SessionContext history compressed: %d turns → %d tokens (recent=%d, older=%d)",
                len(self._turn_messages),
                estimate_tokens(self.compressed_history),
                len(recent_turns),
                len(older_turns),
            )
        except Exception as exc:
            logger.warning("SessionContext compression failed: %s", exc)
            # Fallback: keep last N messages truncated
            self.compressed_history = self._format_raw_history()

    def _overflow_to_episodic(self, overflow_messages: list[dict[str, str]]) -> None:
        """Best-effort: overflow old conversation turns to episodic memory.

        This prevents information loss when the sliding window compresses
        away older turns. Only user messages with emotional signal are
        persisted — assistant replies are not stored.
        """
        try:
            # Access the container's memory gateway if available
            # This is a best-effort operation — if no container is attached,
            # we simply skip the overflow.
            container = getattr(self, "_container", None)
            if container is None or not hasattr(container, "episodic_memory"):
                return
            if container.episodic_memory is None:
                return

            from app.services.memory_gateway import MemoryGateway
            from app.shared.emotion_estimator import get_emotion_estimator

            gw = MemoryGateway.from_container(container)
            estimator = get_emotion_estimator()

            for msg in overflow_messages:
                if msg["role"] != "user":
                    continue
                content = msg["content"].strip()
                if len(content) < 10:
                    continue

                estimate = estimator.estimate(content)
                score = estimator.score(content)
                if abs(score) < 0.2:
                    continue  # Skip low-signal messages

                gw.persist_episodic(
                    event_summary=content[:50],
                    emotion=estimate.label,
                    reply_insight="",
                    source="chat",
                    importance=min(abs(score) + 0.2, 1.0),
                    mood_score=max(0.0, min(1.0, 0.5 + score * 0.5)),
                )
        except Exception as exc:
            logger.debug("Episodic overflow failed (best-effort): %s", exc)


# ── Process-level session registry (LRU) ───────────────────────────────
#
# ``_sessions`` is an LRU cache: an :class:`~collections.OrderedDict` ordered
# from least-recently-used (front) to most-recently-used (back). When the cache
# exceeds :data:`MAX_SESSIONS`, the LRU entry is evicted. Evicted entries can
# still be restored from the L2 Redis snapshot on the next access, so no extra
# resource cleanup is required here.

#: Maximum number of sessions held in L1 memory before LRU eviction kicks in.
MAX_SESSIONS = 32

_sessions: OrderedDict[str, SessionContext] = OrderedDict()

#: Redis key prefix for session snapshots.
_SESSION_KEY_PREFIX = "session:"
#: TTL for session snapshots (30 minutes).
_SESSION_TTL_SECONDS = 1800

#: L1 cache hit counter (for observability via :func:`get_session_cache_stats`).
_hits = 0
#: L1 cache miss counter (L2 restore or create-new paths).
_misses = 0


def _session_key(conversation_id: str) -> str:
    return f"{_SESSION_KEY_PREFIX}{conversation_id}"


def _evict_lru_if_needed() -> None:
    """Evict the least-recently-used session when the cache is over capacity."""
    while len(_sessions) > MAX_SESSIONS:
        evicted_id, _ = _sessions.popitem(last=False)
        logger.debug(
            "SessionContext LRU evicted (size>%d): conversation=%s",
            MAX_SESSIONS,
            evicted_id,
        )


def get_or_create_session(
    conversation_id: str,
    *,
    container: ServiceContainer | None = None,
    user_id: str = "default",
) -> SessionContext:
    """Get the cached SessionContext for *conversation_id*, or create one.

    Lookup order: L1 memory → L2 Redis → create new.
    When *container* is provided and the session is new, the long-term profile
    is loaded eagerly so it's cached for the session lifetime.

    The L1 cache is LRU: a hit promotes the entry to the most-recently-used
    position, and inserting a new entry evicts the least-recently-used one when
    the cache exceeds :data:`MAX_SESSIONS`.
    """
    global _hits, _misses

    # L1: in-memory (hit → promote to MRU end)
    ctx = _sessions.get(conversation_id)
    if ctx is not None:
        _hits += 1
        _sessions.move_to_end(conversation_id)
        return ctx

    # Anything beyond here is a miss (L2 restore or create-new).
    _misses += 1

    # L2: Redis
    from app.infrastructure.redis_client import cache_get, cache_set

    snapshot = cache_get(_session_key(conversation_id))
    if snapshot is not None:
        ctx = SessionContext.from_snapshot(snapshot)
        _sessions[conversation_id] = ctx  # promote to L1
        _evict_lru_if_needed()
        logger.debug("SessionContext restored from Redis: conversation=%s", conversation_id)
        return ctx

    # Create new
    ctx = SessionContext(conversation_id=conversation_id)

    # Eagerly load profile snapshot for new sessions
    if container is not None and container.long_term_memory is not None:
        try:
            profile = container.long_term_memory.get_profile(user_id)
            ctx.profile_style = profile.preferred_response_style or ""
            ctx.profile_topics = list(profile.recurring_topics or [])
        except Exception as exc:
            logger.warning("SessionContext profile load failed: %s", exc)

    _sessions[conversation_id] = ctx  # L1
    _evict_lru_if_needed()
    cache_set(
        _session_key(conversation_id), ctx.to_snapshot(), ttl_seconds=_SESSION_TTL_SECONDS
    )  # L2
    logger.debug("SessionContext created for conversation=%s", conversation_id)
    return ctx


def clear_session(conversation_id: str) -> None:
    """Remove a session from L1 memory and L2 Redis."""
    _sessions.pop(conversation_id, None)
    from app.infrastructure.redis_client import cache_delete

    cache_delete(_session_key(conversation_id))


def get_active_session_count() -> int:
    """Return the number of active sessions (for diagnostics)."""
    return len(_sessions)


def get_session_cache_stats() -> dict[str, int | float]:
    """Return L1 cache observability counters.

    Returns a dict with:

    - ``hits``/``misses``: cumulative L1 hit and miss counts.
    - ``size``: current number of sessions in L1 memory.
    - ``maxsize``: the configured :data:`MAX_SESSIONS` cap.
    - ``hit_rate``: ``hits / (hits + misses)``, or ``0.0`` when no traffic.
    """
    total = _hits + _misses
    return {
        "hits": _hits,
        "misses": _misses,
        "size": len(_sessions),
        "maxsize": MAX_SESSIONS,
        "hit_rate": _hits / total if total > 0 else 0.0,
    }


__all__ = [
    "MAX_HISTORY_TOKENS",
    "MAX_SESSIONS",
    "SessionContext",
    "UsageAccumulator",
    "clear_session",
    "get_active_session_count",
    "get_or_create_session",
    "get_session_cache_stats",
]

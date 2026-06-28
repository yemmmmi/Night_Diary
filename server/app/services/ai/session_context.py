"""SessionContext — conversation-level state management for scene 2.

Replaces the previous pattern of reloading full chat history from DB on every
turn. Instead, SessionContext maintains a compressed sliding window that grows
across turns and is automatically trimmed when it exceeds the token budget.

A process-level registry (:func:`get_or_create`) caches active sessions by
``conversation_id`` so repeated turns hit memory, not the DB.
"""

from __future__ import annotations

import logging
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

    def _format_raw_history(self) -> str:
        lines: list[str] = []
        for msg in self._turn_messages:
            role = "用户" if msg["role"] == "user" else "回信者"
            content = msg["content"].strip().replace("\n", " ")
            lines.append(f"{role}：{content}")
        return "\n".join(lines)

    def _compress_history(self, raw: str) -> None:
        """Use ContextCompressor to rank and compress history by relevance."""
        try:
            compressor = ContextCompressor(max_tokens=MAX_HISTORY_TOKENS)
            # The most recent user message is the "query" for relevance ranking
            recent_query = ""
            for msg in reversed(self._turn_messages):
                if msg["role"] == "user":
                    recent_query = msg["content"]
                    break

            candidates = [
                {"content": f"{m['role']}：{m['content']}"}
                for m in self._turn_messages
            ]
            compressed = compressor.compress(recent_query, candidates=candidates)
            self.compressed_history = compressed or raw[: MAX_HISTORY_TOKENS * 2]
            logger.debug(
                "SessionContext history compressed: %d turns → %d tokens",
                len(self._turn_messages),
                estimate_tokens(self.compressed_history),
            )
        except Exception as exc:
            logger.warning("SessionContext compression failed: %s", exc)
            # Fallback: keep last N messages truncated
            self.compressed_history = self._format_raw_history()


# ── Process-level session registry ──────────────────────────────────────

_sessions: dict[str, SessionContext] = {}


def get_or_create_session(
    conversation_id: str,
    *,
    container: ServiceContainer | None = None,
) -> SessionContext:
    """Get the cached SessionContext for *conversation_id*, or create one.

    When *container* is provided and the session is new, the long-term profile
    is loaded eagerly so it's cached for the session lifetime.
    """
    ctx = _sessions.get(conversation_id)
    if ctx is not None:
        return ctx

    ctx = SessionContext(conversation_id=conversation_id)

    # Eagerly load profile snapshot for new sessions
    if container is not None and container.long_term_memory is not None:
        try:
            profile = container.long_term_memory.get_profile("default")
            ctx.profile_style = profile.preferred_response_style or ""
            ctx.profile_topics = list(profile.recurring_topics or [])
        except Exception as exc:
            logger.warning("SessionContext profile load failed: %s", exc)

    _sessions[conversation_id] = ctx
    logger.debug("SessionContext created for conversation=%s", conversation_id)
    return ctx


def clear_session(conversation_id: str) -> None:
    """Remove a session from the registry (e.g. on conversation delete)."""
    _sessions.pop(conversation_id, None)


def get_active_session_count() -> int:
    """Return the number of active sessions (for diagnostics)."""
    return len(_sessions)


__all__ = [
    "MAX_HISTORY_TOKENS",
    "SessionContext",
    "UsageAccumulator",
    "clear_session",
    "get_active_session_count",
    "get_or_create_session",
]

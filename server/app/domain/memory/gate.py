"""Dirty memory prevention — four-dimensional gate for episodic writes.

Prevents low-quality or harmful memories from entering episodic storage.
Each write passes through four gates:

1. **Emotional significance**: Skip entries with near-zero emotional signal
   (bland logs like "今天吃了饭" don't deserve memory slots).
2. **Content validity**: Reject empty, whitespace-only, or absurdly short
   inputs that would produce meaningless event summaries.
3. **Crisis contamination**: Don't persist raw crisis content — the crisis
   response is safety-critical and should not be replayed as a "memory"
   in future contexts. Crisis signals are handled separately by CrisisGuard.
4. **Deduplication**: Reject near-duplicates of entries already in the
   deque (same event_summary within a time window).

The gate is designed to be cheap (no LLM calls) and fast (O(1) or O(n)
with small n). It runs before MemoryGateway.persist_episodic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.memory.types import EpisodicEntry

logger = logging.getLogger(__name__)

# ── Gate thresholds ──────────────────────────────────────────────────

_MIN_EVENT_SUMMARY_LEN = 3
_MIN_EMOTIONAL_SIGNAL = 0.15  # abs(mood_score - 0.5) must exceed this
_DEDUP_WINDOW_HOURS = 24
_DEDUP_SIMILARITY_THRESHOLD = 0.85  # char Jaccard threshold for dedup

# Crisis keywords that should not be persisted as episodic memories
_CRISIS_KEYWORDS = frozenset({
    "不想活", "自杀", "结束生命", "活不下去", "想死",
    "杀了", "伤害自己", "了结", "跳楼", "吃药结束",
})


@dataclass
class GateResult:
    """Result of the four-dimensional memory gate."""

    passed: bool
    reason: str = ""
    gate_name: str = ""


def _char_jaccard(a: str, b: str) -> float:
    """Character-level Jaccard similarity (handles short Chinese text well)."""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def check_memory_gate(
    event_summary: str,
    emotion: str,
    mood_score: float,
    importance: float,
    content: str = "",
    existing_entries: list[EpisodicEntry] | None = None,
) -> GateResult:
    """Run the four-dimensional gate on a proposed episodic write.

    Args:
        event_summary: The proposed event summary.
        emotion: The emotion label.
        mood_score: The mood score (0.0-1.0).
        importance: The importance score (0.0-1.0).
        content: The original content (for crisis detection).
        existing_entries: Recent entries for deduplication check.

    Returns:
        GateResult indicating whether the write should proceed.
    """
    # ── Gate 1: Content validity ──
    if not event_summary or len(event_summary.strip()) < _MIN_EVENT_SUMMARY_LEN:
        return GateResult(
            passed=False,
            reason=f"Event summary too short (<{_MIN_EVENT_SUMMARY_LEN} chars)",
            gate_name="content_validity",
        )

    # ── Gate 2: Crisis contamination ──
    check_text = (content or event_summary).lower()
    for keyword in _CRISIS_KEYWORDS:
        if keyword in check_text:
            return GateResult(
                passed=False,
                reason=f"Crisis keyword detected: {keyword}",
                gate_name="crisis_contamination",
            )

    # ── Gate 3: Emotional significance ──
    emotional_signal = abs(mood_score - 0.5)
    if emotional_signal < _MIN_EMOTIONAL_SIGNAL and importance < 0.4:
        return GateResult(
            passed=False,
            reason=f"Low emotional signal ({emotional_signal:.3f} < {_MIN_EMOTIONAL_SIGNAL}) and low importance ({importance:.2f} < 0.4)",
            gate_name="emotional_significance",
        )

    # ── Gate 4: Deduplication ──
    if existing_entries:
        now = datetime.now(UTC).timestamp()
        window_start = now - timedelta(hours=_DEDUP_WINDOW_HOURS).total_seconds()
        for entry in existing_entries:
            if entry.timestamp < window_start:
                continue
            similarity = _char_jaccard(event_summary, entry.event_summary)
            if similarity >= _DEDUP_SIMILARITY_THRESHOLD:
                return GateResult(
                    passed=False,
                    reason=f"Near-duplicate of existing entry (similarity={similarity:.2f})",
                    gate_name="deduplication",
                )

    return GateResult(passed=True)


def should_persist(
    event_summary: str,
    emotion: str,
    mood_score: float = 0.5,
    importance: float = 0.5,
    content: str = "",
    existing_entries: list[EpisodicEntry] | None = None,
) -> bool:
    """Convenience wrapper: returns True if the gate passes.

    Logs the rejection reason at debug level.
    """
    result = check_memory_gate(
        event_summary=event_summary,
        emotion=emotion,
        mood_score=mood_score,
        importance=importance,
        content=content,
        existing_entries=existing_entries,
    )
    if not result.passed:
        logger.debug(
            "Memory gate rejected: gate=%s reason=%s summary=%s",
            result.gate_name,
            result.reason,
            event_summary[:50],
        )
    return result.passed


__all__ = [
    "GateResult",
    "check_memory_gate",
    "should_persist",
]

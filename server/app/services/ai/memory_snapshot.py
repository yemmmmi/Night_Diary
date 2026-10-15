"""Frozen memory snapshot — stable system-prompt prefix for prefix caching (D6).

Hermes injects its ``MEMORY.md`` / ``USER.md`` notes into the system prompt as a
*frozen snapshot*: assembled once at session start and kept byte-identical for
the whole session so the provider's automatic prefix cache can hit. 夜记's
analog is the user's long-term profile (preferred style + recurring topics),
which was previously re-injected into the *volatile* user prompt on every turn.

This module builds that block with a hard character budget. When the profile
overflows, topics are consolidated (trimmed to the most recent
:data:`MAX_TOPICS`) and the block is truncated, so a runaway profile can never
bloat every request. The block is placed at a fixed position in the system
prompt (right after the base prompt) so the stable prefix survives across turns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.memory.types import MAX_ABOUT_CHARS, ShortTermState

#: Hard character cap for the frozen memory block.
MEMORY_BLOCK_MAX_CHARS = 1200

#: Maximum number of recurring topics kept before consolidation kicks in.
MAX_TOPICS = 8

_HEADER = "## 关于我（会话冻结快照）"


@dataclass(frozen=True, slots=True)
class MemoryBudget:
    """Capacity accounting for a frozen memory block."""

    used_chars: int
    cap_chars: int
    topic_count: int
    over_budget: bool
    consolidated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "used_chars": self.used_chars,
            "cap_chars": self.cap_chars,
            "topic_count": self.topic_count,
            "over_budget": self.over_budget,
            "consolidated": self.consolidated,
        }


@dataclass(frozen=True, slots=True)
class FrozenMemoryBlock:
    """The frozen block text plus its budget; ``text`` is empty when nothing to freeze."""

    text: str
    budget: MemoryBudget

    @property
    def empty(self) -> bool:
        return not self.text


def build_frozen_memory_block(
    *,
    profile_style: str = "",
    profile_topics: list[str] | None = None,
    user_about: str = "",
    short_term_state: ShortTermState | None = None,
    cap: int = MEMORY_BLOCK_MAX_CHARS,
) -> FrozenMemoryBlock:
    """Assemble the frozen memory block, consolidating when over budget.

    The user-authored 「关于我」 (``user_about``, B2) is placed first — it is the
    highest-signal, user-owned content, so when the block overflows it is the
    system-inferred style/topics that get trimmed first.

    ``short_term_state`` (P1-A) renders the recent mode/mood trend line; it is
    day-granular, so freezing it still keeps the block byte-stable within a
    session.
    """
    style = (profile_style or "").strip()
    about = (user_about or "").strip()
    topics = [topic.strip() for topic in (profile_topics or []) if topic and topic.strip()]

    consolidated = False
    if len(topics) > MAX_TOPICS:
        topics = topics[:MAX_TOPICS]
        consolidated = True

    lines = [_HEADER]
    if about:
        lines.append(f"- 用户自述：{about}")
    if style:
        lines.append(f"- 偏好风格：{style}")
    if topics:
        lines.append(f"- 近期关注：{'、'.join(topics)}")
    if short_term_state is not None:
        state_text = short_term_state.render()
        if state_text:
            lines.append(f"- 近期状态：{state_text}")

    if len(lines) == 1:
        return FrozenMemoryBlock(
            text="",
            budget=MemoryBudget(0, cap, 0, False, consolidated),
        )

    raw = "\n".join(lines)
    over_budget = len(raw) > cap
    text = raw
    if over_budget:
        text = raw[: max(0, cap - 1)].rstrip() + "…"
        consolidated = True

    return FrozenMemoryBlock(
        text=text,
        budget=MemoryBudget(
            used_chars=len(text),
            cap_chars=cap,
            topic_count=len(topics),
            over_budget=over_budget,
            consolidated=consolidated,
        ),
    )


__all__ = [
    "MAX_ABOUT_CHARS",
    "MEMORY_BLOCK_MAX_CHARS",
    "MAX_TOPICS",
    "FrozenMemoryBlock",
    "MemoryBudget",
    "build_frozen_memory_block",
]
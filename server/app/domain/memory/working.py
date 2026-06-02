"""Working memory — session context with token-budget enforcement.

This PR delivers the domain-level integration contract only. Supervisor /
Multi-Agent wiring lands in Phase B-9 / C-1.

Example::

    from app.domain.memory.types import UserProfile
    from app.domain.memory.working import WorkingMemory

    wm = WorkingMemory()
    ctx = wm.load_context(
        diary_id="d03",
        user_profile=UserProfile(recurring_topics=["失眠"]),
    )
    ctx = wm.update_context(
        ctx,
        {
            "retrieval_context": "你曾在 Day1 提到失眠…",
            "empathy_response": "听起来你最近睡眠还是不稳定。",
        },
    )
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from app.domain.memory.types import UserProfile, WorkingContext
from app.shared.token_utils import estimate_tokens

logger = logging.getLogger(__name__)

MAX_CONTEXT_TOKENS = 4000
_CONTEXT_FIELDS = (
    "retrieval_context",
    "empathy_response",
    "insight_response",
    "compressed_history",
)


class WorkingMemory:
    """Session-level working memory for one diary analysis turn."""

    MAX_CONTEXT_TOKENS = MAX_CONTEXT_TOKENS

    def __init__(self) -> None:
        self._context: WorkingContext | None = None

    @property
    def context(self) -> WorkingContext | None:
        if self._context is None:
            return None
        return deepcopy(self._context)

    @property
    def is_active(self) -> bool:
        return self._context is not None

    def load_context(self, diary_id: str, user_profile: UserProfile) -> WorkingContext:
        """Initialize working memory for a diary analysis session."""
        profile_dict = user_profile.model_dump()
        self._context = WorkingContext(
            diary_id=diary_id,
            diary_content="",
            user_profile=profile_dict,
            episodic_context=[],
            long_term_profile=profile_dict,
            retrieval_context="",
            empathy_response="",
            insight_response="",
            compressed_history="",
            final_response="",
            turn=0,
            total_tokens_used=0,
        )
        logger.debug("WorkingMemory initialized for diary_id=%s", diary_id)
        return deepcopy(self._context)

    def update_context(self, ctx: WorkingContext, turn_result: dict[str, Any]) -> None:
        """Merge turn output into working memory and enforce token limits."""
        merged = deepcopy(ctx)
        for key, value in turn_result.items():
            if key in _CONTEXT_FIELDS and isinstance(value, str):
                merged[key] = self._enforce_token_limit(merged, key, value)  # type: ignore[literal-required]
            else:
                merged[key] = value  # type: ignore[literal-required]

        merged["turn"] = int(merged.get("turn", 0)) + 1
        merged["total_tokens_used"] = self._context_tokens_used(merged)
        self._context = merged
        logger.debug(
            "WorkingMemory updated turn=%s tokens=%s",
            merged.get("turn"),
            merged.get("total_tokens_used"),
        )

    def get_context_tokens_used(self, ctx: WorkingContext | None = None) -> int:
        state = ctx if ctx is not None else self._context
        if state is None:
            return 0
        return self._context_tokens_used(state)

    def clear(self) -> None:
        diary_id = self._context.get("diary_id") if self._context else "unknown"
        logger.debug("WorkingMemory cleared diary_id=%s", diary_id)
        self._context = None

    def _context_tokens_used(self, ctx: WorkingContext) -> int:
        total = 0
        for field in _CONTEXT_FIELDS:
            content = ctx.get(field, "")
            if isinstance(content, str) and content:
                total += estimate_tokens(content)
        return total

    def _enforce_token_limit(
        self,
        ctx: WorkingContext,
        key: str,
        value: str,
    ) -> str:
        other_tokens = 0
        for field in _CONTEXT_FIELDS:
            if field == key:
                continue
            content = ctx.get(field, "")
            if isinstance(content, str) and content:
                other_tokens += estimate_tokens(content)

        value_tokens = estimate_tokens(value)
        if other_tokens + value_tokens <= self.MAX_CONTEXT_TOKENS:
            return value

        available_tokens = self.MAX_CONTEXT_TOKENS - other_tokens
        if available_tokens <= 0:
            logger.warning(
                "WorkingMemory token budget exhausted before writing field=%s",
                key,
            )
            return ""

        ratio = available_tokens / value_tokens
        target_len = int(len(value) * ratio * 0.9)
        truncated = value[:target_len]

        while estimate_tokens(truncated) > available_tokens and truncated:
            truncated = truncated[: int(len(truncated) * 0.9)]

        if truncated and not truncated.endswith("..."):
            truncated = truncated.rstrip() + "..."

        logger.info(
            "WorkingMemory truncated field=%s from %d to %d tokens",
            key,
            value_tokens,
            estimate_tokens(truncated),
        )
        return truncated

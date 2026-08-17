"""SafetyMiddleware — unify the crisis-response instruction across both scenes.

P0-P6 review found the crisis-response guidance existed only in scene 1's
empathy prompt (``EMPATHY_CRISIS_BLOCK`` in ``app/domain/agents/prompts.py``);
scene 2's ``CHAT_SYSTEM_PROMPT`` had none, relying entirely on the Stage-2
short-circuit and the sliding-window safety guard. This middleware injects the
same block into any system prompt that lacks it — single source of truth, so
the two scenes' crisis guidance can never drift.
"""

from __future__ import annotations

from app.domain.agents.prompts import EMPATHY_CRISIS_BLOCK
from app.shared.middleware.base import MiddlewareBase, MiddlewareContext

#: Single source of truth for the crisis-response instruction. Scene 1 keeps
#: referencing EMPATHY_CRISIS_BLOCK directly; scene 2 receives this via
#: SafetyMiddleware.on_system_prompt.
CRISIS_SYSTEM_BLOCK = EMPATHY_CRISIS_BLOCK

#: Marker used to detect an already-injected block (idempotency).
_CRISIS_MARKER = "## ⚠️ 危机响应模式"


class SafetyMiddleware(MiddlewareBase):
    """Inject the shared crisis-response block into system prompts (idempotent)."""

    name = "safety"

    def __init__(self, block: str = CRISIS_SYSTEM_BLOCK) -> None:
        self._block = block

    def on_system_prompt(self, prompt: str, ctx: MiddlewareContext) -> str:
        if _CRISIS_MARKER in prompt:
            return prompt
        return f"{prompt}\n{self._block.strip()}"

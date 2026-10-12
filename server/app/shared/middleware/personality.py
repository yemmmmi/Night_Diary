"""PersonalityPromptBuilder — user-chosen 回信人格 preset (E1).

Orthogonal to the V3.x *mode* system (:class:`ModePromptBuilder`): the mode is
auto-decided by :class:`~app.services.ai.mood_monitor.MoodMonitor` and governs
*what to talk about this turn*; the personality is a user setting that governs
*the tone and length* of every reply. The two compose — a user can be in
``introspection`` mode while keeping a ``pragmatic`` personality.

The preset wording itself lives in :mod:`app.domain.agents.prompts`
(``PERSONALITY_PRESETS`` / ``EMPATHY_STYLE_INSTRUCTIONS``) so the diary-reply
scene (empathy agent) and this conversation scene share one source of truth.

The chosen key is read from ``ctx.extra["personality"]`` (the conversation loop
forwards the session-cached ``preferred_response_style``). This middleware only
*renders words* from a given key and is defensive: a missing/unknown key falls
back to the default preset, so a degraded personality subsystem can never break
the reply flow.
"""

from __future__ import annotations

from app.domain.agents.prompts import build_personality_directive
from app.shared.middleware.base import MiddlewareBase, MiddlewareContext

#: Key we read the chosen personality preset from in ctx.extra.
_PERSONALITY_KEY = "personality"


class PersonalityPromptBuilder(MiddlewareBase):
    """Inject the 【回信人格】 directive into a conversation system prompt."""

    name = "personality"

    def on_system_prompt(self, prompt: str, ctx: MiddlewareContext) -> str:
        key = ctx.extra.get(_PERSONALITY_KEY)
        directive = build_personality_directive(key if isinstance(key, str) else None)
        return f"{prompt}\n{directive}"


__all__ = ["PersonalityPromptBuilder"]
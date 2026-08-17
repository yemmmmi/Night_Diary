"""MiddlewareBase + MiddlewarePipeline — optional cross-cutting hooks shared by both scenes.

V3 P7: after P0-P6, two hooks proved real reuse value across the diary-reply
(scene 1) and conversation (scene 2) pipelines:

- ``on_system_prompt`` — transform the system prompt before the LLM call
  (used by :class:`SafetyMiddleware` to inject the crisis-response
  instruction that scene 2 was missing).
- ``on_reply`` — post-reply side effects such as the fire-and-forget
  episodic memory write-back (used by :class:`FinalizeMiddleware`).

The pipeline is **optionally injected**: an empty pipeline is a zero-cost
no-op and simple scenes skip it entirely (anti-over-engineering mitigation
from the V3 design doc, section 4.2.2 / 4.3).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MiddlewareContext:
    """Per-run context carried through the middleware pipeline.

    One instance is created per orchestration run (per streaming reply) and
    passed to every middleware hook so they share a single view of the turn.
    """

    #: "diary_reply" | "conversation"
    scenario: str
    user_id: str = "default"
    #: Diary content (scene 1) or user message (scene 2).
    content: str = ""
    intent: str = ""
    trace_id: str = ""
    conversation_id: str | None = None
    diary_id: str | None = None
    #: Final reply text (safe template or generated reply). Filled before on_reply.
    reply_text: str = ""
    #: Service container (lazy-typed to avoid circular imports). May be None.
    container: ServiceContainer | None = None
    #: Scene-1 diary turns always persist (importance 0.6), bypassing the
    #: emotion gate used by conversation turns.
    always_persist: bool = False
    #: Scene-specific payloads (e.g. the DiaryEntryRow for diary_reply).
    extra: dict[str, Any] = field(default_factory=dict)


class MiddlewareBase:
    """Lifecycle hooks shared by both scenes.

    Subclasses override only the hooks they need (the hooks are optional —
    that is the point: simple scenes skip middleware entirely). ``on_reply``
    implementations must be best-effort (swallow their own exceptions) so a
    failing middleware never breaks the reply flow.
    """

    name: str = "base"

    def on_system_prompt(self, prompt: str, ctx: MiddlewareContext) -> str:
        """Transform the system prompt. Default: return it unchanged."""
        return prompt

    def on_reply(self, ctx: MiddlewareContext) -> None:
        """Post-reply side effects (e.g. async memory write-back). Default: no-op."""


class MiddlewarePipeline:
    """Ordered, optionally-empty list of middlewares.

    An empty pipeline is a zero-cost no-op: callers check :attr:`is_empty`
    and skip, so simple scenes never pay for middleware they do not use.
    """

    def __init__(self, middlewares: Iterable[MiddlewareBase] | None = None) -> None:
        self._middlewares: list[MiddlewareBase] = list(middlewares or [])

    def add(self, middleware: MiddlewareBase) -> MiddlewarePipeline:
        """Append a middleware (chainable)."""
        self._middlewares.append(middleware)
        return self

    @property
    def is_empty(self) -> bool:
        return not self._middlewares

    def apply_system_prompt(self, prompt: str, ctx: MiddlewareContext) -> str:
        """Fold ``on_system_prompt`` over the pipeline in registration order."""
        for middleware in self._middlewares:
            prompt = middleware.on_system_prompt(prompt, ctx)
        return prompt

    def run_on_reply(self, ctx: MiddlewareContext) -> None:
        """Run every middleware's ``on_reply``; failures are logged, not raised."""
        for middleware in self._middlewares:
            try:
                middleware.on_reply(ctx)
            except Exception as exc:
                logger.warning(
                    "Middleware %s on_reply failed (best-effort): %s",
                    middleware.name,
                    exc,
                )


__all__ = ["MiddlewareBase", "MiddlewareContext", "MiddlewarePipeline"]

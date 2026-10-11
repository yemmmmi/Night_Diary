"""V3 P7 middleware pipeline — shared cross-cutting hooks for both scenes.

Public API: :class:`MiddlewareBase` / :class:`MiddlewareContext` /
:class:`MiddlewarePipeline` plus the two shipped middlewares
(:class:`SafetyMiddleware`, :class:`FinalizeMiddleware`) and the
:func:`build_default_pipeline` factory.

See ``docs/superpowers/specs/2026-08-12-v3-p7-middleware.md`` for the design.
"""

from __future__ import annotations

from app.shared.middleware.approval import ToolApprovalMiddleware
from app.shared.middleware.base import MiddlewareBase, MiddlewareContext, MiddlewarePipeline
from app.shared.middleware.finalize import FinalizeMiddleware
from app.shared.middleware.mode import ModePromptBuilder
from app.shared.middleware.safety import SafetyMiddleware

__all__ = [
    "MiddlewareBase",
    "MiddlewareContext",
    "MiddlewarePipeline",
    "SafetyMiddleware",
    "FinalizeMiddleware",
    "ModePromptBuilder",
    "ToolApprovalMiddleware",
]


def build_default_pipeline(
    approved_write_tools: frozenset[str] = frozenset(),
) -> MiddlewarePipeline:
    """Default production pipeline: Safety + Mode + Approval + Finalize.

    Calls that want zero overhead pass an empty ``MiddlewarePipeline()``
    instead (optional injection — simple scenes skip middleware entirely).

    Order note: ``ModePromptBuilder`` injects the mode tone + plan-state blocks
    into the system prompt; ``SafetyMiddleware`` is idempotent and must still
    guarantee the crisis-response block is present regardless of ordering.
    ``ToolApprovalMiddleware`` carries the C2 write-tool gate; the loop's
    ``_execute_tool`` applies the same gate independently, so this entry is the
    hook-visible surface, not the only enforcement point.
    """
    return MiddlewarePipeline(
        [
            SafetyMiddleware(),
            ModePromptBuilder(),
            ToolApprovalMiddleware(approved_write_tools),
            FinalizeMiddleware(),
        ]
    )

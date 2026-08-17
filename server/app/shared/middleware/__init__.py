"""V3 P7 middleware pipeline — shared cross-cutting hooks for both scenes.

Public API: :class:`MiddlewareBase` / :class:`MiddlewareContext` /
:class:`MiddlewarePipeline` plus the two shipped middlewares
(:class:`SafetyMiddleware`, :class:`FinalizeMiddleware`) and the
:func:`build_default_pipeline` factory.

See ``docs/superpowers/specs/2026-08-12-v3-p7-middleware.md`` for the design.
"""

from __future__ import annotations

from app.shared.middleware.base import MiddlewareBase, MiddlewareContext, MiddlewarePipeline
from app.shared.middleware.finalize import FinalizeMiddleware
from app.shared.middleware.safety import SafetyMiddleware

__all__ = [
    "MiddlewareBase",
    "MiddlewareContext",
    "MiddlewarePipeline",
    "SafetyMiddleware",
    "FinalizeMiddleware",
]


def build_default_pipeline() -> MiddlewarePipeline:
    """Default production pipeline: Safety (prompt injection) + Finalize (write-back).

    Callers that want zero overhead pass an empty ``MiddlewarePipeline()``
    instead (optional injection — simple scenes skip middleware entirely).
    """
    return MiddlewarePipeline([SafetyMiddleware(), FinalizeMiddleware()])

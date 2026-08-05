"""chromadb 0.5.x x posthog 7.x compatibility patch.

Background
----------
Two problems:

1. **API incompatibility**: chromadb 0.5.x's ``_direct_capture`` calls
   ``posthog.capture(distinct_id, event, properties)`` (3 positional args),
   but posthog 7.x changed to ``capture(event, *, distinct_id=None,
   properties=None)``.

2. **Consumer thread crash**: posthog 7.x's background consumer thread
   triggers an access violation (segfault) on Windows, crashing the process.

This patch:
- Sets ``posthog.disabled = True`` before chromadb is imported, preventing
  posthog from creating the default client and consumer thread
- Replaces ``Posthog._direct_capture`` with a no-op, so any
  ``posthog.capture()`` call can never trigger client creation
- Leaves the original ``Posthog.__init__`` untouched, keeping chromadb's
  component system initialisation intact

It does not affect any chromadb business functionality such as vector
retrieval or collection management.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_patched = False


def apply_telemetry_compat_patch() -> None:
    """Disable chromadb's posthog telemetry to fix the Windows crash.

    Silently skips when chromadb is not installed or has already fixed the
    problem itself.
    """
    global _patched
    if _patched:
        return

    # ── Step 1: disable the posthog module before chromadb is imported ──
    try:
        import posthog as _posthog

        _posthog.disabled = True
        # Silence posthog logs
        _posthog_logger = logging.getLogger("posthog")
        _posthog_logger.disabled = True
    except ImportError:
        pass

    # ── Step 2: monkeypatch chromadb's Posthog._direct_capture ──
    try:
        from chromadb.telemetry.product.posthog import Posthog
    except ImportError:
        # chromadb not installed, nothing to patch
        return

    original_direct_capture = Posthog._direct_capture

    import inspect

    # Check whether it has already been fixed
    src = inspect.getsource(original_direct_capture)
    if "disabled" in src and "return" in src:
        logger.debug("chromadb _direct_capture already compatible, skipping patch")
        return

    def _compat_direct_capture(self: Posthog, event: object) -> None:
        """No-op — posthog is already disabled at module level.

        The original implementation calls ``posthog.capture(distinct_id, event,
        properties)``, which triggers a TypeError (API signature change) and a
        consumer thread crash (Windows access violation) on posthog 7.x.
        """
        return

    Posthog._direct_capture = _compat_direct_capture  # type: ignore[method-assign]
    _patched = True
    logger.info(
        "Applied chromadb x posthog telemetry compat patch "
        "(posthog.disabled=True + _direct_capture no-op)"
    )

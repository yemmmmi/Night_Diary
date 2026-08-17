"""Pytest configuration shared across the suite.

Phase 0 only needs the application Settings to load without a real ``.env``
file, so we inject safe defaults before any module-level import happens.

Windows hardening: CPython < 3.12 crashes with an access violation when the
garbage collector finalises an ``asyncio`` proactor pipe transport whose IOCP
socket handle was already freed by the event-loop teardown
(``proactor_events._ProactorBasePipeTransport.__del__`` /
``__repr__``). This is a known Windows interpreter bug, not an app bug; the
crash surfaces at test-process exit (after all tests pass) when TestClient /
pytest-asyncio loops are collected. We replace the two GC-touched methods
with safe no-ops so the suite exits cleanly.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATA_DIR", "/tmp/night-diary-test")
os.environ.setdefault("MODEL_KEY_SECRET", "test-model-secret-min-16-chars")

if sys.platform == "win32":  # pragma: no cover - Windows-only hardening
    import asyncio

    def _safe_proactor_transport_del(self: object) -> None:
        # The proactor socket handle is already freed by the loop teardown;
        # touching it here (as the original __del__ does) reads freed memory.
        pass

    def _safe_proactor_transport_repr(self: object) -> str:
        # Never touch ``self._sock`` during GC-time repr (fileno() on a freed
        # proactor socket crashes).
        return f"<{self.__class__.__name__} closed>"

    _PROACTOR_TRANSPORT = asyncio.proactor_events._ProactorBasePipeTransport
    _PROACTOR_TRANSPORT.__del__ = _safe_proactor_transport_del  # type: ignore[attr-defined]
    _PROACTOR_TRANSPORT.__repr__ = _safe_proactor_transport_repr  # type: ignore[attr-defined]

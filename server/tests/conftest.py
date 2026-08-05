"""Pytest configuration shared across the suite.

Phase 0 only needs the application Settings to load without a real ``.env``
file, so we inject safe defaults before any module-level import happens.
"""

from __future__ import annotations

import os
import sys

# ── Python 3.10 compatibility shim ──
# StrEnum and datetime.UTC were added in Python 3.11; patch for 3.10 test runs.
if sys.version_info < (3, 11):  # noqa: UP036
    import enum

    if not hasattr(enum, "StrEnum"):

        class StrEnum(str, enum.Enum):
            """Backport of Python 3.11's StrEnum for 3.10 test runs."""

            def __str__(self) -> str:
                return str(self.value)

        enum.StrEnum = StrEnum  # type: ignore[attr-defined]

    import datetime as _dt

    if not hasattr(_dt, "UTC"):
        _dt.UTC = _dt.timezone.utc  # type: ignore[attr-defined]  # noqa: UP017

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATA_DIR", "/tmp/night-diary-test")
os.environ.setdefault("MODEL_KEY_SECRET", "test-model-secret-min-16-chars")

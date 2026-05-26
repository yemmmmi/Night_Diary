"""Pytest configuration shared across the suite.

Phase 0 only needs the application Settings to load without a real `.env`
file, so we inject safe defaults before any module-level import happens.
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-min-16-chars")
os.environ.setdefault("MODEL_KEY_SECRET", "test-model-secret-min-16-chars")

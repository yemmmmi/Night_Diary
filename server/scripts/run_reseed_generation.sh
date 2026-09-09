#!/bin/sh
set -eu

pip install --disable-pip-version-check --default-timeout=180 --retries=10 \
  'pytest>=8' 'pytest-asyncio>=0.24' >/tmp/pip-dev.log

python -u - <<'PY'
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

env_path = Path("/app/.env")
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if key and value:
            os.environ[key] = value

os.environ["EVAL_UPDATE_BASELINE"] = "1"
os.environ.setdefault("MCP_DECISION_REAL", "1")

from tests.eval._http_llm import REAL_MODE, MODEL, API_KEY

print("REAL_MODE", REAL_MODE)
print("MODEL", MODEL)
print("KEY_SET", bool(API_KEY))
if not API_KEY:
    raise SystemExit("LLM_API_KEY missing")

completed = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/eval/generation/", "-m", "eval", "-q", "-s"],
    check=False,
)
print(f"=== generation reseed exit={completed.returncode} ===")
raise SystemExit(completed.returncode)
PY

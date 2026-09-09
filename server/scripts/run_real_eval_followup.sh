#!/bin/sh
set -eu

pip install --disable-pip-version-check --default-timeout=180 --retries=10 \
  'pytest>=8' 'pytest-asyncio>=0.24' >/tmp/pip-dev.log

python - <<'PY'
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Prefer non-empty values from server/.env over empty Compose placeholders.
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

os.environ.setdefault("MCP_DECISION_REAL", "1")

from tests.eval._http_llm import REAL_MODE, MODEL, API_KEY
from app.config import get_settings

get_settings.cache_clear()
settings = get_settings()
print("REAL_MODE", REAL_MODE)
print("MODEL", MODEL)
print("KEY_SET", bool(API_KEY))
print("EMBEDDING_KEY_SET", bool(settings.embedding_api_key))
if not API_KEY:
    raise SystemExit("LLM_API_KEY missing")
if not settings.embedding_api_key:
    raise SystemExit("EMBEDDING_API_KEY missing")


def run(label: str, args: list[str], *, update_baseline: bool = False) -> int:
    env = os.environ.copy()
    if update_baseline:
        env["EVAL_UPDATE_BASELINE"] = "1"
    else:
        env.pop("EVAL_UPDATE_BASELINE", None)
    print(f"=== {label} ===")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-m", "eval", "-q", "-s"],
        env=env,
        check=False,
    )
    print(f"=== {label} exit={completed.returncode} ===")
    return completed.returncode


rc_gen = run(
    "1) generation REAL re-run",
    ["tests/eval/generation/"],
)
rc_seed = run(
    "2) reseed intent / skill / episodic baselines",
    [
        "tests/eval/intent/",
        "tests/eval/skill_call/",
        "tests/eval/episodic/",
    ],
    update_baseline=True,
)
sys.exit(0 if rc_gen == 0 and rc_seed == 0 else 1)
PY

#!/bin/sh
set -eu

# Production image already has the app. Only pytest is missing; skip the
# full ``.[dev]`` extra (ruff/mypy/scipy) which times out on PyPI.
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

os.environ.setdefault("MCP_DECISION_REAL", "1")

from tests.eval._http_llm import REAL_MODE, MODEL, BASE_URL, API_KEY
from app.config import get_settings

get_settings.cache_clear()
settings = get_settings()

print("REAL_MODE", REAL_MODE)
print("MODEL", MODEL)
print("BASE_URL", BASE_URL)
print("KEY_SET", bool(API_KEY))
print("EMBEDDING_KEY_SET", bool(settings.embedding_api_key))
print("RERANK_KEY_SET", bool(settings.rerank_api_key or settings.embedding_api_key))
print("EMBEDDING_MODEL", settings.embedding_model)
print("RERANK_MODEL", settings.rerank_model)
print("MCP_DECISION_REAL", os.getenv("MCP_DECISION_REAL", ""))

if not API_KEY:
    raise SystemExit("LLM_API_KEY missing after loading server/.env")
if not settings.embedding_api_key:
    raise SystemExit("EMBEDDING_API_KEY missing (repo root .env or server/.env)")

judge_dirs = [
    "tests/eval/intent/",
    "tests/eval/skill_call/",
    "tests/eval/tool_call/",
    "tests/eval/plan/",
    "tests/eval/treehole/",
    "tests/eval/generation/",
    "tests/eval/mcp_decision/",
]
retrieval_dirs = [
    "tests/eval/rag/",
    "tests/eval/episodic/",
]
baseline_dirs = [
    "tests/eval/generation/",
    "tests/eval/plan/",
    "tests/eval/intent/",
    "tests/eval/skill_call/",
    "tests/eval/episodic/",
]


def run_pytest(label: str, dirs: list[str], *, update_baseline: bool = False) -> int:
    env = os.environ.copy()
    if update_baseline:
        env["EVAL_UPDATE_BASELINE"] = "1"
    else:
        env.pop("EVAL_UPDATE_BASELINE", None)
    print(f"=== {label} ===")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *dirs, "-m", "eval", "-q", "-s"],
        env=env,
        check=False,
    )
    print(f"=== {label} exit={completed.returncode} ===")
    return completed.returncode


for run_idx in range(1, 4):
    print(f"\n########## REAL QUALITY GATE RUN {run_idx}/3 ##########")
    judge_rc = run_pytest(f"{run_idx}/3 judge/decision", judge_dirs)
    retrieval_rc = run_pytest(f"{run_idx}/3 rag/episodic", retrieval_dirs)
    if judge_rc != 0 or retrieval_rc != 0:
        raise SystemExit(f"REAL quality gate failed on run {run_idx}/3")

print("\n########## RESEED REAL BASELINES ##########")
seed_rc = run_pytest("reseed baselines", baseline_dirs, update_baseline=True)
if seed_rc != 0:
    raise SystemExit("baseline reseed failed")
print("REAL quality gates passed 3/3 and baselines were reseeded")
PY

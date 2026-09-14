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

# 1) Compose may inject empty LLM_API_KEY= ; fill/override from server/.env non-empty values.
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

# Import after env is ready (module caches REAL_MODE at import time).
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

print("=== Judge / decision evals ===")
judge = subprocess.run(
    [sys.executable, "-m", "pytest", *judge_dirs, "-m", "eval", "-q", "-s"],
    check=False,
)
print("=== RAG + episodic embedding/rerank evals ===")
retrieval = subprocess.run(
    [sys.executable, "-m", "pytest", *retrieval_dirs, "-m", "eval", "-q", "-s"],
    check=False,
)
sys.exit(0 if judge.returncode == 0 and retrieval.returncode == 0 else 1)
PY

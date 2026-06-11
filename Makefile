.PHONY: help dev-api dev-web dev-web-fast test test-server test-web lint lint-server lint-web format eval eval-rag

PY ?= python
NPM ?= npm
SERVER_DIR := server

help:
	@echo "Night Diary V2 — common targets"
	@echo "  dev-api        Run FastAPI dev server (http://127.0.0.1:8000, keep running)"
  @echo "  dev-web        Run Tauri desktop (auto-starts backend on :8000, then attaches)"
	@echo "  dev-web-fast   Tauri dev attaching to dev-api (no Python respawn)"
	@echo "  test           Run pytest + vitest"
	@echo "  lint           Run ruff + mypy + eslint + vue-tsc"
	@echo "  format         Run ruff format"

dev-api:
	cd $(SERVER_DIR) && $(PY) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-web:
	$(NPM) run tauri dev

dev-web-fast:
	@echo "Start dev-api in another terminal first: make dev-api"
	$(NPM) run tauri dev

test: test-server test-web

test-server:
	cd $(SERVER_DIR) && $(PY) -m pytest -q

# Full offline eval: RAG retrieval (B-3.5) + generation quality (B-7+).
# Out of CI; needs the [eval] extra + models/LLM. Prints per-suite token total
# and average latency (-s shows the [EVAL SUMMARY] lines) for cost regression.
eval:
	cd $(SERVER_DIR) && $(PY) -m pytest tests/eval/ -v -s -m eval

# Offline RAG retrieval eval only (out of CI; needs the [eval] extra + models).
# Seed/refresh the baseline with: EVAL_UPDATE_BASELINE=1 make eval-rag
eval-rag:
	cd $(SERVER_DIR) && $(PY) -m pytest tests/eval/rag/ -v -s -m eval

test-web:
	$(NPM) run test

lint: lint-server lint-web

lint-server:
	cd $(SERVER_DIR) && $(PY) -m ruff check . && $(PY) -m mypy app

lint-web:
	$(NPM) run lint && $(NPM) run type-check

format:
	cd $(SERVER_DIR) && $(PY) -m ruff format .

.PHONY: help dev-api dev-web test test-server test-web lint lint-server lint-web format eval eval-rag eval-episodic eval-tool eval-skill eval-intent eval-plan e2e smoke

PY ?= python
NPM ?= npm
SERVER_DIR := server

help:
	@echo "Night Diary V2 — common targets"
	@echo "  dev-api        Run FastAPI dev server (http://127.0.0.1:8000, keep running)"
	@echo "  dev-web        Run Vue 3 dev server (http://localhost:5173, attaches to :8000)"
	@echo "  e2e            API end-to-end flow (diary → analysis → feedback)"
	@echo "  smoke          Performance smoke checks (SQLite / bootstrap)"
	@echo "  test           Run pytest + vitest"
	@echo "  lint           Run ruff + mypy + eslint + vue-tsc"
	@echo "  format         Run ruff format"

dev-api:
	cd $(SERVER_DIR) && $(PY) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-web:
	$(NPM) run dev

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

# Offline episodic memory retrieval eval (V3 P5): jaccard vs vector vs vector+reranker.
# Stub mode (no sentence-transformers) runs jaccard + StubEmbedder vector branches;
# real mode (BGE) is what validates P4 vectorization ROI. Seed baseline:
# EVAL_UPDATE_BASELINE=1 make eval-episodic
eval-episodic:
	cd $(SERVER_DIR) && $(PY) -m pytest tests/eval/episodic/ -v -s -m eval

# Tool call accuracy eval (B-tool). Seed baseline: EVAL_UPDATE_BASELINE=1 make eval-tool
eval-tool:
	cd $(SERVER_DIR) && $(PY) -m pytest tests/eval/tool_call/ -v -s -m eval

# Skill call accuracy eval (progressive disclosure A/B). Seed baseline: EVAL_UPDATE_BASELINE=1 make eval-skill
eval-skill:
	cd $(SERVER_DIR) && $(PY) -m pytest tests/eval/skill_call/ -v -s -m eval

# Intent classification eval (fine-tune A/B). Seed baseline: EVAL_UPDATE_BASELINE=1 make eval-intent
eval-intent:
	cd $(SERVER_DIR) && $(PY) -m pytest tests/eval/intent/ -v -s -m eval

# Plan proposal quality eval (V3 P5 / Task 4-5): LLM-as-Judge over PlannerAgent
# proposals across 4 dimensions (actionability / gentleness / context_faithfulness /
# safety). Stub mode (no LLM_API_KEY) validates wiring; real mode does meaningful
# scoring. Seed baseline: EVAL_UPDATE_BASELINE=1 make eval-plan
eval-plan:
	cd $(SERVER_DIR) && $(PY) -m pytest tests/eval/plan/ -v -s -m eval

test-web:
	$(NPM) run test

lint: lint-server lint-web

lint-server:
	cd $(SERVER_DIR) && $(PY) -m ruff check . && $(PY) -m mypy app

lint-web:
	$(NPM) run lint && $(NPM) run type-check

format:
	cd $(SERVER_DIR) && $(PY) -m ruff format .

e2e:
	cd $(SERVER_DIR) && $(PY) -m pytest tests/e2e/ -v

smoke:
	cd $(SERVER_DIR) && $(PY) -m pytest tests/smoke/ -v

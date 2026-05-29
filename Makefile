.PHONY: help dev-api dev-web test test-server test-web lint lint-server lint-web format

PY ?= python
NPM ?= npm
SERVER_DIR := server

help:
	@echo "Night Diary V2 — common targets"
	@echo "  dev-api    Run FastAPI dev server (http://127.0.0.1:8000)"
	@echo "  dev-web    Run Tauri desktop app (npm run tauri dev)"
	@echo "  test       Run pytest + vitest"
	@echo "  lint       Run ruff + mypy + eslint + vue-tsc"
	@echo "  format     Run ruff format"

dev-api:
	cd $(SERVER_DIR) && $(PY) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-web:
	$(NPM) run tauri dev

test: test-server test-web

test-server:
	cd $(SERVER_DIR) && $(PY) -m pytest -q

test-web:
	$(NPM) run test

lint: lint-server lint-web

lint-server:
	cd $(SERVER_DIR) && $(PY) -m ruff check . && $(PY) -m mypy app

lint-web:
	$(NPM) run lint && $(NPM) run type-check

format:
	cd $(SERVER_DIR) && $(PY) -m ruff format .

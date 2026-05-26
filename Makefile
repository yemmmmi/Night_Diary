.PHONY: help up down logs migrate dev-api dev-web test test-server test-web lint lint-server lint-web format

PY ?= python
NPM ?= npm
SERVER_DIR := server
WEB_DIR := web

help:
	@echo "Night Diary V2 — common targets"
	@echo "  up         Start docker compose (mysql + redis)"
	@echo "  down       Stop docker compose"
	@echo "  logs       Tail docker compose logs"
	@echo "  migrate    Apply Alembic migrations to latest"
	@echo "  dev-api    Run FastAPI dev server (http://localhost:8000)"
	@echo "  dev-web    Run Vite dev server (http://localhost:5173)"
	@echo "  test       Run pytest + vitest"
	@echo "  lint       Run ruff + mypy + eslint + vue-tsc"
	@echo "  format     Run ruff format"

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	$(PY) -m alembic -c alembic.ini upgrade head

dev-api:
	cd $(SERVER_DIR) && $(PY) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	cd $(WEB_DIR) && $(NPM) run dev

test: test-server test-web

test-server:
	cd $(SERVER_DIR) && $(PY) -m pytest -q

test-web:
	cd $(WEB_DIR) && $(NPM) run test

lint: lint-server lint-web

lint-server:
	cd $(SERVER_DIR) && $(PY) -m ruff check . && $(PY) -m mypy app

lint-web:
	cd $(WEB_DIR) && $(NPM) run lint && $(NPM) run type-check

format:
	cd $(SERVER_DIR) && $(PY) -m ruff format .

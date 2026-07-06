# Night Diary — Python Backend

FastAPI AI engine for the Night Diary V2 web app. Runs as a uvicorn service (Docker or local).

## Development

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"

python -m app.main --port 8000 --data-dir ./testdata
curl http://127.0.0.1:8000/health
```

From repo root: `make dev-api`

## Docker

The backend runs in a Docker container (Python 3.12-slim + uvicorn 4 workers):

```bash
docker compose up -d            # 生产模式（MySQL + Redis + 全服务）
docker compose -f docker-compose.yml -f docker-compose.dev.yml up  # 开发模式（SQLite + 内存降级）
```

## Model files

Sentence-transformer and reranker weights are stored under the runtime data directory:

```
{DATA_DIR}/models/
```

Downloaded automatically on first RAG use (Phase B+), or copy model files there manually. Configure `HF_ENDPOINT=https://hf-mirror.com` to use the domestic mirror.

## Common issues

| Symptom | Fix |
|---------|-----|
| Port already in use | Pass a different `--port` or stop the dev server |
| LLM API timeout | Check `LLM_API_KEY` / `LLM_BASE_URL` in `.env` |
| Model download slow | First download ~200MB; configure `HF_ENDPOINT` for domestic mirror |

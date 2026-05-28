"""FastAPI application entry point — local desktop sidecar.

Binds to ``127.0.0.1`` only (never exposed to the network).  Accepts ``--port``
and ``--data-dir`` CLI arguments so the Tauri shell can control them.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Night Diary backend")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", type=str, default=None)
    return parser.parse_args(argv)


def _ensure_dirs(settings) -> None:  # type: ignore[no-untyped-def]
    for p in [
        Path(settings.data_dir),
        Path(settings.chroma_persist_dir),
        Path(settings.models_dir),
        Path(settings.backups_dir),
        Path(settings.logs_dir),
    ]:
        p.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Phase B+ : init SQLite engine, seed domain knowledge, warm up embeddings
    yield


def create_app(settings=None) -> FastAPI:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    cfg = settings or get_settings()

    _ensure_dirs(cfg)

    app = FastAPI(title=cfg.app_name, version="0.0.1", lifespan=lifespan)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/shutdown", tags=["meta"])
    def shutdown() -> dict[str, str]:
        """Graceful shutdown — Tauri calls this before sending SIGTERM."""
        import asyncio

        loop = asyncio.get_event_loop()
        loop.call_later(0.3, lambda: os._exit(0))
        return {"status": "shutting_down"}

    return app


app = create_app()


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``uvicorn`` (programmatic) — used by PyInstaller builds."""
    import uvicorn

    args = _parse_args(argv)

    if args.data_dir:
        os.environ["DATA_DIR"] = args.data_dir

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()

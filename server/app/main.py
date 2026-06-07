"""FastAPI application entry point — local desktop sidecar.

Binds to ``127.0.0.1`` only (never exposed to the network).  Accepts ``--port``
and ``--data-dir`` CLI arguments so the Tauri shell can control them.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

logger = logging.getLogger(__name__)


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


def _bootstrap_sync(app: FastAPI) -> None:
    """Load ServiceContainer (heavy — run off the event loop)."""
    from app.services.container import ServiceContainer

    app.state.container = ServiceContainer.create()
    app.state.bootstrap_done = True
    logger.info("Service container ready (SQLite + RAG + multi-agent graph)")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.container = None
    app.state.bootstrap_done = False
    bootstrap_task = asyncio.create_task(asyncio.to_thread(_bootstrap_sync, app))
    app.state.bootstrap_task = bootstrap_task
    yield
    await bootstrap_task


def create_app(settings=None) -> FastAPI:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    cfg = settings or get_settings()

    _ensure_dirs(cfg)

    app = FastAPI(title=cfg.app_name, version="0.0.1", lifespan=lifespan)

    from app.api.v1.error_handlers import register_error_handlers
    from app.api.v1.router import api_router

    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/shutdown", tags=["meta"])
    async def shutdown() -> dict[str, str]:
        """Graceful shutdown — Tauri calls this before sending SIGTERM."""
        loop = asyncio.get_running_loop()
        loop.call_later(0.3, lambda: os._exit(0))
        return {"status": "shutting_down"}

    return app


def main(argv: list[str] | None = None) -> None:
    """Entry point for uvicorn and PyInstaller ``nightdiary-backend`` builds."""
    import uvicorn

    from app.config import get_settings

    args = _parse_args(argv)

    if args.data_dir:
        os.environ["DATA_DIR"] = args.data_dir

    get_settings.cache_clear()
    application = create_app()

    uvicorn.run(
        application,
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


def __getattr__(name: str) -> FastAPI:  # PEP 562 lazy export for tests
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()

"""FastAPI 应用入口。

默认绑定到 ``127.0.0.1``（Docker 环境请使用 ``--host 0.0.0.0``）。接受
``--port`` 和 ``--data-dir`` 命令行参数。
"""

from __future__ import annotations

import argparse
import asyncio
import faulthandler
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

# 启用 faulthandler 以捕获原生崩溃的 traceback
faulthandler.enable()

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

# 在任何 chromadb 导入之前应用 chromadb × posthog 兼容性补丁。
# 必须尽早执行——chromadb 在导入时会触发遥测调用。
from app.shared.chromadb_telemetry_compat import apply_telemetry_compat_patch

apply_telemetry_compat_patch()

logger = logging.getLogger(__name__)


def _app_build_version() -> str:
    """尽力获取 git 短哈希，用于开发环境检测过期的后端进程。"""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


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


def _bootstrap_core_sync(app: FastAPI) -> None:
    """SQLite + 会话工厂——速度足够快，足以支撑 ``/ready`` 和日记 CRUD。"""
    import time as _time

    from app.services.container import ServiceContainer

    t0 = _time.perf_counter()
    app.state.container = ServiceContainer.create_core()
    t1 = _time.perf_counter()
    app.state.bootstrap_done = True
    logger.info("Core bootstrap ready (SQLite + diary CRUD) in %.2fs", t1 - t0)


def _bootstrap_ai_sync(app: FastAPI) -> None:
    """RAG / 智能体——在核心启动之后运行；若仍在挂起，首次 AI 调用可能会触发。"""
    container = app.state.container
    if container is not None:
        container.ensure_ai_stack()
    app.state.bootstrap_ai_done = True
    logger.info("AI bootstrap complete")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.container = None
    app.state.bootstrap_done = False
    app.state.bootstrap_ai_done = False

    core_task = asyncio.create_task(asyncio.to_thread(_bootstrap_core_sync, app))
    yield
    await core_task


def create_app(settings=None) -> FastAPI:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    cfg = settings or get_settings()

    from app.services.model_downloader import configure_hf_environment

    configure_hf_environment(cfg)
    _ensure_dirs(cfg)

    app = FastAPI(title=cfg.app_name, version="0.0.1", lifespan=lifespan)

    # CORS：始终允许回环地址；额外的源通过配置指定。
    import re as _re

    from fastapi.middleware.cors import CORSMiddleware

    _cors_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    if cfg.cors_origins:
        _extra = "|".join(_re.escape(o.strip()) for o in cfg.cors_origins.split(",") if o.strip())
        if _extra:
            _cors_regex = f"{_cors_regex}|{_extra}"

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_cors_regex,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.v1.error_handlers import register_error_handlers
    from app.api.v1.router import api_router

    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """Uvicorn 正在监听。"""
        return {"status": "ok"}

    @app.get("/ready", tags=["meta"])
    def ready() -> JSONResponse:
        """核心启动完成——日记 CRUD 可安全使用。"""
        if getattr(app.state, "bootstrap_done", False) and app.state.container is not None:
            return JSONResponse({"status": "ok"})
        return JSONResponse(
            {"status": "bootstrapping"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @app.get("/meta/version", tags=["meta"])
    def meta_version() -> dict[str, str]:
        """开发辅助工具——让前端检测过期的后端进程。"""
        return {"version": _app_build_version()}

    return app


def main(argv: list[str] | None = None) -> None:
    """uvicorn 的入口点。"""
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


def __getattr__(name: str) -> FastAPI:  # PEP 562 惰性导出，供测试使用
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()

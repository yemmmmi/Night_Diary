"""Task queue — async sidecar execution with Redis Queue or threading fallback.

When REDIS_URL is set and Redis is available, tasks are enqueued to RQ
(Redis Queue) workers for proper background processing. When Redis is
unavailable, tasks fall back to daemon threads (same as before, but
centralized here for easier migration).

Usage:
    from app.infrastructure.task_queue import enqueue_task

    enqueue_task(
        "app.domain.agents.entity_extractor._run_extraction_sync",
        session_factory,
        user_id,
        conversation_id,
        text,
    )
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from app.infrastructure.redis_client import is_redis_available

logger = logging.getLogger(__name__)

_redis_queue = None


def _init_rq() -> None:
    """Initialize RQ queue if Redis is available."""
    global _redis_queue
    if not is_redis_available():
        return
    try:
        from rq import Queue

        from app.infrastructure.redis_client import _redis_client

        _redis_queue = Queue(connection=_redis_client, default_timeout=300)
        logger.info("RQ task queue initialized")
    except ImportError:
        logger.debug("rq package not installed; using threading fallback")
    except Exception as exc:
        logger.warning("RQ initialization failed: %s", exc)


def enqueue_task(
    func: Callable[..., Any] | str,
    *args: Any,
    **kwargs: Any,
) -> str | None:
    """Enqueue a background task.

    Args:
        func: Either a callable (threading mode) or a dotted path string
              like "app.module.function" (RQ mode). When using RQ, a string
              path is required so the worker can import it.
        *args, **kwargs: Arguments to pass to the function.

    Returns:
        Job ID (RQ mode) or thread name (threading mode), or None on failure.
    """
    if _redis_queue is not None and isinstance(func, str):
        try:
            job = _redis_queue.enqueue(func, *args, **kwargs)
            logger.debug("RQ task enqueued: %s → job_id=%s", func, job.id)
            return str(job.id)
        except Exception as exc:
            logger.warning("RQ enqueue failed, falling back to thread: %s", exc)

    # Threading fallback
    if callable(func):
        return _spawn(func, args, kwargs)
    elif isinstance(func, str):
        # Import the function by dotted path
        try:
            parts = func.rsplit(".", 1)
            if len(parts) == 2:
                module = __import__(parts[0], fromlist=[parts[1]])
                fn = getattr(module, parts[1])
                return _spawn(fn, args, kwargs)
        except Exception as exc:
            logger.warning("Failed to import task function %s: %s", func, exc)
    return None


# ── Graceful shutdown: track in-flight daemon threads ──────────────────
#
# The threading fallback runs fire-and-forget daemon threads. On process
# shutdown these are normally killed mid-work (memory writes / entity
# extraction can be lost). We track live threads and provide
# :func:`begin_shutdown` / :func:`drain` so the app lifespan can stop
# accepting new tasks and wait briefly for in-flight ones to finish.

_threads_lock = threading.Lock()
_active_threads: set[threading.Thread] = set()
_shutting_down = False


def begin_shutdown() -> None:
    """Stop accepting new background tasks (in-flight ones keep running)."""
    global _shutting_down
    _shutting_down = True


def reset_shutdown_state() -> None:
    """Re-allow background tasks (called on app startup / hot-reload).

    A fresh app instance must accept tasks even if a previous instance in
    this process ran :func:`begin_shutdown` (tests, dev reload).
    """
    global _shutting_down
    _shutting_down = False


def _spawn(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    """Start a tracked daemon thread running ``func`` safely."""
    with _threads_lock:
        if _shutting_down:
            logger.info("Task queue shutting down; skipping %s", getattr(func, "__name__", func))
            return None
        thread = threading.Thread(
            target=_thread_runner, args=(func, args, kwargs), daemon=True
        )
        _active_threads.add(thread)
    thread.start()
    return thread.name


def _thread_runner(
    func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    try:
        _run_safe(func, args, kwargs)
    finally:
        with _threads_lock:
            _active_threads.discard(threading.current_thread())


def drain(timeout_s: float = 5.0) -> int:
    """Wait up to ``timeout_s`` for in-flight daemon tasks; return remaining count.

    Best-effort: tasks that ignore the deadline are abandoned (they are
    daemon threads, so they never block process exit).
    """
    deadline = time.monotonic() + timeout_s
    while True:
        with _threads_lock:
            alive = [t for t in _active_threads if t.is_alive()]
        if not alive:
            return 0
        if time.monotonic() >= deadline:
            return len(alive)
        for t in alive:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return len([x for x in _active_threads if x.is_alive()])
            t.join(timeout=min(0.2, remaining))
    return 0


def _run_safe(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """Run a function safely, catching all exceptions."""
    try:
        func(*args, **kwargs)
    except Exception as exc:
        logger.warning("Background task failed: %s", exc, exc_info=True)


# Initialize on import
_init_rq()

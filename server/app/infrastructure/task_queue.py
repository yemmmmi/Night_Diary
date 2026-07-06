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
            return job.id
        except Exception as exc:
            logger.warning("RQ enqueue failed, falling back to thread: %s", exc)

    # Threading fallback
    if callable(func):
        thread = threading.Thread(target=_run_safe, args=(func, args, kwargs), daemon=True)
        thread.start()
        return thread.name
    elif isinstance(func, str):
        # Import the function by dotted path
        try:
            parts = func.rsplit(".", 1)
            if len(parts) == 2:
                module = __import__(parts[0], fromlist=[parts[1]])
                fn = getattr(module, parts[1])
                thread = threading.Thread(target=_run_safe, args=(fn, args, kwargs), daemon=True)
                thread.start()
                return thread.name
        except Exception as exc:
            logger.warning("Failed to import task function %s: %s", func, exc)
    return None


def _run_safe(func: Callable, args: tuple, kwargs: dict) -> None:
    """Run a function safely, catching all exceptions."""
    try:
        func(*args, **kwargs)
    except Exception as exc:
        logger.warning("Background task failed: %s", exc, exc_info=True)


# Initialize on import
_init_rq()

"""任务队列 — 使用 Redis Queue 或线程回退的异步边车执行。

当设置了 REDIS_URL 且 Redis 可用时，任务入队到 RQ
（Redis Queue）工作进程进行正式的后台处理。当 Redis
不可用时，任务回退到守护线程（与之前相同，但在此集中
管理以便于迁移）。

用法：
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
    """如果 Redis 可用则初始化 RQ 队列。"""
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
    """将后台任务入队。

    Args:
        func: 可调用对象（线程模式）或点分路径字符串
              如 "app.module.function"（RQ 模式）。使用 RQ 时需要字符串
              路径，以便工作进程可以导入它。
        *args, **kwargs: 传递给函数的参数。

    Returns:
        作业 ID（RQ 模式）或线程名（线程模式），失败时返回 None。
    """
    if _redis_queue is not None and isinstance(func, str):
        try:
            job = _redis_queue.enqueue(func, *args, **kwargs)
            logger.debug("RQ task enqueued: %s → job_id=%s", func, job.id)
            return str(job.id)
        except Exception as exc:
            logger.warning("RQ enqueue failed, falling back to thread: %s", exc)

    # 线程回退
    if callable(func):
        thread = threading.Thread(target=_run_safe, args=(func, args, kwargs), daemon=True)
        thread.start()
        return thread.name
    elif isinstance(func, str):
        # 通过点分路径导入函数
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


def _run_safe(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    """安全地运行函数，捕获所有异常。"""
    try:
        func(*args, **kwargs)
    except Exception as exc:
        logger.warning("Background task failed: %s", exc, exc_info=True)


# 导入时初始化
_init_rq()

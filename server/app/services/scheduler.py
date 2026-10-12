"""Scheduled-task scheduler loop (A4).

A single in-process background loop that ticks on an interval, selects due
tasks and enqueues them through the task queue (RQ when Redis is available,
daemon threads otherwise). The loop only *dispatches* — the task bodies run
in :func:`app.services.scheduled_task_service.execute_scheduled_task`, so a
slow or failing task body can never stall the loop.

Best-effort by design: a missing container or a failing tick is logged and
swallowed, never raised into the app lifespan.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Interval floor — never spin the scheduler faster than this.
_MIN_INTERVAL_S = 10


def run_scheduler_tick(app: Any) -> int:
    """One scheduler pass: enqueue every due task. Returns the dispatch count.

    Reads the bootstrap container from ``app.state.container`` (populated in a
    background thread at startup). Best-effort: returns 0 when the container
    is not ready or the pass fails.
    """
    container = getattr(app.state, "container", None)
    if container is None:
        return 0
    from app.services import scheduled_task_service

    try:
        return scheduled_task_service.run_due_tasks(container)
    except Exception as exc:  # never let a tick break the loop
        logger.warning("Scheduler tick failed: %s", exc)
        return 0


def run_scheduler_loop(app: Any) -> Any:
    """Start the async scheduler loop; return the task for shutdown cancel.

    Re-reads settings/container each iteration so it survives the deferred
    core bootstrap. Only ticks when ``settings.scheduler_enabled`` is true.
    """

    async def _loop() -> None:
        settings = getattr(app.state, "settings", None)
        while True:
            try:
                interval = max(
                    _MIN_INTERVAL_S,
                    int(getattr(settings, "scheduler_interval_s", 60) or 60),
                )
                await asyncio.sleep(interval)
                settings = getattr(app.state, "settings", None)
                if settings is None or not getattr(settings, "scheduler_enabled", True):
                    continue
                await asyncio.to_thread(run_scheduler_tick, app)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Scheduler loop iteration failed: %s", exc)

    return asyncio.create_task(_loop())


__all__ = ["run_scheduler_loop", "run_scheduler_tick"]
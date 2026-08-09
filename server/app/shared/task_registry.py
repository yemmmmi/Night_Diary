"""TaskRegistry — lifecycle management for streaming background tasks.

Replaces the simple ``set[asyncio.Task]`` used in P0's ``conversation.py``
with a structured registry that:

1. Maps ``trace_id`` → ``asyncio.Task`` so tasks can be cancelled by ID
   (needed for the abort endpoint and for ``_terminating_reply`` tests).
2. Auto-removes completed tasks via ``add_done_callback``.
3. Supports ``cancel_all()`` for graceful application shutdown.

This is the P1 layer-5 "task finalization" mechanism — it ensures no
background task is orphaned when the server shuts down or when a client
disconnects mid-stream.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Timeout (seconds) for waiting a cancelled task to actually terminate.
#: A task that ignores ``CancelledError`` longer than this is abandoned
#: (the registry stops tracking it, but the OS-level coroutine may leak —
#: that's acceptable for P1; P5 will add hard process-level cancellation).
_CANCEL_TIMEOUT_S = 5.0


class TaskRegistry:
    """Registry mapping ``trace_id`` → background ``asyncio.Task``.

    Not thread-safe — must be used from the main event loop. All methods
    are coroutines (or sync getters) intended to run on the loop.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def register(self, trace_id: str, task: asyncio.Task[Any]) -> None:
        """Register *task* under *trace_id*.

        When the task completes (normally or by exception), it is
        automatically removed from the registry via ``add_done_callback``.
        """
        self._tasks[trace_id] = task

        def _on_done(_t: asyncio.Task[Any]) -> None:
            # pop only if the same task is still registered (avoid clobbering
            # a re-registered task with the same trace_id)
            if self._tasks.get(trace_id) is _t:
                self._tasks.pop(trace_id, None)

        task.add_done_callback(_on_done)

    async def cancel(self, trace_id: str) -> bool:
        """Cancel the task registered under *trace_id*.

        Returns ``True`` if a live task was found and cancelled,
        ``False`` if the trace_id is unknown or the task already finished.
        """
        task = self._tasks.get(trace_id)
        if task is None or task.done():
            return False

        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=_CANCEL_TIMEOUT_S)
        except (TimeoutError, asyncio.CancelledError):
            # Task didn't terminate within timeout — log and abandon.
            logger.warning(
                "Task trace_id=%s did not terminate within %.1fs after cancel; "
                "abandoning (may leak at OS level)",
                trace_id,
                _CANCEL_TIMEOUT_S,
            )
        return True

    def get_active_trace_ids(self) -> list[str]:
        """Return all currently-registered trace_ids (for debugging/monitoring)."""
        return list(self._tasks.keys())

    async def cancel_all(self) -> None:
        """Cancel every active task. Used during graceful application shutdown."""
        trace_ids = list(self._tasks.keys())
        for trace_id in trace_ids:
            await self.cancel(trace_id)


# ── Application-level singleton ──────────────────────────────────────

_registry: TaskRegistry | None = None


def get_task_registry() -> TaskRegistry:
    """Return the process-global ``TaskRegistry`` singleton.

    Lazily initialised so the event loop is only touched when first
    accessed (importing this module does not create one).
    """
    global _registry
    if _registry is None:
        _registry = TaskRegistry()
    return _registry

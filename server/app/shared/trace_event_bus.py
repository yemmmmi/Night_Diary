"""In-memory event bus for developer-mode SSE trace push.

Provides ``TraceEventBus`` — a lightweight asyncio.Queue-based pub/sub that
fans out trace events (one ``trace_id`` → many SSE subscriber queues). The bus
is process-local: each subscriber holds an ``asyncio.Queue`` and drains it via
``get_nowait`` / ``await get`` inside an SSE handler. When the queue fills up
(the client is slow or disconnected), events are dropped with a warning so the
producer never blocks.

Usage::

    from app.shared.trace_event_bus import get_event_bus

    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)
    ...
    await bus.publish(trace_id, {"type": "span", "data": {...}})
    ...
    await bus.unsubscribe(trace_id, queue)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton (lazily initialised by ``get_event_bus``).
_event_bus: TraceEventBus | None = None


class TraceEventBus:
    """Asyncio.Queue-backed pub/sub for fanning trace events to SSE subscribers.

    Each ``trace_id`` maps to a list of ``asyncio.Queue`` instances — one per
    active SSE connection. Producers call ``publish`` to fan-out an event to
    every subscriber; consumers drain their queue inside the SSE handler.

    When a subscriber's queue is full (slow client), ``publish`` drops the
    event and logs a warning instead of blocking the producer.

    Sync worker threads (where ``trace_span.__exit__`` and request ``finally``
    blocks run) must use ``publish_from_thread`` instead of ``publish`` — it
    captures the main event loop on first ``subscribe`` and uses
    ``call_soon_threadsafe`` to schedule the fan-out there, avoiding the
    cross-loop ``put_nowait`` race that silently drops wake-ups.
    """

    def __init__(self, max_queue_size: int = 100) -> None:
        self._subscribers: defaultdict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(
            list
        )
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size
        self._main_loop: asyncio.AbstractEventLoop | None = None

    async def subscribe(self, trace_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Register a new subscriber queue for ``trace_id`` and return it.

        The returned queue is bounded by ``max_queue_size`` so a slow consumer
        cannot accumulate unbounded events in memory.  Also captures the
        running event loop so that ``publish_from_thread`` can safely schedule
        fan-out callbacks from sync worker threads.
        """
        if self._main_loop is None:
            self._main_loop = asyncio.get_running_loop()
        async with self._lock:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
                maxsize=self._max_queue_size
            )
            self._subscribers[trace_id].append(queue)
            return queue

    async def unsubscribe(self, trace_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a specific subscriber queue for ``trace_id``.

        If the subscriber list becomes empty after removal, the ``trace_id``
        key is deleted entirely so ``_subscribers`` does not accumulate stale
        empty lists.
        """
        async with self._lock:
            queues = self._subscribers.get(trace_id)
            if queues and queue in queues:
                queues.remove(queue)
                if not queues:
                    del self._subscribers[trace_id]

    async def publish(self, trace_id: str, event: dict[str, Any]) -> None:
        """Fan-out ``event`` to every subscriber of ``trace_id``.

        Uses ``put_nowait`` so a full queue drops the event with a warning
        instead of blocking the producer. No-op when there are no subscribers.

        Must be called from the main event loop.  Sync worker threads should
        use ``publish_from_thread`` instead.
        """
        # Read without the lock — iteration is atomic within a single event
        # loop tick (``put_nowait`` is synchronous, no awaits are interleaved).
        self._fanout(trace_id, event)

    def publish_from_thread(self, trace_id: str, event: dict[str, Any]) -> None:
        """Thread-safe publish for sync worker threads.

        Schedules the fan-out on the main event loop via
        ``call_soon_threadsafe`` so that ``queue.put_nowait`` runs in the same
        loop as the SSE subscriber's ``await queue.get()``.  This avoids the
        cross-loop wake-up race where ``put_nowait`` from a different thread
        silently fails to schedule the getter's callback.

        Best-effort: if the main loop hasn't been captured yet (no SSE
        subscriber has connected) or is closed, the event is silently dropped.
        """
        loop = self._main_loop
        if loop is None or loop.is_closed():
            return
        with contextlib.suppress(RuntimeError):
            # Loop closed between the check above and the call — drop silently.
            loop.call_soon_threadsafe(self._fanout, trace_id, event)

    def _fanout(self, trace_id: str, event: dict[str, Any]) -> None:
        """Put ``event`` into every subscriber queue (main-loop only)."""
        queues = self._subscribers.get(trace_id, [])
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Trace event bus queue full for trace_id=%s; dropping event",
                    trace_id,
                )

    async def cleanup(self, trace_id: str) -> None:
        """Delete the entire subscriber list for ``trace_id``.

        Called when a trace ends (e.g. request finished) to release all
        subscriber queues at once.
        """
        async with self._lock:
            self._subscribers.pop(trace_id, None)


def get_event_bus() -> TraceEventBus:
    """Return the process-global ``TraceEventBus`` singleton.

    Lazily initialised on first call so the event loop is only touched when
    the bus is actually needed (importing this module does not create one).
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = TraceEventBus()
    return _event_bus

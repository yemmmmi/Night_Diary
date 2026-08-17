"""Event bus for SSE trace push — in-memory primary, Redis for cross-replica.

Provides ``TraceEventBus``: fan-out of trace events (one ``trace_id`` → many
SSE subscriber queues).

**In-memory primary (robustness P2-7 design):** events always fan out to
same-process subscriber queues via ``asyncio.Queue`` — a Redis hiccup never
breaks same-process streaming (the production single-replica deployment).

**Redis cross-replica capability (when Redis is available):**
- every published event is also appended to a capped per-trace buffer
  (``evt:<trace_id>`` list) and published on a per-trace channel
  (``evtchan:<trace_id>``);
- a subscriber first listens on the channel, then replays the buffer, then
  drains live channel events;
- each event carries a unique ``event_uuid`` and every queue dedups by it,
  so an event delivered via both the local fan-out and Redis is received
  exactly once.

When Redis is unavailable the bus is a plain in-memory pub/sub (previous
behaviour, no buffering for late subscribers — the SSE handler replays
already-completed spans from the persisted trace).

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
import json
import logging
import uuid
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton (lazily initialised by ``get_event_bus``).
_event_bus: TraceEventBus | None = None

#: Max events buffered per trace in Redis (late-subscriber replay window).
_REDIS_BUFFER_CAP = 200
#: Max event uuids remembered per subscriber for dedup.
_DEDUP_CAP = 500


def _buffer_key(trace_id: str) -> str:
    return f"evt:{trace_id}"


def _channel(trace_id: str) -> str:
    return f"evtchan:{trace_id}"


class TraceEventBus:
    """Queue-backed pub/sub for fanning trace events to SSE subscribers.

    Each ``trace_id`` maps to subscriber entries (an ``asyncio.Queue`` plus an
    optional Redis pub/sub listener task). Producers call :meth:`publish`;
    consumers drain their queue inside the SSE handler. A full queue drops
    the event with a warning so the producer never blocks.
    """

    def __init__(self, max_queue_size: int = 100) -> None:
        self._subscribers: defaultdict[str, list[Any]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._redis: Any = None  # lazy redis.asyncio client

    # ── Redis plumbing ───────────────────────────────────────────────────

    def _redis_enabled(self) -> bool:
        try:
            from app.infrastructure.redis_client import is_redis_available

            return is_redis_available()
        except Exception:
            return False

    async def _redis_client(self) -> Any:
        """Lazily build the async Redis client (None when unavailable)."""
        if self._redis is not None:
            return self._redis
        if not self._redis_enabled():
            return None
        try:
            import redis.asyncio as aioredis

            from app.infrastructure.redis_client import _REDIS_URL

            self._redis = aioredis.from_url(_REDIS_URL, decode_responses=True)
        except Exception as exc:
            logger.warning("Event bus Redis client init failed: %s", exc)
            self._redis = None
        return self._redis

    @staticmethod
    def _with_uuid(event: dict[str, Any]) -> dict[str, Any]:
        """Stamp a dedup uuid onto an event (idempotent)."""
        if "event_uuid" not in event:
            event = dict(event)
            event["event_uuid"] = uuid.uuid4().hex
        return event

    async def _publish_redis(self, trace_id: str, event: dict[str, Any]) -> None:
        redis = await self._redis_client()
        if redis is None:
            return
        with contextlib.suppress(Exception):
            raw = json.dumps(event, ensure_ascii=False, default=str)
            pipe = redis.pipeline()
            pipe.rpush(_buffer_key(trace_id), raw)
            pipe.ltrim(_buffer_key(trace_id), -_REDIS_BUFFER_CAP, -1)
            pipe.publish(_channel(trace_id), raw)
            await pipe.execute()

    async def _replay_buffer(self, trace_id: str, queue: asyncio.Queue[Any]) -> None:
        redis = await self._redis_client()
        if redis is None:
            return
        with contextlib.suppress(Exception):
            raw_items = await redis.lrange(_buffer_key(trace_id), -_REDIS_BUFFER_CAP, -1)
            for raw in raw_items:
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    self._put(queue, json.loads(raw), set())

    # ── Subscriber management ────────────────────────────────────────────

    async def subscribe(self, trace_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Register a subscriber queue for ``trace_id`` and return it.

        When Redis is available the queue is pre-filled with the recent
        per-trace buffer (so events published before the SSE client connected
        are not lost) and a pub/sub listener task starts forwarding live
        channel events. Dedup by ``event_uuid`` keeps deliveries exactly once.
        """
        if self._main_loop is None:
            self._main_loop = asyncio.get_running_loop()
        async with self._lock:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
                maxsize=self._max_queue_size
            )
            entry: dict[str, Any] = {"queue": queue, "seen": set(), "task": None}
            self._subscribers[trace_id].append(entry)

            redis = await self._redis_client()
            if redis is not None:
                pubsub = redis.pubsub()
                await pubsub.subscribe(_channel(trace_id))
                entry["pubsub"] = pubsub
                entry["task"] = asyncio.create_task(
                    self._listen(trace_id, pubsub, queue, entry["seen"])
                )
                await self._replay_buffer(trace_id, queue)
            return queue

    async def _listen(
        self,
        trace_id: str,
        pubsub: Any,
        queue: asyncio.Queue[Any],
        seen: set[str],
    ) -> None:
        """Forward Redis pub/sub messages into the subscriber queue."""
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    self._put(queue, json.loads(message["data"]), seen)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Event bus redis listener failed for %s: %s", trace_id, exc)

    async def unsubscribe(
        self, trace_id: str, queue: asyncio.Queue[dict[str, Any]]
    ) -> None:
        """Remove the subscriber for ``trace_id`` (cancels its redis task)."""
        async with self._lock:
            entries = self._subscribers.get(trace_id)
            if entries:
                entry = next((e for e in entries if e["queue"] is queue), None)
                if entry is not None:
                    entries.remove(entry)
                    task = entry.get("task")
                    if task is not None:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                    pubsub = entry.get("pubsub")
                    if pubsub is not None:
                        with contextlib.suppress(Exception):
                            await pubsub.unsubscribe()
                            await pubsub.aclose()
                    if not entries:
                        del self._subscribers[trace_id]

    # ── Publish ──────────────────────────────────────────────────────────

    async def publish(self, trace_id: str, event: dict[str, Any]) -> None:
        """Fan-out ``event`` to every same-process subscriber + Redis.

        Must be called from the main event loop; sync worker threads should
        use :meth:`publish_from_thread`.
        """
        event = self._with_uuid(event)
        self._fanout(trace_id, event)
        await self._publish_redis(trace_id, event)

    def publish_from_thread(self, trace_id: str, event: dict[str, Any]) -> None:
        """Thread-safe publish for sync worker threads (best-effort)."""
        event = self._with_uuid(event)
        loop = self._main_loop
        if loop is None or loop.is_closed():
            return
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._fanout, trace_id, event)
        with contextlib.suppress(RuntimeError):
            if loop.is_closed():
                return
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._publish_redis(trace_id, event))
            )

    def _put(
        self,
        queue: asyncio.Queue[Any],
        event: dict[str, Any],
        seen: set[str],
    ) -> None:
        """Put ``event`` into ``queue`` unless its uuid was already delivered."""
        event_uuid = event.get("event_uuid")
        if event_uuid is not None:
            if event_uuid in seen:
                return
            seen.add(event_uuid)
            if len(seen) > _DEDUP_CAP:
                seen.clear()
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "Trace event bus queue full; dropping event (trace_id=%s)",
                queue,
            )

    def _fanout(self, trace_id: str, event: dict[str, Any]) -> None:
        """Put ``event`` into every same-process subscriber queue."""
        for entry in list(self._subscribers.get(trace_id, [])):
            self._put(entry["queue"], event, entry["seen"])

    async def cleanup(self, trace_id: str) -> None:
        """Delete all subscribers for ``trace_id`` (cancels redis tasks)."""
        async with self._lock:
            entries = self._subscribers.pop(trace_id, [])
        for entry in entries:
            task = entry.get("task")
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            pubsub = entry.get("pubsub")
            if pubsub is not None:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe()
                    await pubsub.aclose()


def get_event_bus() -> TraceEventBus:
    """Return the process-global ``TraceEventBus`` singleton."""
    global _event_bus
    if _event_bus is None:
        _event_bus = TraceEventBus()
    return _event_bus

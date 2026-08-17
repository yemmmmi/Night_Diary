"""Unit tests for the Redis-backed event bus (robustness P2-7).

Uses a fake async Redis to verify: buffered replay for late subscribers,
live pub/sub delivery, per-event-uuid dedup (no double delivery when an
event reaches a queue via both local fan-out and Redis), and the buffer cap.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict

import pytest

from app.shared.trace_event_bus import _REDIS_BUFFER_CAP, TraceEventBus


class _FakePubSub:
    def __init__(self, channel: str, channel_msgs: dict[str, list[str]]) -> None:
        self._msgs = list(channel_msgs.get(channel, []))
        self._closed = False

    async def subscribe(self, *channels: str) -> None:
        return None

    async def listen(self):  # type: ignore[no-untyped-def]
        for raw in self._msgs:
            yield {"type": "message", "data": raw}
        # 阻塞直到被关闭, 模拟真实 pubsub 长连接
        while not self._closed:
            await asyncio.sleep(3600)
    async def unsubscribe(self) -> None:
        self._closed = True

    async def aclose(self) -> None:
        self._closed = True


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, ...]] = []

    def rpush(self, key: str, raw: str) -> _FakePipeline:
        self._ops.append(("rpush", key, raw))
        return self

    def ltrim(self, key: str, start: int, end: int) -> _FakePipeline:
        self._ops.append(("ltrim", key, str(start), str(end)))
        return self

    def publish(self, channel: str, raw: str) -> _FakePipeline:
        self._ops.append(("publish", channel, raw))
        return self

    async def execute(self) -> None:  # type: ignore[no-untyped-def]
        for op in self._ops:
            kind = op[0]
            if kind == "rpush":
                self._redis.buffers.setdefault(op[1], []).append(op[2])
            elif kind == "ltrim":
                start = int(op[2])
                end = None if op[3] == "-1" else int(op[3])
                items = self._redis.buffers.get(op[1], [])
                self._redis.buffers[op[1]] = items[start:] if end is None else items[start : end + 1]
            elif kind == "publish":
                self._redis.channel_msgs[op[1]].append(op[2])


class _FakeRedis:
    def __init__(self) -> None:
        self.buffers: dict[str, list[str]] = {}
        self.channel_msgs: dict[str, list[str]] = defaultdict(list)

    async def rpush(self, key: str, raw: str) -> None:
        self.buffers.setdefault(key, []).append(raw)

    async def ltrim(self, key: str, start: int, end: int) -> None:
        items = self.buffers.get(key, [])
        self.buffers[key] = items[start:] if end == -1 else items[start : end + 1]

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self.buffers.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)

    async def publish(self, channel: str, raw: str) -> None:
        self.channel_msgs[channel].append(raw)

    def pubsub(self) -> _FakePubSub:
        return _FakePubSub("evtchan:test", self.channel_msgs)


@pytest.fixture()
def redis_bus() -> tuple[TraceEventBus, _FakeRedis]:
    bus = TraceEventBus()
    fake = _FakeRedis()
    bus._redis = fake  # type: ignore[attr-defined]
    return bus, fake


async def _drain(queue: asyncio.Queue, n: int, timeout: float = 1.0) -> list[dict]:
    out: list[dict] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while len(out) < n and asyncio.get_event_loop().time() < deadline:
        with contextlib.suppress(TimeoutError):
            out.append(await asyncio.wait_for(queue.get(), timeout=0.2))
    return out


@pytest.mark.asyncio
async def test_redis_publish_buffers_and_publishes_channel(redis_bus):
    bus, fake = redis_bus
    await bus.publish("test", {"type": "text_delta", "text": "a"})
    await bus.publish("test", {"type": "text_delta", "text": "b"})

    assert len(fake.buffers["evt:test"]) == 2
    assert len(fake.channel_msgs["evtchan:test"]) == 2
    # 事件带去重 uuid
    first = json.loads(fake.buffers["evt:test"][0])
    assert "event_uuid" in first


@pytest.mark.asyncio
async def test_redis_subscribe_replays_buffer(redis_bus):
    bus, fake = redis_bus
    for i in range(3):
        await bus.publish("test", {"type": "text_delta", "text": str(i)})

    queue = await bus.subscribe("test")
    events = await _drain(queue, 3)
    assert [e["text"] for e in events] == ["0", "1", "2"]
    await bus.unsubscribe("test", queue)


@pytest.mark.asyncio
async def test_redis_live_delivery_and_dedup(redis_bus):
    """事件经本地 fanout + Redis 双路径投递时只到达一次, uuid 去重。"""
    bus, fake = redis_bus
    queue = await bus.subscribe("test")

    await bus.publish("test", {"type": "text_delta", "text": "hi"})
    await asyncio.sleep(0.05)  # 让 pubsub listener 处理

    events = await _drain(queue, 1)
    assert len(events) == 1
    assert events[0]["text"] == "hi"
    await bus.unsubscribe("test", queue)


@pytest.mark.asyncio
async def test_redis_buffer_capped(redis_bus):
    bus, fake = redis_bus
    for i in range(_REDIS_BUFFER_CAP + 50):
        await bus.publish("test", {"type": "text_delta", "text": str(i)})
    assert len(fake.buffers["evt:test"]) == _REDIS_BUFFER_CAP


@pytest.mark.asyncio
async def test_in_memory_mode_without_redis_still_works():
    """无 Redis 时保持纯内存行为, 无缓冲无 pubsub。"""
    bus = TraceEventBus()
    queue = await bus.subscribe("mem")
    await bus.publish("mem", {"type": "text_delta", "text": "x"})
    event = await asyncio.wait_for(queue.get(), timeout=0.5)
    assert event["text"] == "x"
    await bus.unsubscribe("mem", queue)

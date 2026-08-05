"""用于开发者模式 SSE 追踪推送的内存事件总线。

提供 ``TraceEventBus``——一个基于 asyncio.Queue 的轻量级发布/订阅，将追踪
事件扇出（一个 ``trace_id`` → 多个 SSE 订阅者队列）。总线是进程本地的：每个
订阅者持有一个 ``asyncio.Queue``，并在 SSE 处理器内通过 ``get_nowait`` /
``await get`` 排空它。当队列填满时（客户端慢或已断开），事件会被丢弃并记录
警告，因此生产者永远不会阻塞。

用法::

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
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# 模块级单例（由 ``get_event_bus`` 惰性初始化）。
_event_bus: TraceEventBus | None = None


class TraceEventBus:
    """基于 asyncio.Queue 的发布/订阅，将追踪事件扇出到 SSE 订阅者。

    每个 ``trace_id`` 映射到一个 ``asyncio.Queue`` 实例列表——每个活跃的
    SSE 连接一个。生产者调用 ``publish`` 将事件扇出到每个订阅者；消费者在
    SSE 处理器内排空自己的队列。

    当订阅者的队列已满时（客户端慢），``publish`` 会丢弃事件并记录警告，
    而不是阻塞生产者。
    """

    def __init__(self, max_queue_size: int = 100) -> None:
        self._subscribers: defaultdict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(
            list
        )
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size

    async def subscribe(self, trace_id: str) -> asyncio.Queue[dict[str, Any]]:
        """为 ``trace_id`` 注册一个新的订阅者队列并返回它。

        返回的队列受 ``max_queue_size`` 限制，因此慢消费者不会在内存中
        积累无界的事件。
        """
        async with self._lock:
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
                maxsize=self._max_queue_size
            )
            self._subscribers[trace_id].append(queue)
            return queue

    async def unsubscribe(self, trace_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """移除 ``trace_id`` 对应的特定订阅者队列。

        如果移除后订阅者列表变为空，则完全删除 ``trace_id`` 键，使
        ``_subscribers`` 不会积累过期的空列表。
        """
        async with self._lock:
            queues = self._subscribers.get(trace_id)
            if queues and queue in queues:
                queues.remove(queue)
                if not queues:
                    del self._subscribers[trace_id]

    async def publish(self, trace_id: str, event: dict[str, Any]) -> None:
        """将 ``event`` 扇出到 ``trace_id`` 的每个订阅者。

        使用 ``put_nowait``，因此队列已满时会丢弃事件并记录警告，而不是
        阻塞生产者。没有订阅者时为空操作。
        """
        # 无需加锁读取——在单个事件循环 tick 内迭代是原子的
        # （``put_nowait`` 是同步的，不会有 await 交错）。
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
        """删除 ``trace_id`` 的整个订阅者列表。

        当追踪结束（例如请求完成）时调用，一次性释放所有订阅者队列。
        """
        async with self._lock:
            self._subscribers.pop(trace_id, None)


def get_event_bus() -> TraceEventBus:
    """返回进程全局的 ``TraceEventBus`` 单例。

    在首次调用时惰性初始化，因此事件循环仅在真正需要总线时才会被触及
    （导入本模块不会创建一个）。
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = TraceEventBus()
    return _event_bus

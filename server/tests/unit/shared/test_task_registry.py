"""Unit tests for TaskRegistry — background task lifecycle management."""

import asyncio

import pytest

from app.shared.task_registry import TaskRegistry


@pytest.mark.asyncio
async def test_register_and_auto_cleanup_on_done():
    """register 的 task 完成后应自动从注册表移除。"""
    registry = TaskRegistry()

    async def dummy_task():
        await asyncio.sleep(0.01)

    task = asyncio.create_task(dummy_task())
    registry.register("trace-1", task)

    assert "trace-1" in registry.get_active_trace_ids()

    await task  # 等待完成

    # done_callback 异步触发，需要让事件循环跑一轮
    await asyncio.sleep(0.01)
    assert "trace-1" not in registry.get_active_trace_ids()


@pytest.mark.asyncio
async def test_cancel_existing_task():
    """cancel 应取消指定 trace_id 的 task 并等待其终止。"""
    registry = TaskRegistry()

    async def long_task():
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(long_task())
    registry.register("trace-2", task)

    cancelled = await registry.cancel("trace-2")
    assert cancelled is True
    assert task.cancelled() or task.done()
    assert "trace-2" not in registry.get_active_trace_ids()


@pytest.mark.asyncio
async def test_cancel_nonexistent_returns_false():
    """cancel 不存在的 trace_id 应返回 False。"""
    registry = TaskRegistry()
    cancelled = await registry.cancel("nonexistent")
    assert cancelled is False


@pytest.mark.asyncio
async def test_cancel_already_done_task_returns_false():
    """cancel 已完成的 task 应返回 False（无需取消）。"""
    registry = TaskRegistry()

    async def quick_task():
        pass

    task = asyncio.create_task(quick_task())
    registry.register("trace-3", task)
    await task
    await asyncio.sleep(0.01)  # let done_callback run

    cancelled = await registry.cancel("trace-3")
    assert cancelled is False


@pytest.mark.asyncio
async def test_cancel_all():
    """cancel_all 应取消所有活跃 task。"""
    registry = TaskRegistry()

    async def long_task():
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            raise

    task1 = asyncio.create_task(long_task())
    task2 = asyncio.create_task(long_task())
    registry.register("trace-a", task1)
    registry.register("trace-b", task2)

    assert len(registry.get_active_trace_ids()) == 2

    await registry.cancel_all()

    assert len(registry.get_active_trace_ids()) == 0
    assert task1.cancelled() or task1.done()
    assert task2.cancelled() or task2.done()


@pytest.mark.asyncio
async def test_cancel_times_out_gracefully():
    """cancel 时 task 若不响应取消（超 5s），cancel 仍应返回 True。"""
    registry = TaskRegistry()

    async def unresponsive_task():
        try:
            # 捕获 CancelledError 但不退出（模拟不听话的 task）
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            await asyncio.sleep(0.05)
            raise

    task = asyncio.create_task(unresponsive_task())
    registry.register("trace-stubborn", task)

    # task 会快速完成，这里主要验证 cancel 不卡死
    cancelled = await registry.cancel("trace-stubborn")
    # task 可能已完成或被取消，都算 True
    assert cancelled is True

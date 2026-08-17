"""Unit tests for task_queue graceful shutdown (robustness P0-1)."""

from __future__ import annotations

import threading
import time

import pytest

from app.infrastructure import task_queue
from app.infrastructure.task_queue import begin_shutdown, drain


@pytest.fixture(autouse=True)
def _reset_queue_state():
    """Isolate the module-level shutdown flag + thread set between tests."""
    task_queue._shutting_down = False
    with task_queue._threads_lock:
        task_queue._active_threads.clear()
    yield
    task_queue._shutting_down = False
    with task_queue._threads_lock:
        task_queue._active_threads.clear()


def test_begin_shutdown_blocks_new_tasks():
    """begin_shutdown 后新任务不再派发（返回 None，不启动线程）。"""
    begin_shutdown()

    def _noop() -> None:
        pass

    result = task_queue.enqueue_task(_noop)
    assert result is None
    with task_queue._threads_lock:
        assert task_queue._active_threads == set()


def test_drain_waits_for_inflight_threads():
    """drain 等待进行中的 daemon 线程完成并返回剩余数 0。"""
    done = threading.Event()

    def _slow() -> None:
        time.sleep(0.2)
        done.set()

    task_queue.enqueue_task(_slow)
    # 保证线程已启动
    with task_queue._threads_lock:
        assert len(task_queue._active_threads) == 1

    remaining = drain(timeout_s=2.0)
    assert remaining == 0
    assert done.is_set()


def test_drain_times_out_for_stubborn_thread():
    """drain 超时后返回仍存活的线程数（不永久阻塞）。"""
    stop = threading.Event()

    def _stubborn() -> None:
        stop.wait(5.0)  # 不响应退出

    task_queue.enqueue_task(_stubborn)
    t0 = time.monotonic()
    remaining = drain(timeout_s=0.5)
    elapsed = time.monotonic() - t0

    assert elapsed < 2.0  # 没有阻塞超过超时太多
    assert remaining >= 1
    stop.set()


def test_enqueue_task_still_works_before_shutdown():
    """未 shutdown 时正常派发。"""
    done = threading.Event()

    def _fast() -> None:
        done.set()

    result = task_queue.enqueue_task(_fast)
    assert result is not None
    assert done.wait(1.0)

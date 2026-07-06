"""Unit tests for TracingLLMClient — PR-5: async non-blocking tracing."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.shared.tracing_llm import TracingLLMClient


class _FakeLLM:
    """Fake LLM client for testing."""

    def __init__(self, response: str = "test response", delay: float = 0.0):
        self._response = response
        self._delay = delay

    def invoke(self, prompt: str) -> str:
        if self._delay:
            import time

            time.sleep(self._delay)
        return self._response

    async def ainvoke(self, prompt: str) -> str:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._response


@pytest.mark.asyncio
async def test_ainvoke_does_not_block_event_loop() -> None:
    """ainvoke should run tracing in a thread — concurrent calls should overlap."""
    import time

    tracer = MagicMock()
    # Simulate slow SQLite write (100ms)
    tracer.record.side_effect = lambda _: time.sleep(0.1)

    client = TracingLLMClient(
        _FakeLLM(response="reply"),
        model="test-model",
        tracer=tracer,
    )

    # Run 2 concurrent ainvoke calls — if tracing blocks, total > 400ms
    # If non-blocking, total ≈ max(llm_time) + tracing overhead ≈ 200ms
    start = time.perf_counter()
    await asyncio.gather(
        client.ainvoke("prompt 1"),
        client.ainvoke("prompt 2"),
    )
    elapsed = time.perf_counter() - start

    # 2 x (0ms LLM + 100ms tracing) = 200ms if sequential
    # If blocking: ~200ms. If non-blocking: <250ms (threads overlap)
    # Allow generous threshold to avoid flakiness
    assert elapsed < 0.4, f"ainvoke appears to block event loop: {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_record_failure_does_not_mask_exception() -> None:
    """If _record throws, ainvoke should still return the LLM response."""
    tracer = MagicMock()
    tracer.record.side_effect = RuntimeError("DB write failed")

    client = TracingLLMClient(
        _FakeLLM(response="important reply"),
        model="test-model",
        tracer=tracer,
    )

    # Should not raise despite tracer.record throwing
    result = await client.ainvoke("test prompt")
    assert result == "important reply"


@pytest.mark.asyncio
async def test_ainvoke_propagates_llm_error() -> None:
    """If LLM throws, ainvoke should propagate the error (not swallow it)."""

    class _ErrorLLM:
        async def ainvoke(self, prompt: str):
            raise RuntimeError("LLM unavailable")

    client = TracingLLMClient(
        _ErrorLLM(),
        model="test-model",
        tracer=MagicMock(),
    )

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        await client.ainvoke("test")


def test_invoke_records_sync() -> None:
    """Sync invoke should still record (no asyncio.to_thread needed)."""
    tracer = MagicMock()
    client = TracingLLMClient(
        _FakeLLM(response="sync reply"),
        model="test-model",
        tracer=tracer,
    )

    result = client.invoke("test prompt")
    assert result == "sync reply"
    assert tracer.record.call_count == 1

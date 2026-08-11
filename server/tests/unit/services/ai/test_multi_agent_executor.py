"""Tests for multi_agent_executor — run_multi_agent + streaming variant.

The streaming helper (``run_multi_agent_streaming``) is a *native* async
generator: unlike :func:`run_multi_agent` it does **not** wrap the graph call in
a ``ThreadPoolExecutor`` + ``asyncio.run``, so it is safe to await from inside
an already-running event loop (e.g. a FastAPI request handler).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.ai.multi_agent_executor import run_multi_agent_streaming


@pytest.mark.asyncio
async def test_run_multi_agent_streaming_yields_tokens() -> None:
    """run_multi_agent_streaming 应原生 async yield token(不用线程池)。"""
    mock_graph = MagicMock()

    async def mock_invoke_streaming(state: Any, *, workers: Any = None) -> Any:
        async def token_gen():
            for t in ["你", "好"]:
                yield t

        return MagicMock(), token_gen()

    mock_graph.invoke_streaming = mock_invoke_streaming

    tokens: list[str] = []
    async for token in run_multi_agent_streaming(graph=mock_graph, state=MagicMock()):
        tokens.append(token)

    assert tokens == ["你", "好"]


@pytest.mark.asyncio
async def test_run_multi_agent_streaming_passes_workers_through() -> None:
    """workers 关键字参数应透传给 graph.invoke_streaming。"""
    mock_graph = MagicMock()
    captured: dict[str, Any] = {}

    async def mock_invoke_streaming(state: Any, *, workers: Any = None) -> Any:
        captured["workers"] = workers

        async def token_gen():
            if False:  # pragma: no cover - keep it an async generator
                yield ""

        return MagicMock(), token_gen()

    mock_graph.invoke_streaming = mock_invoke_streaming

    workers = {"empathy": MagicMock()}
    async for _ in run_multi_agent_streaming(
        graph=mock_graph, state=MagicMock(), workers=workers
    ):
        pass

    assert captured["workers"] is workers

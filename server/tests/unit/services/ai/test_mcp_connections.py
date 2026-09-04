"""Unit tests for MCP connections: shared loop, stdio lifecycle, restart."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.mcp_config import StdioSpec
from app.services.ai.mcp_connections import (
    McpCallError,
    McpLoop,
    McpTimeoutError,
    StdioMcpConnection,
)

SCRIPT = Path(__file__).parents[3] / "fixtures" / "fake_mcp_stdio.py"


@pytest.fixture()
def mcp_loop():
    loop = McpLoop()
    loop.start()
    yield loop
    loop.stop()


def _stdio_conn(loop: McpLoop, *script_args: str, **kwargs: object) -> StdioMcpConnection:
    kwargs.setdefault("restart_backoff_s", (0.05, 0.05, 0.05))
    kwargs.setdefault("call_timeout_s", 10.0)
    spec = StdioSpec(command=sys.executable, args=(str(SCRIPT), *script_args))
    return StdioMcpConnection("fake", spec, loop, **kwargs)  # type: ignore[arg-type]


class TestMcpLoop:
    def test_run_coro_executes_on_background_loop(self, mcp_loop: McpLoop) -> None:
        import asyncio

        async def _probe() -> int:
            loop_id = id(asyncio.get_running_loop())
            return loop_id

        assert mcp_loop.run_coro(_probe(), timeout=5.0) == id(mcp_loop._loop)

    def test_stop_then_run_raises(self, mcp_loop: McpLoop) -> None:
        mcp_loop.stop()
        import asyncio

        async def _noop() -> None:
            return None

        with pytest.raises(McpCallError):
            mcp_loop.run_coro(_noop(), timeout=1.0)


class TestStdioConnection:
    def test_roundtrip(self, mcp_loop: McpLoop) -> None:
        conn = _stdio_conn(mcp_loop)
        assert conn.connect() is True
        assert conn.state == "healthy"
        tools = conn.list_tools()
        assert [t.name for t in tools] == ["echo", "fail"]
        assert conn.call_tool("echo", {"text": "hi"}) == "echo: hi"

    def test_spawn_failure_is_unhealthy(self, mcp_loop: McpLoop) -> None:
        spec = StdioSpec(command="definitely-not-a-command-xyz")
        conn = StdioMcpConnection("bad", spec, mcp_loop, restart_backoff_s=(0.05,))
        assert conn.connect() is False
        assert conn.state == "unhealthy"
        assert conn.last_error

    def test_restart_after_server_crash(self, mcp_loop: McpLoop) -> None:
        conn = _stdio_conn(mcp_loop, "1")  # server dies after 1 tool call
        assert conn.connect() is True
        assert conn.call_tool("echo", {"text": "a"}) == "echo: a"
        # The server has exited; the next call must restart and retry.
        assert conn.call_tool("echo", {"text": "b"}) == "echo: b"
        assert conn.restart_count == 1

    def test_timeout_raises_after_restart_retry(self, mcp_loop: McpLoop) -> None:
        conn = _stdio_conn(mcp_loop, "999999", "30")  # sleeps 30s per call
        conn._call_timeout_s = 0.5
        assert conn.connect() is True
        with pytest.raises(McpTimeoutError):
            conn.call_tool("echo", {"text": "slow"})

    def test_close_then_call_raises_when_no_backoff(self, mcp_loop: McpLoop) -> None:
        conn = _stdio_conn(mcp_loop, restart_backoff_s=())
        assert conn.connect() is True
        conn.close()
        assert conn.state == "unhealthy"
        with pytest.raises(McpCallError):
            conn.call_tool("echo", {"text": "x"})


class TestSseConnection:
    def test_connect_and_call_with_mocks(self, mcp_loop: McpLoop) -> None:
        from app.services.ai.mcp_connections import SseMcpConnection

        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="hello")]
        mock_session.call_tool = AsyncMock(return_value=mock_resp)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("mcp.client.sse.sse_client", return_value=mock_cm),
            patch("mcp.ClientSession", return_value=mock_session),
        ):
            conn = SseMcpConnection("fake", "http://localhost:9201/sse", mcp_loop)
            assert conn.connect() is True
            assert conn.call_tool("search", {"query": "q"}) == "hello"
            conn.close()
            mock_session.__aexit__.assert_awaited()

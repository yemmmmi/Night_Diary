"""Unit tests for PersistentMCPConnection — fixes the session closure bug."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.mcp_persistent import PersistentMCPConnection


@pytest.mark.asyncio
async def test_connect_initializes_session():
    """connect() 应建立 session 并调用 initialize()。"""
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_session.call_tool = AsyncMock()
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm),
        patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session),
    ):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()

        mock_cm.__aenter__.assert_called_once()
        mock_session.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_call_tool_after_connect():
    """connect 后调用 call_tool 应委托给 session。"""
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_resp = MagicMock()
    mock_session.call_tool = AsyncMock(return_value=mock_resp)
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm),
        patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session),
    ):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()

        result = await conn.call_tool("search", {"query": "test"})
        mock_session.call_tool.assert_called_once_with("search", {"query": "test"})
        assert result is mock_resp


@pytest.mark.asyncio
async def test_call_tool_before_connect_raises():
    """未 connect 就调用 call_tool 应抛 RuntimeError。"""
    conn = PersistentMCPConnection("http://localhost:8081/sse")
    with pytest.raises(RuntimeError, match="Not connected"):
        await conn.call_tool("search", {})


@pytest.mark.asyncio
async def test_close_releases_session():
    """close() 应关闭 session 和 context manager。"""
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_session.call_tool = AsyncMock()
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm),
        patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session),
    ):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()
        await conn.close()

        mock_session.close.assert_called_once()
        mock_cm.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_close_is_idempotent():
    """多次调用 close() 不应抛异常。"""
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm),
        patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session),
    ):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()
        await conn.close()
        await conn.close()  # 不抛


@pytest.mark.asyncio
async def test_session_survives_after_async_context_exit():
    """核心 bug 修复：session 在 connect 后必须持续可用。

    这是 tool_factory.py 中 async with 退出后 session 失效 bug 的
    回归测试。
    """
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_session.call_tool = AsyncMock(return_value=MagicMock())
    mock_session.close = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.ai.mcp_persistent.sse_client", return_value=mock_cm),
        patch("app.services.ai.mcp_persistent.ClientSession", return_value=mock_session),
    ):
        conn = PersistentMCPConnection("http://localhost:8081/sse")
        await conn.connect()

        # 模拟 tool_factory.py 的场景：发现工具后，多次调用
        for i in range(3):
            await conn.call_tool(f"tool_{i}", {})

        # session.call_tool 应被调用 3 次，全部成功
        assert mock_session.call_tool.call_count == 3

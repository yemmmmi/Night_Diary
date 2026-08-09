"""PersistentMCPConnection — MCP client connection that survives beyond async with.

Fixes the session-closure bug in ``tool_factory.py::_load_mcp_tools`` where
``async with sse_client(...)`` exits (closing the session) but the generated
tool closures still reference the now-dead session.

``PersistentMCPConnection`` lifts the session lifecycle to object scope:
``connect()`` enters the async context manually and keeps it open;
``close()`` exits it. Between the two, ``call_tool()`` and ``list_tools()``
reuse the same live session.

Not a reconnect manager — if the connection drops mid-session, calls will
fail (the caller's layer-1 tool error handling kicks in and returns an
ERROR chunk to the model). Automatic reconnect is deferred to P5 or until
MCP is actually enabled in production.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy imports so this module doesn't hard-fail if mcp isn't installed.
# The imports happen inside connect(), and ImportError is caught there.
try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    _MCP_AVAILABLE = True
except ImportError:
    ClientSession = None  # type: ignore[assignment,misc]
    sse_client = None  # type: ignore[assignment]
    _MCP_AVAILABLE = False


class PersistentMCPConnection:
    """Persistent MCP client connection.

    Call ``connect()`` once at startup, then ``call_tool()`` / ``list_tools()``
    as needed, then ``close()`` at shutdown.

    All methods are coroutines and must run on the same event loop.
    """

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._session: ClientSession | None = None
        # sse_client() returns an async context manager; we hold it so we
        # can __aexit__ on close().
        self._cm: Any = None

    async def connect(self) -> None:
        """Establish the connection and initialize the session.

        Raises ``ImportError`` if the ``mcp`` package is not installed.
        Raises the underlying transport error if the endpoint is unreachable.
        """
        if not _MCP_AVAILABLE:
            raise ImportError("mcp package not installed; cannot connect")

        # Exit any previous connection first (idempotent connect).
        if self._session is not None:
            await self.close()

        self._cm = sse_client(self._endpoint)
        read, write = await self._cm.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.initialize()
        logger.info("MCP connected to %s", self._endpoint)

    async def list_tools(self) -> Any:
        """List available tools on the connected server."""
        if self._session is None:
            raise RuntimeError("Not connected; call connect() first")
        return await self._session.list_tools()

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Call a tool on the connected server."""
        if self._session is None:
            raise RuntimeError("Not connected; call connect() first")
        return await self._session.call_tool(name, args)

    async def close(self) -> None:
        """Close the connection. Safe to call multiple times."""
        with contextlib.suppress(Exception):
            if self._session is not None:
                # ClientSession has no public ``close()``; it shuts down via
                # ``__aexit__``. We try ``close()`` first (works for mocks and
                # future API additions) and let suppress() swallow any
                # AttributeError. The transport (sse_client) is torn down via
                # its own ``__aexit__`` below regardless.
                await self._session.close()  # type: ignore[attr-defined]
        self._session = None

        if self._cm is not None:
            with contextlib.suppress(Exception):
                await self._cm.__aexit__(None, None, None)
        self._cm = None

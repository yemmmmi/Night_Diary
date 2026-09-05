"""MCP transport connections: shared background event loop + SSE/stdio clients.

The ``mcp`` SDK is asyncio-only while agent tool functions are synchronous
(``ToolFn = Callable[..., str]``), so every MCP connection marshals its async
work onto one dedicated background event loop (:class:`McpLoop`). A single
long-lived loop also avoids the "session created on loop A, used on loop B"
failure mode of ``asyncio.run`` per call.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CALL_TIMEOUT_S = 30.0
DEFAULT_CONNECT_TIMEOUT_S = 15.0
DEFAULT_RESTART_BACKOFF_S = (1.0, 2.0, 4.0)


class McpCallError(Exception):
    """MCP tool call failed (after retries)."""


class McpTimeoutError(McpCallError):
    """MCP tool call exceeded its timeout."""


class McpLoop:
    """Background asyncio event loop shared by all MCP connections."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="nd-mcp-loop", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run_coro(self, coro: Any, *, timeout: float) -> Any:
        """Run a coroutine on the background loop, blocking up to ``timeout``."""
        if self._loop is None or self._thread is None or not self._thread.is_alive():
            with contextlib.suppress(Exception):
                coro.close()
            raise McpCallError("MCP loop not running")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except TimeoutError as exc:
            future.cancel()
            raise McpTimeoutError(f"timed out after {timeout}s") from exc

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._loop = None
        self._thread = None


def datetime_utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


class McpConnection:
    """One MCP server endpoint with health state and restart-on-failure.

    Shared-process model: each endpoint keeps ONE connection for all users;
    callers pass ``user_id`` through the tool layer for per-call logging.
    """

    transport = "sse"

    def __init__(
        self,
        alias: str,
        loop: McpLoop,
        *,
        call_timeout_s: float = DEFAULT_CALL_TIMEOUT_S,
        connect_timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S,
        restart_backoff_s: tuple[float, ...] = DEFAULT_RESTART_BACKOFF_S,
    ) -> None:
        self.alias = alias
        self.loop = loop
        self.state = "unhealthy"  # healthy | unhealthy | dead
        self.restart_count = 0
        self.last_error = ""
        self.loaded_at = ""
        self.tool_count = 0
        self._call_timeout_s = call_timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._restart_backoff_s = restart_backoff_s
        self._session: Any = None
        self._cm: Any = None

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> bool:
        """Best-effort connect (also used for lazy recovery of dead endpoints)."""
        self._close_session()
        try:
            self._session = self.loop.run_coro(self._connect(), timeout=self._connect_timeout_s)
        except Exception as exc:
            self._close_session()
            self.state = "unhealthy"
            self.last_error = str(exc)
            logger.warning("MCP connect %s (%s) failed: %s", self.alias, self.transport, exc)
            return False
        self.state = "healthy"
        self.last_error = ""
        self.loaded_at = datetime_utc_now_iso()
        return True

    def _connect(self) -> Any:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    def _close_session(self) -> None:
        session, self._session = self._session, None
        cm, self._cm = self._cm, None
        if session is not None:
            with contextlib.suppress(Exception):
                # mcp 2.0 sessions shut down via __aexit__ (no public close()).
                self.loop.run_coro(session.__aexit__(None, None, None), timeout=5.0)
        if cm is not None:
            with contextlib.suppress(Exception):
                self.loop.run_coro(cm.__aexit__(None, None, None), timeout=5.0)

    def close(self) -> None:
        self._close_session()
        self.state = "unhealthy"

    # -- tools -------------------------------------------------------------

    def list_tools(self) -> list[Any]:
        if self._session is None:
            raise McpCallError(f"{self.alias}: not connected")
        result = self.loop.run_coro(self._session.list_tools(), timeout=self._connect_timeout_s)
        return list(result.tools)

    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        """Call once; on failure restart with backoff and retry once."""
        try:
            return self._call_once(name, args)
        except Exception as exc:
            logger.warning("MCP call %s/%s failed (%s); restarting", self.alias, name, exc)
        if not self._restart_with_backoff():
            raise McpCallError(
                f"MCP endpoint {self.alias} unavailable: {self.last_error}"
            ) from None
        return self._call_once(name, args)

    def _call_once(self, name: str, args: dict[str, Any]) -> str:
        if self._session is None:
            raise McpCallError(f"{self.alias}: not connected")
        resp = self.loop.run_coro(
            self._session.call_tool(name, args), timeout=self._call_timeout_s
        )
        texts = [c.text for c in getattr(resp, "content", []) if hasattr(c, "text")]
        return "\n".join(texts) if texts else str(resp)

    def _restart_with_backoff(self) -> bool:
        for delay in self._restart_backoff_s:
            self._close_session()
            time.sleep(delay)
            if self.connect():
                self.restart_count += 1
                return True
        self.state = "dead"
        self._close_session()
        return False


class SseMcpConnection(McpConnection):
    """HTTP/SSE transport — no child process to manage."""

    transport = "sse"

    def __init__(self, alias: str, url: str, loop: McpLoop, **kwargs: Any) -> None:
        super().__init__(alias, loop, **kwargs)
        self.url = url

    async def _connect(self) -> Any:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        cm = sse_client(self.url)
        read, write = await cm.__aenter__()
        self._cm = cm
        session = ClientSession(read, write)
        await session.__aenter__()
        try:
            await session.initialize()
        except BaseException:
            with contextlib.suppress(Exception):
                await session.__aexit__(None, None, None)
            raise
        return session


class StdioMcpConnection(McpConnection):
    """stdio transport — the ``mcp`` SDK spawns and owns the child process."""

    transport = "stdio"

    def __init__(self, alias: str, spec: Any, loop: McpLoop, **kwargs: Any) -> None:
        super().__init__(alias, loop, **kwargs)
        self.spec = spec

    async def _connect(self) -> Any:
        import os

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = {**os.environ, **self.spec.env} if self.spec.env else None
        params = StdioServerParameters(
            command=self.spec.command, args=list(self.spec.args), env=env
        )
        cm = stdio_client(params)
        read, write = await cm.__aenter__()
        self._cm = cm
        session = ClientSession(read, write)
        await session.__aenter__()
        try:
            await session.initialize()
        except BaseException:
            with contextlib.suppress(Exception):
                await session.__aexit__(None, None, None)
            raise
        return session

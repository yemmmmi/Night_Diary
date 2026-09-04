"""Unified tool registry: built-in local tools + MCP remote tools.

Single source of truth for "what can the agent use". Local tools are rebuilt
per request (they bind ``user_id``); MCP connections are shared globally
(shared-process model) with per-call ``user_id`` logging.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.infrastructure.mcp_call_tracer import McpCallRecord, McpCallTracer
from app.services.ai.mcp_config import parse_endpoints, parse_stdios
from app.services.ai.mcp_connections import (
    McpCallError,
    McpLoop,
    McpTimeoutError,
    SseMcpConnection,
    StdioMcpConnection,
)
from app.services.ai.tool_factory import (
    ToolFn,
    build_tool_map,
    namespaced_tool_name,
    register_dynamic_specs,
)
from app.shared.pipeline_trace import get_trace, trace_span
from app.shared.tool_protocol import ToolSpec

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

SNAPSHOT_RESULT_CHARS = 512


@dataclass(frozen=True, slots=True)
class _McpToolEntry:
    alias: str
    raw_name: str
    spec: ToolSpec


class ToolRegistry:
    """Registry of all agent tools (local built-in + MCP remote)."""

    def __init__(self, container: ServiceContainer, settings: Any) -> None:
        self._container = container
        self._settings = settings
        self._loop = McpLoop()
        self._connections: dict[str, Any] = {}
        self._mcp_tools: dict[str, _McpToolEntry] = {}
        self._tracer: McpCallTracer | None = None

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None:
        self._loop.start()
        self._tracer = McpCallTracer(self._container.session_factory)
        for alias, url in parse_endpoints(self._settings.mcp_endpoints).items():
            self.register_connection(SseMcpConnection(alias, url, self._loop))
        for alias, spec in parse_stdios(self._settings.mcp_stdios).items():
            self.register_connection(StdioMcpConnection(alias, spec, self._loop))

    def register_connection(self, conn: Any) -> None:
        """Register + connect one MCP endpoint (best-effort, isolated)."""
        self._connections[conn.alias] = conn
        if not conn.connect():
            return
        self._sync_tools(conn)

    def close(self) -> None:
        for conn in self._connections.values():
            with contextlib.suppress(Exception):
                conn.close()
        self._loop.stop()

    # -- tool discovery ----------------------------------------------------

    def _sync_tools(self, conn: Any) -> None:
        # Drop stale entries of this alias before re-registering.
        for name in [n for n, e in self._mcp_tools.items() if e.alias == conn.alias]:
            del self._mcp_tools[name]
        try:
            tools = conn.list_tools()
        except Exception as exc:
            conn.state = "unhealthy"
            conn.last_error = str(exc)
            logger.warning("MCP list_tools %s failed: %s", conn.alias, exc)
            return
        conn.tool_count = len(tools)
        specs: dict[str, ToolSpec] = {}
        for tool in tools:
            full = namespaced_tool_name(conn.alias, tool.name)
            if full in self._mcp_tools:
                logger.warning("Duplicate MCP tool name %s skipped", full)
                continue
            schema = getattr(tool, "inputSchema", None) or {
                "type": "object",
                "properties": {},
            }
            spec = ToolSpec(
                name=full,
                description=getattr(tool, "description", "") or full,
                parameters=schema,
            )
            self._mcp_tools[full] = _McpToolEntry(conn.alias, tool.name, spec)
            specs[full] = spec
        register_dynamic_specs(specs)

    def _recover_unhealthy(self) -> None:
        """Lazy recovery: one reconnect attempt per unhealthy/dead endpoint."""
        for conn in self._connections.values():
            if conn.state == "healthy":
                continue
            if conn.connect():
                self._sync_tools(conn)

    # -- agent-facing API ---------------------------------------------------

    def build_tool_map(self, *, user_id: str = "default") -> dict[str, ToolFn] | None:
        """Per-request tool map: local tools (user-bound) + MCP tools."""
        self._recover_unhealthy()
        llm = self._container._llm_for_tier("light", agent_name="tool")
        retriever = self._container.retriever
        if llm is None or retriever is None:
            return None
        tools = build_tool_map(
            self._container.session_factory,
            retriever=retriever,
            llm=llm,
            user_id=user_id,
        )
        for name in self._mcp_tools:
            tools[name] = self._make_mcp_fn(name, user_id=user_id)
        return tools

    def _make_mcp_fn(self, name: str, *, user_id: str) -> ToolFn:
        def _call(**kwargs: Any) -> str:
            return self.call_mcp(name, kwargs, user_id=user_id)

        return _call

    def call_mcp(self, name: str, args: dict[str, Any], *, user_id: str) -> str:
        """One MCP tool call: S8_mcp span + mcp_call_logs row + error string."""
        entry = self._mcp_tools.get(name)
        if entry is None:
            return f"[{name}]: 未知工具"
        conn = self._connections[entry.alias]
        started = time.perf_counter()
        metadata: dict[str, Any] = {
            "endpoint_alias": entry.alias,
            "transport": conn.transport,
            "raw_tool_name": entry.raw_name,
            "restart_count": conn.restart_count,
        }
        result_text = ""
        error_message: str | None = None
        status = "success"
        with trace_span(
            "S8_mcp",
            f"MCP {entry.raw_name}",
            input_snapshot=dict(args),
            metadata=metadata,
        ) as span:
            try:
                result_text = conn.call_tool(entry.raw_name, args)
            except McpTimeoutError as exc:
                status = "timeout"
                error_message = str(exc)
                result_text = f"[{name} error]: {exc}"
            except McpCallError as exc:
                status = "error"
                error_message = str(exc)
                result_text = f"[{name} error]: {exc}"
            except Exception as exc:  # noqa: BLE001 — tool layer never raises
                status = "error"
                error_message = str(exc)
                result_text = f"[{name} error]: {exc}"
            if span:
                span.output_snapshot = result_text[:SNAPSHOT_RESULT_CHARS]
        self._record(
            user_id=user_id,
            entry=entry,
            transport=conn.transport,
            status=status,
            duration_ms=(time.perf_counter() - started) * 1000,
            error_message=error_message,
            args=args,
            result_text=result_text,
            span_id=span.span_id if span else "",
        )
        return result_text

    def _record(
        self,
        *,
        user_id: str,
        entry: _McpToolEntry,
        transport: str,
        status: str,
        duration_ms: float,
        error_message: str | None,
        args: dict[str, Any],
        result_text: str,
        span_id: str,
    ) -> None:
        if self._tracer is None:
            return
        trace = get_trace()
        self._tracer.record(
            McpCallRecord(
                user_id=user_id,
                trace_id=trace.trace_id if trace else None,
                span_id=span_id,
                endpoint_alias=entry.alias,
                transport=transport,
                tool_name=namespaced_tool_name(entry.alias, entry.raw_name),
                raw_tool_name=entry.raw_name,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
                arguments_snapshot=json.dumps(args, ensure_ascii=False, default=str),
                result_snapshot=result_text,
            )
        )

    # -- Dev API read models -------------------------------------------------

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "alias": conn.alias,
                "transport": conn.transport,
                "state": conn.state,
                "tool_count": conn.tool_count,
                "restart_count": conn.restart_count,
                "last_error": conn.last_error,
                "loaded_at": conn.loaded_at,
            }
            for conn in self._connections.values()
        ]

    def tools_listing(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": entry.spec.description,
                "source": entry.alias,
                "transport": self._connections[entry.alias].transport,
            }
            for name, entry in self._mcp_tools.items()
        ]

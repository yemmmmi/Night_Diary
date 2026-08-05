"""MCP server — exposes the existing tools over the Model Context Protocol.

This lets external MCP clients (e.g. Claude Desktop, other AI agents)
discover and call the diary tools through a standardised protocol.

The server wraps the same ``ToolFn`` callables from ``tool_factory.py``, so
behaviour is identical to in-process tool calls. Two transports:
- stdio: for local CLI clients
- SSE:   for remote HTTP clients

Usage:
    python -m app.infrastructure.mcp_server --transport stdio
    python -m app.infrastructure.mcp_server --transport sse --port 8080
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from app.shared.tool_protocol import ToolSpec

logger = logging.getLogger(__name__)


def _specs_to_mcp_tools(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    """Convert the internal ``ToolSpec`` list into MCP tool definitions."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": spec.parameters,
        }
        for spec in specs
    ]


class MCPServer:
    """Wrap the existing tool factory into an MCP-compatible server.

    The core logic (``list_tools``/``call_tool``) is decoupled from the MCP
    library so it can be tested independently. The transport methods
    (``run_stdio``/``run_sse``) handle the low-level MCP protocol connections.
    """

    def __init__(self, container: Any, *, user_id: str = "default") -> None:
        self._container = container
        self._user_id = user_id
        self._tools: dict[str, Any] = {}
        self._specs: list[ToolSpec] = []

    def initialize(self) -> None:
        """Build the tool map and specs.

        Uses the container's session_factory so tools open short-lived
        sessions on demand — no long-held DB connection during tool calls.
        """
        from app.services.ai.tool_factory import build_tool_map, build_tool_specs

        self._container.ensure_ai_stack(user_id=self._user_id)
        if self._container.retriever is None:
            raise RuntimeError("Retriever unavailable — AI stack not initialized")
        llm = self._container._llm_for_tier("light", agent_name="mcp_tool")
        self._tools = build_tool_map(
            self._container.session_factory,
            retriever=self._container.retriever,
            llm=llm or self._container.llm_factory.create_default(),
            user_id=self._user_id,
        )
        self._specs = build_tool_specs()

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the MCP-format tool definitions."""
        return _specs_to_mcp_tools(self._specs)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool by name with the given arguments."""
        fn = self._tools.get(name)
        if fn is None:
            return f"Unknown tool: {name}"
        try:
            return str(fn(**arguments))
        except Exception as exc:
            logger.error("MCP tool %s failed: %s", name, exc)
            return f"Tool {name} error: {exc}"

    def run_stdio(self) -> None:
        """Run the MCP server over stdio transport."""
        try:
            from mcp.server import Server
            from mcp.server.stdio import stdio_server
            from mcp.types import (
                CallToolRequestParams,
                CallToolResult,
                ListToolsResult,
                PaginatedRequestParams,
                TextContent,
                Tool,
            )
        except ImportError:
            logger.error("mcp package not installed; run: pip install mcp")
            return

        async def list_tools(
            ctx: Any, params: PaginatedRequestParams | None
        ) -> ListToolsResult:
            del ctx, params  # protocol handler; request metadata not needed
            return ListToolsResult(
                tools=[
                    Tool(
                        name=spec.name,
                        description=spec.description,
                        input_schema=spec.parameters,
                    )
                    for spec in self._specs
                ]
            )

        async def call_tool(ctx: Any, params: CallToolRequestParams) -> CallToolResult:
            del ctx
            result = self.call_tool(params.name, params.arguments or {})
            return CallToolResult(content=[TextContent(type="text", text=result)])

        server = Server(
            "night-diary",
            on_list_tools=list_tools,
            on_call_tool=call_tool,
        )

        import asyncio

        async def _main() -> None:
            async with stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        asyncio.run(_main())

    def run_sse(self, *, port: int = 8080) -> None:
        """Run the MCP server over SSE transport (HTTP)."""
        try:
            import uvicorn
            from mcp.server import Server
            from mcp.server.sse import SseServerTransport
            from mcp.types import (
                CallToolRequestParams,
                CallToolResult,
                ListToolsResult,
                PaginatedRequestParams,
                TextContent,
                Tool,
            )
            from starlette.applications import Starlette
            from starlette.routing import Mount, Route
        except ImportError:
            logger.error("mcp/SSE deps not installed; run: pip install mcp uvicorn starlette")
            return

        async def list_tools(
            ctx: Any, params: PaginatedRequestParams | None
        ) -> ListToolsResult:
            del ctx, params  # protocol handler; request metadata not needed
            return ListToolsResult(
                tools=[
                    Tool(
                        name=spec.name,
                        description=spec.description,
                        input_schema=spec.parameters,
                    )
                    for spec in self._specs
                ]
            )

        async def call_tool(ctx: Any, params: CallToolRequestParams) -> CallToolResult:
            del ctx
            result = self.call_tool(params.name, params.arguments or {})
            return CallToolResult(content=[TextContent(type="text", text=result)])

        server = Server(
            "night-diary-sse",
            on_list_tools=list_tools,
            on_call_tool=call_tool,
        )
        sse = SseServerTransport("/messages/")

        async def handle_sse(request: Any) -> Any:
            async with sse.connect_sse(request.scope, request.receive, request._send) as (
                read,
                write,
            ):
                await server.run(read, write, server.create_initialization_options())

        app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ]
        )

        logger.info("MCP SSE server starting on port %d", port)
        uvicorn.run(app, host="0.0.0.0", port=port)


def main() -> None:
    """CLI entry point for the MCP server."""
    parser = argparse.ArgumentParser(description="Night Diary MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--user-id", default="default")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    from app.services.container import ServiceContainer

    container = ServiceContainer.create_core()
    server = MCPServer(container, user_id=args.user_id)

    server.initialize()

    if args.transport == "stdio":
        server.run_stdio()
    else:
        server.run_sse(port=args.port)


if __name__ == "__main__":
    main()

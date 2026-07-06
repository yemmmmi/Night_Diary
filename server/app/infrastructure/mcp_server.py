"""MCP Server — exposes existing tools via the Model Context Protocol.

This allows external MCP clients (e.g. Claude Desktop, other AI agents) to
discover and invoke the diary tools through a standardized protocol.

The server wraps the same ToolFn callables from tool_factory.py, so behavior
is identical to the in-process tool calls. Two transport modes:
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
    """Convert internal ToolSpec list to MCP tool definitions."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": spec.parameters,
        }
        for spec in specs
    ]


class MCPServer:
    """Wraps the existing tool factory as an MCP-compatible server.

    The core logic (``list_tools``/``call_tool``) is decoupled from the MCP
    library so it can be tested independently. Transport methods
    (``run_stdio``/``run_sse``) handle the MCP protocol wiring.
    """

    def __init__(self, container: Any, *, user_id: str = "default") -> None:
        self._container = container
        self._user_id = user_id
        self._tools: dict[str, Any] = {}
        self._specs: list[ToolSpec] = []

    def initialize(self, db_session: Any) -> None:
        """Build the tool map and specs (requires a DB session)."""
        from app.services.ai.tool_factory import build_tool_map, build_tool_specs

        self._container.ensure_ai_stack(user_id=self._user_id)
        if self._container.retriever is None:
            raise RuntimeError("Retriever unavailable — AI stack not initialized")
        llm = self._container._llm_for_tier(db_session, "light", agent_name="mcp_tool")
        self._tools = build_tool_map(
            db_session,
            retriever=self._container.retriever,
            llm=llm or self._container.llm_factory.create_default(),
            user_id=self._user_id,
        )
        self._specs = build_tool_specs()

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP-formatted tool definitions."""
        return _specs_to_mcp_tools(self._specs)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Invoke a tool by name with the given arguments."""
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
            from mcp.types import TextContent, Tool
        except ImportError:
            logger.error("mcp package not installed; run: pip install mcp")
            return

        server = Server("night-diary")

        @server.list_tools()  # type: ignore[untyped-decorator]
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name=spec.name,
                    description=spec.description,
                    inputSchema=spec.parameters,
                )
                for spec in self._specs
            ]

        @server.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            result = self.call_tool(name, arguments)
            return [TextContent(type="text", text=result)]

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
            from starlette.applications import Starlette
            from starlette.routing import Mount, Route
        except ImportError:
            logger.error("mcp/SSE deps not installed; run: pip install mcp uvicorn starlette")
            return

        server = Server("night-diary-sse")
        sse = SseServerTransport("/messages/")

        @server.list_tools()  # type: ignore[untyped-decorator]
        async def list_tools() -> list[Any]:
            from mcp.types import Tool

            return [
                Tool(
                    name=spec.name,
                    description=spec.description,
                    inputSchema=spec.parameters,
                )
                for spec in self._specs
            ]

        @server.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
            from mcp.types import TextContent

            result = self.call_tool(name, arguments)
            return [TextContent(type="text", text=result)]

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

    with container.session() as db:
        server.initialize(db)

    if args.transport == "stdio":
        server.run_stdio()
    else:
        server.run_sse(port=args.port)


if __name__ == "__main__":
    main()

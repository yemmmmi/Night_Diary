"""MCP 服务器 — 通过模型上下文协议暴露现有工具。

这允许外部 MCP 客户端（如 Claude Desktop、其他 AI 智能体）
通过标准化协议发现并调用日记工具。

该服务器包装了 tool_factory.py 中相同的 ToolFn 可调用对象，
因此行为与进程内工具调用完全一致。两种传输模式：
- stdio：用于本地 CLI 客户端
- SSE：  用于远程 HTTP 客户端

用法：
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
    """将内部 ToolSpec 列表转换为 MCP 工具定义。"""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": spec.parameters,
        }
        for spec in specs
    ]


class MCPServer:
    """将现有工具工厂包装为兼容 MCP 的服务器。

    核心逻辑（``list_tools``/``call_tool``）与 MCP 库解耦，
    以便独立测试。传输方法（``run_stdio``/``run_sse``）
    处理 MCP 协议的底层连接。
    """

    def __init__(self, container: Any, *, user_id: str = "default") -> None:
        self._container = container
        self._user_id = user_id
        self._tools: dict[str, Any] = {}
        self._specs: list[ToolSpec] = []

    def initialize(self) -> None:
        """构建工具映射和规格。

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
        """返回 MCP 格式的工具定义。"""
        return _specs_to_mcp_tools(self._specs)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """按名称及给定参数调用工具。"""
        fn = self._tools.get(name)
        if fn is None:
            return f"Unknown tool: {name}"
        try:
            return str(fn(**arguments))
        except Exception as exc:
            logger.error("MCP tool %s failed: %s", name, exc)
            return f"Tool {name} error: {exc}"

    def run_stdio(self) -> None:
        """通过 stdio 传输运行 MCP 服务器。"""
        try:
            from mcp.server import Server
            from mcp.server.stdio import stdio_server
            from mcp.types import TextContent, Tool
        except ImportError:
            logger.error("mcp package not installed; run: pip install mcp")
            return

        server = Server("night-diary")

        @server.list_tools()  # type: ignore[untyped-decorator, no-untyped-call]
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name=spec.name,
                    description=spec.description,
                    inputSchema=spec.parameters,
                )
                for spec in self._specs
            ]

        @server.call_tool()  # type: ignore[untyped-decorator, no-untyped-call]
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            result = self.call_tool(name, arguments)
            return [TextContent(type="text", text=result)]

        import asyncio

        async def _main() -> None:
            async with stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        asyncio.run(_main())

    def run_sse(self, *, port: int = 8080) -> None:
        """通过 SSE 传输运行 MCP 服务器（HTTP）。"""
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

        @server.list_tools()  # type: ignore[untyped-decorator, no-untyped-call]
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

        @server.call_tool()  # type: ignore[untyped-decorator, no-untyped-call]
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
    """MCP 服务器的 CLI 入口点。"""
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

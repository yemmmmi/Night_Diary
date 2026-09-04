"""Unit tests for ToolRegistry: namespacing, merge, call logging, spans."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database import Base
from app.infrastructure.mcp_call_tracer import McpCallTracer, list_calls
from app.services.ai.tool_factory import is_mcp_tool, namespaced_tool_name
from app.services.ai.tool_registry import ToolRegistry
from app.shared.pipeline_trace import PipelineTrace, reset_trace, set_trace


class FakeConn:
    transport = "stdio"

    def __init__(self, alias: str = "fake") -> None:
        self.alias = alias
        self.state = "healthy"
        self.restart_count = 0
        self.last_error = ""
        self.loaded_at = "2026-09-04T00:00:00+00:00"
        self.tool_count = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def connect(self) -> bool:
        return True

    def list_tools(self) -> list[Any]:
        return [
            SimpleNamespace(
                name="echo",
                description="回声",
                inputSchema={"type": "object", "properties": {"text": {"type": "string"}}},
            )
        ]

    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        self.calls.append((name, args))
        return "ok"

    def close(self) -> None:
        pass


class FailingConn(FakeConn):
    def call_tool(self, name: str, args: dict[str, Any]) -> str:
        raise RuntimeError("boom")


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _registry(session_factory, conn: FakeConn | None = None) -> tuple[ToolRegistry, FakeConn]:
    container = MagicMock()
    container._llm_for_tier.return_value = MagicMock()
    container.retriever = MagicMock()
    container.session_factory = session_factory
    settings = SimpleNamespace(mcp_endpoints="", mcp_stdios="")
    reg = ToolRegistry.__new__(ToolRegistry)  # 不启动 McpLoop（连接用 Fake）
    reg._container = container
    reg._settings = settings
    reg._loop = MagicMock()
    reg._connections = {}
    reg._mcp_tools = {}
    reg._tracer = McpCallTracer(session_factory)
    fake = conn or FakeConn()
    reg.register_connection(fake)
    return reg, fake


class TestNamespacing:
    def test_names(self) -> None:
        assert namespaced_tool_name("tavily", "search") == "mcp__tavily__search"
        assert is_mcp_tool("mcp__tavily__search") is True
        assert is_mcp_tool("search_diary") is False


class TestBuildToolMap:
    def test_local_plus_mcp(self, session_factory) -> None:
        reg, _ = _registry(session_factory)
        tools = reg.build_tool_map(user_id="u1")
        assert tools is not None
        assert "search_diary" in tools  # 本地 8 个
        assert "mcp__fake__echo" in tools  # MCP 1 个
        assert len(tools) == 9

    def test_llm_unavailable_returns_none(self, session_factory) -> None:
        reg, _ = _registry(session_factory)
        reg._container._llm_for_tier.return_value = None
        assert reg.build_tool_map(user_id="u1") is None


class TestCallMcp:
    def test_success_logs_row(self, session_factory) -> None:
        reg, fake = _registry(session_factory)
        tools = reg.build_tool_map(user_id="u1")
        result = tools["mcp__fake__echo"](text="hi")
        assert result == "ok"
        assert fake.calls == [("echo", {"text": "hi"})]
        with session_factory() as db:
            items, total = list_calls(db)
        assert total == 1
        assert items[0]["tool_name"] == "mcp__fake__echo"
        assert items[0]["user_id"] == "u1"
        assert items[0]["status"] == "success"

    def test_failure_logs_error_row(self, session_factory) -> None:
        reg, _ = _registry(session_factory, FailingConn())
        tools = reg.build_tool_map(user_id="u1")
        result = tools["mcp__fake__echo"](text="hi")
        assert "error" in result
        with session_factory() as db:
            items, _ = list_calls(db)
        assert items[0]["status"] == "error"
        assert "boom" in (items[0]["error_message"] or "")

    def test_creates_s8_mcp_span(self, session_factory) -> None:
        reg, _ = _registry(session_factory)
        trace = PipelineTrace(scenario="chat", user_id="u1")
        token = set_trace(trace)
        try:
            reg.call_mcp("mcp__fake__echo", {"text": "hi"}, user_id="u1")
        finally:
            reset_trace(token)
        mcp_spans = [s for s in trace.spans if s.stage_name == "S8_mcp"]
        assert len(mcp_spans) == 1
        assert mcp_spans[0].metadata["endpoint_alias"] == "fake"
        assert mcp_spans[0].metadata["transport"] == "stdio"

    def test_log_write_failure_does_not_break_call(self, session_factory) -> None:
        reg, fake = _registry(session_factory)

        class _BrokenFactory:
            def __call__(self):
                raise RuntimeError("db down")

        reg._tracer = McpCallTracer(_BrokenFactory())  # type: ignore[arg-type]
        result = reg.call_mcp("mcp__fake__echo", {"text": "hi"}, user_id="u1")
        assert result == "ok"


class TestStatus:
    def test_status_and_tools_listing(self, session_factory) -> None:
        reg, _ = _registry(session_factory)
        status = reg.status()
        assert status[0]["alias"] == "fake"
        assert status[0]["state"] == "healthy"
        listing = reg.tools_listing()
        assert listing[0]["name"] == "mcp__fake__echo"
        assert listing[0]["source"] == "fake"

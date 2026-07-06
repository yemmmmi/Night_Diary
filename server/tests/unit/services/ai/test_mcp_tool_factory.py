"""Tests for MCP tool integration in tool_factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.ai.tool_factory import build_tool_map_with_mcp


def test_build_tool_map_with_mcp_no_endpoints() -> None:
    """Without MCP endpoints, only built-in tools are returned."""
    db = MagicMock()
    retriever = MagicMock()
    llm = MagicMock()

    tools = build_tool_map_with_mcp(
        db,
        retriever=retriever,
        llm=llm,
        mcp_endpoints=None,
    )

    # Should have all 5 built-in tools
    assert "search_diary" in tools
    assert "get_weather_info" in tools
    assert "get_user_address" in tools
    assert "analyze_sentiment" in tools
    assert "query_entity_graph" in tools
    assert len(tools) == 5


def test_build_tool_map_with_mcp_empty_endpoints() -> None:
    """Empty MCP endpoints list returns only built-in tools."""
    db = MagicMock()
    retriever = MagicMock()
    llm = MagicMock()

    tools = build_tool_map_with_mcp(
        db,
        retriever=retriever,
        llm=llm,
        mcp_endpoints=[],
    )

    assert len(tools) == 5  # Only built-in tools


def test_build_tool_map_with_mcp_empty_string_endpoints() -> None:
    """Empty string endpoints are skipped."""
    db = MagicMock()
    retriever = MagicMock()
    llm = MagicMock()

    tools = build_tool_map_with_mcp(
        db,
        retriever=retriever,
        llm=llm,
        mcp_endpoints=["", "  ", ""],
    )

    assert len(tools) == 5  # Only built-in tools


def test_build_tool_map_with_mcp_load_failure_non_blocking() -> None:
    """MCP loading failure does not block built-in tools."""
    db = MagicMock()
    retriever = MagicMock()
    llm = MagicMock()

    # Mock _load_mcp_tools to return empty (simulating failure)
    with patch("app.services.ai.tool_factory._load_mcp_tools", return_value={}):
        tools = build_tool_map_with_mcp(
            db,
            retriever=retriever,
            llm=llm,
            mcp_endpoints=["http://localhost:9999/sse"],
        )

    # Built-in tools still available
    assert "search_diary" in tools
    assert len(tools) == 5


def test_build_tool_map_with_mcp_merges_external_tools() -> None:
    """External MCP tools are merged into the tool map."""
    db = MagicMock()
    retriever = MagicMock()
    llm = MagicMock()

    # Mock _load_mcp_tools to return an external tool
    external_tool = MagicMock()
    with patch(
        "app.services.ai.tool_factory._load_mcp_tools",
        return_value={"external_search": external_tool},
    ):
        tools = build_tool_map_with_mcp(
            db,
            retriever=retriever,
            llm=llm,
            mcp_endpoints=["http://localhost:8081/sse"],
        )

    # Both built-in and external tools present
    assert "search_diary" in tools
    assert "external_search" in tools
    assert len(tools) == 6  # 5 built-in + 1 external


def test_build_tool_map_with_mcp_multiple_endpoints() -> None:
    """Multiple MCP endpoints are all loaded."""
    db = MagicMock()
    retriever = MagicMock()
    llm = MagicMock()

    tool1 = MagicMock()
    tool2 = MagicMock()

    call_count = [0]

    def mock_load(endpoint: str):
        call_count[0] += 1
        if "8081" in endpoint:
            return {"tool_a": tool1}
        elif "8082" in endpoint:
            return {"tool_b": tool2}
        return {}

    with patch("app.services.ai.tool_factory._load_mcp_tools", side_effect=mock_load):
        tools = build_tool_map_with_mcp(
            db,
            retriever=retriever,
            llm=llm,
            mcp_endpoints=[
                "http://localhost:8081/sse",
                "http://localhost:8082/sse",
            ],
        )

    assert call_count[0] == 2
    assert "tool_a" in tools
    assert "tool_b" in tools
    assert len(tools) == 7  # 5 built-in + 2 external

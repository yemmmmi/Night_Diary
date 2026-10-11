"""Unit tests for tool_factory — verify RetrievalResult attribute access (PR-2)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.rag.types import RetrievalResult
from app.services.ai.tool_factory import (
    TOOLSET_EXTERNAL,
    TOOLSET_MEMORY,
    TOOLSET_PLAN,
    build_tool_specs,
    create_diary_search_tool,
    create_summarize_diaries_tool,
    group_by_toolset,
    toolset_for_tool,
)
from app.services.ai.utils import summarize_diary_results


def test_build_retrieval_tools_accesses_date_and_tags() -> None:
    """search_diary must use hit.date / hit.tags — not hit.metadata (which doesn't exist)."""
    hits = [
        RetrievalResult(
            doc_id="doc-1",
            content="今天很开心",
            diary_id="1",
            score=0.9,
            date="2026-06-27",
            tags="开心,日常",
        ),
    ]
    retriever = MagicMock()
    retriever.retrieve.return_value = hits

    tool = create_diary_search_tool(retriever)
    result = tool(query="开心")

    # Must not raise AttributeError; must contain date and content
    assert "2026-06-27" in result
    assert "今天很开心" in result
    retriever.retrieve.assert_called_once_with("开心", top_k=10)


def test_tool_factory_with_empty_results() -> None:
    """Empty results must not crash — returns '未找到' message."""
    retriever = MagicMock()
    retriever.retrieve.return_value = []

    tool = create_diary_search_tool(retriever)
    result = tool(query="不存在的词")

    assert "未找到" in result


def test_tool_factory_with_multiple_hits() -> None:
    """Multiple hits should all be formatted with their dates."""
    hits = [
        RetrievalResult(
            doc_id="doc-1",
            content="第一篇日记",
            diary_id="1",
            score=0.9,
            date="2026-06-25",
            tags="日常",
        ),
        RetrievalResult(
            doc_id="doc-2",
            content="第二篇日记",
            diary_id="2",
            score=0.8,
            date="2026-06-26",
            tags="工作",
        ),
    ]
    retriever = MagicMock()
    retriever.retrieve.return_value = hits

    tool = create_diary_search_tool(retriever)
    result = tool(query="日记")

    assert "2026-06-25" in result
    assert "2026-06-26" in result
    assert "第一篇日记" in result
    assert "第二篇日记" in result


# ── D2: toolset abstraction ──────────────────────────────────────────────


def test_every_builtin_spec_has_a_known_toolset() -> None:
    known = {TOOLSET_MEMORY, TOOLSET_PLAN, TOOLSET_EXTERNAL}
    for spec in build_tool_specs():
        assert spec.toolset in known, f"{spec.name} has unexpected toolset {spec.toolset}"


def test_toolset_for_local_tools() -> None:
    assert toolset_for_tool("search_diary") == TOOLSET_MEMORY
    assert toolset_for_tool("analyze_sentiment") == TOOLSET_MEMORY
    assert toolset_for_tool("query_entity_graph") == TOOLSET_MEMORY
    assert toolset_for_tool("list_todos") == TOOLSET_PLAN
    assert toolset_for_tool("get_plan_progress") == TOOLSET_PLAN
    assert toolset_for_tool("get_plan_detail") == TOOLSET_PLAN
    assert toolset_for_tool("get_weather_info") == TOOLSET_EXTERNAL
    assert toolset_for_tool("get_user_address") == TOOLSET_EXTERNAL


def test_toolset_for_mcp_tools_groups_by_alias() -> None:
    assert toolset_for_tool("mcp__fetch__get_url") == "mcp:fetch"
    assert toolset_for_tool("mcp__tavily__search") == "mcp:tavily"


def test_group_by_toolset() -> None:
    grouped = group_by_toolset(
        ["search_diary", "list_todos", "mcp__fetch__get_url", "get_weather_info"]
    )
    assert grouped[TOOLSET_MEMORY] == ["search_diary"]
    assert grouped[TOOLSET_PLAN] == ["list_todos"]
    assert grouped[TOOLSET_EXTERNAL] == ["get_weather_info"]
    assert grouped["mcp:fetch"] == ["mcp__fetch__get_url"]


# ── A6: compound retrieval tool ──────────────────────────────────────────


def _hits(*specs: tuple[str, str, str]) -> list[RetrievalResult]:
    return [
        RetrievalResult(
            doc_id=f"doc-{i}",
            content=content,
            diary_id=str(i),
            score=0.9,
            date=date,
            tags=tags,
        )
        for i, (date, tags, content) in enumerate(specs, start=1)
    ]


def test_summarize_tool_aggregates_hits() -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = _hits(
        ("2026-06-25", "工作", "加班到很晚"),
        ("2026-06-26", "工作,疲惫", "又加班了"),
        ("2026-06-27", "休息", "终于休息"),
    )
    tool = create_summarize_diaries_tool(retriever)
    result = tool(query="加班")

    assert "共命中 3 条" in result
    assert "2026-06-25 ~ 2026-06-27" in result
    assert "工作(2)" in result
    retriever.retrieve.assert_called_once_with("加班", top_k=20)


def test_summarize_tool_filters_by_tag() -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = _hits(
        ("2026-06-25", "工作", "加班到很晚"),
        ("2026-06-27", "休息", "终于休息"),
    )
    tool = create_summarize_diaries_tool(retriever)
    result = tool(query="最近", tag="休息")

    assert "共命中 1 条" in result
    assert "终于休息" in result
    assert "加班到很晚" not in result


def test_summarize_tool_caps_items() -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = _hits(
        *[(f"2026-06-{d:02d}", "日常", f"第{d}篇") for d in range(1, 13)]
    )
    tool = create_summarize_diaries_tool(retriever)
    result = tool(query="日记", max_items=3)

    assert "仅展示前 3 条" in result


def test_summarize_tool_degrades_on_error() -> None:
    retriever = MagicMock()
    retriever.retrieve.side_effect = RuntimeError("boom")
    tool = create_summarize_diaries_tool(retriever)
    assert "暂时不可用" in tool(query="x")


def test_summarize_tool_empty_results() -> None:
    retriever = MagicMock()
    retriever.retrieve.return_value = []
    tool = create_summarize_diaries_tool(retriever)
    assert "未找到" in tool(query="x")


def test_summarize_helper_empty() -> None:
    assert summarize_diary_results([]) == "未找到匹配的历史日记。"

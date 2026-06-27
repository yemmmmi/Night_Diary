"""Unit tests for tool_factory — verify RetrievalResult attribute access (PR-2)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.rag.types import RetrievalResult
from app.services.ai.tool_factory import create_diary_search_tool


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

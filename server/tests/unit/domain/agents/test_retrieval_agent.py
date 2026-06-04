"""Unit tests for RetrievalAgent (HybridRetriever + knowledge mocked)."""

from __future__ import annotations

from app.domain.agents.retrieval_agent import RetrievalAgent, lexical_similarity
from app.domain.knowledge.types import KnowledgeHit
from app.domain.rag.types import RetrievalResult
from app.shared.token_utils import estimate_tokens

from .conftest import StubKnowledgeStore


class StubRetriever:
    """HybridRetriever stand-in returning scripted hits per hop."""

    def __init__(self, hops: list[list[RetrievalResult]]) -> None:
        self._hops = hops
        self.queries: list[str] = []

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[RetrievalResult]:
        index = min(len(self.queries), len(self._hops) - 1)
        self.queries.append(query)
        return self._hops[index] if self._hops else []


def _hit(doc_id: str, content: str, *, score: float, date: str = "") -> RetrievalResult:
    return RetrievalResult(
        doc_id=doc_id, content=content, diary_id=doc_id, score=score, date=date
    )


def test_lexical_similarity_bounds() -> None:
    assert lexical_similarity("今天很开心", "今天很开心") == 1.0
    assert lexical_similarity("今天很开心", "") == 0.0
    assert 0.0 <= lexical_similarity("今天去公园散步", "昨天在家睡觉") < 1.0


async def test_high_relevance_stops_after_first_hop(knowledge_store: StubKnowledgeStore) -> None:
    retriever = StubRetriever(
        [[_hit("d1", "相关日记一", score=0.9), _hit("d2", "相关日记二", score=0.85)]]
    )
    agent = RetrievalAgent(retriever, knowledge_store)  # type: ignore[arg-type]
    result = await agent.run({"diary_content": "我想回顾一下最近的状态。"})

    assert len(retriever.queries) == 1
    assert "【相关日记】" in result["retrieval_context"]


async def test_anchor_guard_stops_on_query_drift(knowledge_store: StubKnowledgeStore) -> None:
    # Low-score hits keep relevance under threshold, so the loop would continue;
    # the injected similarity forces an anchor stop after the first hop.
    retriever = StubRetriever(
        [
            [_hit("d1", "弱相关内容", score=0.05)],
            [_hit("d2", "更弱相关内容", score=0.05)],
        ]
    )
    agent = RetrievalAgent(
        retriever,  # type: ignore[arg-type]
        knowledge_store,
        query_similarity=lambda a, b: 0.1,
    )
    await agent.run({"diary_content": "记录一下今天的琐事。"})
    assert len(retriever.queries) == 1


async def test_irrelevant_first_hop_does_not_drift_unbounded(
    knowledge_store: StubKnowledgeStore,
) -> None:
    """First hop returns irrelevant hits; anchor guard caps further hops."""
    retriever = StubRetriever(
        [
            [_hit("d1", "完全无关的体育新闻", score=0.02)],
            [_hit("d2", "另一篇无关内容", score=0.01)],
            [_hit("d3", "第三篇无关内容", score=0.01)],
        ]
    )
    drift_calls: list[tuple[str, str]] = []

    def track_drift(original: str, refined: str) -> float:
        drift_calls.append((original, refined))
        # Refined query diverges heavily from the original diary topic.
        return 0.05

    agent = RetrievalAgent(
        retriever,  # type: ignore[arg-type]
        knowledge_store,
        max_hops=3,
        query_similarity=track_drift,
    )
    await agent.run({"diary_content": "最近工作压力很大，经常失眠。"})

    assert len(retriever.queries) == 1
    assert drift_calls, "anchor similarity should be evaluated before stopping"


async def test_multi_hop_runs_until_max_hops(knowledge_store: StubKnowledgeStore) -> None:
    retriever = StubRetriever(
        [
            [_hit("d1", "片段一", score=0.05)],
            [_hit("d2", "片段二", score=0.05)],
            [_hit("d3", "片段三", score=0.05)],
            [_hit("d4", "片段四", score=0.05)],
        ]
    )
    agent = RetrievalAgent(
        retriever,  # type: ignore[arg-type]
        knowledge_store,
        max_hops=3,
        query_similarity=lambda a, b: 0.9,
    )
    await agent.run({"diary_content": "想看看以前发生过什么类似的事。"})
    assert len(retriever.queries) == 3


async def test_summary_respects_token_budget(knowledge_store: StubKnowledgeStore) -> None:
    long_hits = [_hit(f"d{i}", "很长的日记内容" * 30, score=0.9) for i in range(6)]
    retriever = StubRetriever([long_hits])
    agent = RetrievalAgent(retriever, knowledge_store, max_summary_tokens=300)  # type: ignore[arg-type]
    result = await agent.run({"diary_content": "回顾最近发生的事情。"})
    assert estimate_tokens(result["retrieval_context"]) <= 300


async def test_domain_knowledge_included_in_summary() -> None:
    hits = [
        KnowledgeHit(
            content="规律作息有助于改善睡眠质量。",
            category="sleep_hygiene",
            topic="睡眠",
            source="test",
            distance=0.1,
            doc_id="k1",
        )
    ]
    store = StubKnowledgeStore(hits)
    retriever = StubRetriever([[_hit("d1", "相关日记", score=0.9), _hit("d2", "另一条", score=0.9)]])
    agent = RetrievalAgent(retriever, store)  # type: ignore[arg-type]
    result = await agent.run({"diary_content": "最近总是睡不好。"})
    assert "【领域参考】" in result["retrieval_context"]
    assert "规律作息" in result["retrieval_context"]


async def test_empty_content_returns_empty_context(knowledge_store: StubKnowledgeStore) -> None:
    retriever = StubRetriever([])
    agent = RetrievalAgent(retriever, knowledge_store)  # type: ignore[arg-type]
    result = await agent.run({"diary_content": "   "})
    assert result["retrieval_context"] == ""
    assert retriever.queries == []


async def test_retriever_failure_degrades_gracefully(knowledge_store: StubKnowledgeStore) -> None:
    class BoomRetriever:
        def retrieve(self, query: str, *, top_k: int | None = None) -> list[RetrievalResult]:
            raise RuntimeError("chroma down")

    agent = RetrievalAgent(BoomRetriever(), knowledge_store)  # type: ignore[arg-type]
    result = await agent.run({"diary_content": "回顾最近的状态。"})
    # No exception; empty diary section, summary may still be empty.
    assert "retrieval_context" in result


def test_fallback_returns_empty_context(knowledge_store: StubKnowledgeStore) -> None:
    retriever = StubRetriever([])
    agent = RetrievalAgent(retriever, knowledge_store)  # type: ignore[arg-type]
    assert agent.fallback() == {"retrieval_context": ""}

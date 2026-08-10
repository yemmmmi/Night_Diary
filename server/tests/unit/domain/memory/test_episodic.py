"""Unit tests for EpisodicMemory."""

from __future__ import annotations

import time

from app.domain.memory.episodic import EpisodicMemory
from app.domain.memory.types import EpisodicEntry
from app.infrastructure.memory_repository import SqliteEpisodicMemoryStore


def _entry(
    *,
    importance: float = 0.7,
    timestamp: float | None = None,
    event: str = "测试事件",
    emotion: str = "happy",
) -> EpisodicEntry:
    return EpisodicEntry(
        event_summary=event,
        emotion=emotion,
        reply_insight="建议",
        timestamp=timestamp if timestamp is not None else time.time(),
        diary_ids=["d01"],
        importance=importance,
    )


def test_store_high_importance(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    assert memory.store(_entry(importance=0.8)) is True
    assert memory.size == 1


def test_store_low_importance_skipped(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    assert memory.store(_entry(importance=0.3)) is False
    assert memory.size == 0


def test_store_exact_threshold_skipped(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    assert memory.store(_entry(importance=0.5)) is False


def test_retrieve_returns_top_k(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    now = time.time()
    for index in range(8):
        memory.store(
            _entry(
                importance=0.6 + index * 0.05,
                timestamp=now - index * 3600,
                event=f"事件{index}",
            )
        )

    results = memory.retrieve_relevant(now=now)
    assert len(results) == 5


def test_retrieve_respects_decay(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    now = time.time()
    memory.store(_entry(importance=0.6, timestamp=now, event="新事件"))
    memory.store(
        _entry(
            importance=0.7,
            timestamp=now - 30 * 24 * 3600,
            event="旧事件",
        )
    )

    results = memory.retrieve_relevant(now=now)
    assert results[0].event_summary == "新事件"


def test_persistence_survives_restart(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    entry = _entry(importance=0.8, event="失眠")
    memory.store(entry)

    reloaded = EpisodicMemory(store=episodic_store, user_id="u1")
    reloaded.load()
    hits = reloaded.retrieve_relevant(top_k=1)
    assert len(hits) == 1
    assert hits[0].event_summary == "失眠"


def test_decay_purges_entries_below_threshold(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1")
    now = time.time()
    fourteen_days = 14 * 24 * 3600
    memory.store(_entry(importance=0.8, timestamp=now - fourteen_days, event="过期事件"))
    assert memory.size == 1  # stored before purge

    # evict_lowest() triggers purge_stale(); 14-day decay drops score below 0.5.
    memory.evict_lowest(now=now)
    assert memory.size == 0


def test_evict_when_over_limit(episodic_store: SqliteEpisodicMemoryStore) -> None:
    memory = EpisodicMemory(store=episodic_store, user_id="u1", persist=False)
    now = time.time()
    for index in range(102):
        memory.store(
            _entry(
                importance=0.51 + index * 0.001,
                timestamp=now + index,
                event=f"事件{index}",
            )
        )

    assert memory.size == 100


def test_multiturn_insomnia_context_retained(episodic_store: SqliteEpisodicMemoryStore) -> None:
    """Simulate Day1 insomnia -> Day2 exercise -> Day3 recall."""
    memory = EpisodicMemory(store=episodic_store, user_id="default")
    day1 = time.mktime(time.strptime("2026-06-01", "%Y-%m-%d"))
    day2 = time.mktime(time.strptime("2026-06-02", "%Y-%m-%d"))
    day3 = time.mktime(time.strptime("2026-06-03", "%Y-%m-%d"))

    memory.store(
        _entry(
            importance=0.85,
            timestamp=day1,
            event="失眠",
            emotion="焦虑",
        )
    )
    memory.store(
        _entry(
            importance=0.75,
            timestamp=day2,
            event="晨跑",
            emotion="振奋",
        )
    )

    hits = memory.retrieve_relevant(query="睡眠", now=day3, top_k=2)
    assert any(hit.event_summary == "失眠" for hit in hits)


def test_query_relevance_ranks_related_entry_higher(
    episodic_store: SqliteEpisodicMemoryStore,
) -> None:
    """A query-relevant entry should outrank a higher-importance but irrelevant entry."""
    memory = EpisodicMemory(store=episodic_store, user_id="default")
    now = time.time()

    # "加班" has higher importance but zero character overlap with "失眠"
    memory.store(_entry(importance=0.7, timestamp=now, event="加班", emotion="疲惫"))
    # "失眠" has lower importance but shares "眠" with the query "睡眠"
    memory.store(_entry(importance=0.6, timestamp=now, event="失眠", emotion="焦虑"))

    hits = memory.retrieve_relevant(query="睡眠", now=now, top_k=2)
    assert hits[0].event_summary == "失眠"


def test_empty_query_keeps_importance_order(episodic_store: SqliteEpisodicMemoryStore) -> None:
    """Without a query, pure importance * decay ranking is preserved."""
    memory = EpisodicMemory(store=episodic_store, user_id="default")
    now = time.time()

    memory.store(_entry(importance=0.6, timestamp=now, event="失眠"))
    memory.store(_entry(importance=0.9, timestamp=now, event="加班"))

    hits = memory.retrieve_relevant(query="", now=now, top_k=2)
    assert hits[0].event_summary == "加班"


# ── V3 P4 Task 10: two-stage retrieval (importance×decay → vector → reranker) ──


def test_retrieve_relevant_uses_embedder_when_provided() -> None:
    """有 embedder 时应走向量检索(非 char_jaccard)。"""
    from app.shared.embed_utils import StubEmbedder

    memory = EpisodicMemory(
        store=None,
        user_id="test",
        embedder=StubEmbedder(),
    )
    memory._entries.clear()
    # 存几条 entry
    for summary, importance in [("失眠", 0.9), ("吃饭", 0.6), ("加班", 0.7)]:
        memory._entries.append(
            EpisodicEntry(
                event_summary=summary,
                emotion="neutral",
                timestamp=time.time(),
                importance=importance,
            )
        )

    # 用 StubEmbedder 检索(确定性 hash)
    results = memory.retrieve_relevant("失眠", top_k=2)
    assert len(results) <= 2
    # 应该有结果
    assert len(results) >= 1


def test_retrieve_relevant_degrades_to_jaccard_without_embedder() -> None:
    """无 embedder 时应降级 char_jaccard。"""
    memory = EpisodicMemory(store=None, user_id="test", embedder=None)
    memory._entries.clear()
    memory._entries.append(
        EpisodicEntry(
            event_summary="失眠",
            emotion="焦虑",
            timestamp=time.time(),
            importance=0.9,
        )
    )

    # char_jaccard("失眠", "失眠") = 1.0,应命中
    results = memory.retrieve_relevant("失眠", top_k=1)
    assert len(results) == 1
    assert results[0].event_summary == "失眠"


def test_get_or_compute_embedding_lazy_and_caches() -> None:
    """_get_or_compute_embedding 应懒计算并缓存到 entry.embedding。"""
    from app.shared.embed_utils import StubEmbedder

    memory = EpisodicMemory(
        store=None,
        user_id="test",
        embedder=StubEmbedder(),
    )
    entry = EpisodicEntry(
        event_summary="测试",
        emotion="n",
        timestamp=time.time(),
        importance=0.6,
    )
    assert entry.embedding is None  # 初始无

    vec = memory._get_or_compute_embedding(entry)
    assert vec is not None
    assert len(vec) > 0
    assert entry.embedding is not None  # 已缓存
    assert entry.embedding == vec

    # 第二次调用应直接用缓存(不重算)
    vec2 = memory._get_or_compute_embedding(entry)
    assert vec2 == vec


def test_store_precomputes_embedding_when_embedder_available() -> None:
    """store 时如果有 embedder 应预计算 embedding。"""
    from app.shared.embed_utils import StubEmbedder

    memory = EpisodicMemory(
        store=None,
        user_id="test",
        embedder=StubEmbedder(),
    )
    entry = EpisodicEntry(
        event_summary="新条目",
        emotion="n",
        timestamp=time.time(),
        importance=0.7,
    )
    memory.store(entry)
    assert entry.embedding is not None  # store 时预计算
    assert len(entry.embedding) > 0


def test_retrieve_relevant_respects_top_k() -> None:
    """retrieve_relevant 应返回不超过 top_k 条。"""
    from app.shared.embed_utils import StubEmbedder

    memory = EpisodicMemory(
        store=None,
        user_id="test",
        embedder=StubEmbedder(),
    )
    memory._entries.clear()
    for i in range(5):
        memory._entries.append(
            EpisodicEntry(
                event_summary=f"条目{i}",
                emotion="n",
                timestamp=time.time(),
                importance=0.6,
            )
        )

    results = memory.retrieve_relevant("查询", top_k=3)
    assert len(results) <= 3

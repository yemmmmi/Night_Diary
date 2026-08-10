"""情景记忆 —— 进程内 deque，可选 SQLite 持久化。

Example::

    from app.infrastructure.database import create_db_engine, create_session_factory, init_db
    from app.infrastructure.memory_repository import SqliteEpisodicMemoryStore
    from app.domain.memory.episodic import EpisodicMemory
    from app.domain.memory.types import EpisodicEntry

    engine = create_db_engine("sqlite:////tmp/night-diary-test/episodic.db")
    init_db(engine)
    store = SqliteEpisodicMemoryStore(create_session_factory(engine))
    memory = EpisodicMemory(store=store, user_id="default")
    memory.load()

    entry = EpisodicEntry(
        event_summary="失眠",
        emotion="焦虑",
        reply_insight="尝试放松呼吸",
        timestamp=time.time(),
        importance=0.8,
        diary_ids=["d01"],
    )
    memory.store(entry)
    hits = memory.retrieve_relevant(query="睡眠", top_k=3)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.domain.memory.types import EpisodicEntry, EpisodicMemoryStore

if TYPE_CHECKING:
    from app.shared.embed_utils import Embedder

logger = logging.getLogger(__name__)

SimilarityFn = Callable[[str, str], float]

#: 查询相关性与 importance * decay 混合时的权重。
#: final_score = time_score * (1.0 + relevance * RELEVANCE_WEIGHT)
#: 取 1.0 时，一个完全相关的条目会使其基础分翻倍 —— 足以
#: 克服中等程度的 importance 差距（例如 0.6 相关 > 0.7 不相关），
#: 同时在相关性为 0 时仍保留 importance-decay 的排序。
RELEVANCE_WEIGHT = 1.0


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity for normalized vectors (= dot product).

    Vectors from :class:`BgeEmbedder` are L2-normalized, so cosine sim reduces
    to a plain dot product downstream. This helper falls back to the full
    cosine formula when vectors aren't normalized, and returns ``0.0`` for
    mismatched lengths or zero-norm vectors so callers never see a ``NaN``.
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    # 显式 start=0.0 让 sum() 的返回类型解析为 float(否则 mypy 推断为 Any)。
    dot = sum((a * b for a, b in zip(vec_a, vec_b, strict=False)), 0.0)
    norm_a = sum((a * a for a in vec_a), 0.0) ** 0.5
    norm_b = sum((b * b for b in vec_b), 0.0) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def char_jaccard(left: str, right: str) -> float:
    """针对短中文文本的字符级 Jaccard 重叠度。

    情景记忆的 ``event_summary`` 标签通常为 2-4 个字符（"失眠"、"加班"）。
    词级 jieba 分词会把它们当作单个 token，导致在语义相关的标签（如"失眠"和"睡眠"）
    之间得到零重叠。字符级匹配可以捕获共享的"眠"字符。
    """
    left_chars = {c for c in left if c.strip()}
    right_chars = {c for c in right if c.strip()}
    if not left_chars or not right_chars:
        return 0.0
    intersection = left_chars & right_chars
    union = left_chars | right_chars
    return len(intersection) / len(union)


class EpisodicMemory:
    """进程本地的情景记忆，由 ``deque`` 支撑并具备 SQLite 持久化。"""

    MAX_ENTRIES = 100
    IMPORTANCE_THRESHOLD = 0.5
    DECAY_HALF_LIFE = 7 * 24 * 3600

    def __init__(
        self,
        *,
        store: EpisodicMemoryStore | None = None,
        user_id: str = "default",
        persist: bool = True,
        similarity: SimilarityFn | None = None,
        embedder: Embedder | None = None,
        reranker: Any | None = None,
    ) -> None:
        self._store = store
        self._user_id = user_id
        self._persist = persist and store is not None
        self._entries: deque[EpisodicEntry] = deque()
        # 延迟导入，以避免在从未传入查询时承担 jieba 的加载成本。
        self._similarity = similarity
        # ── V3 P4: 向量化两阶段检索 ──
        # embedder 用于 Stage 2 向量精排;为 None 时降级 char_jaccard。
        self._embedder = embedder
        # reranker 用于 Stage 3 cross-encoder 精排;为 None 时跳过。
        # 类型为 Reranker,但此处用 Any 以避免与 app.domain.rag.reranker 循环 import。
        self._reranker = reranker

    def load(self) -> None:
        """将持久化的条目加载到进程内 deque 中。"""
        if self._store is None:
            return

        loaded = self._store.load_entries(self._user_id)
        self._entries.clear()
        for entry in loaded:
            if self._effective_score(entry, time.time()) >= self.IMPORTANCE_THRESHOLD:
                self._entries.append(entry)
        self._enforce_capacity()

    def store(self, entry: EpisodicEntry) -> bool:
        """当 importance 超过阈值时，存储一条情景记忆条目。"""
        if entry.importance <= self.IMPORTANCE_THRESHOLD:
            logger.debug(
                "Skip episodic store: importance=%.2f <= %.2f",
                entry.importance,
                self.IMPORTANCE_THRESHOLD,
            )
            return False

        # V3 P4: store 时预计算 embedding(在 model_copy 之前,保证调用方也能看到缓存)。
        # 仅在 importance 通过阈值后才计算,避免对被跳过的条目浪费算力。
        if entry.embedding is None and self._embedder is not None:
            try:
                text = entry.event_summary
                if entry.tags:
                    text += " " + " ".join(entry.tags)
                entry.embedding = self._embedder.embed(text)
            except Exception as exc:  # embed 失败不应阻断存储
                logger.warning("Store-time embedding precompute failed: %s", exc)

        if not entry.entry_id:
            entry = entry.model_copy(update={"entry_id": uuid.uuid4().hex})

        self._entries.append(entry)
        self.upsert(entry)
        self._enforce_capacity()
        return True

    def upsert(self, entry: EpisodicEntry) -> None:
        """将单条条目持久化到 SQLite。"""
        if not self._persist or self._store is None:
            return
        self._store.upsert_entry(self._user_id, entry)

    def retrieve_relevant(
        self,
        query: str = "",
        top_k: int = 5,
        now: float | None = None,
    ) -> list[EpisodicEntry]:
        """两阶段检索:importance×decay 粗排 → 向量精排 → 可选 reranker。

        Stage 1: 按 importance 阈值过滤 + 按 importance×decay 排序,取 top_k×5
        Stage 2: 若有 embedder,用向量余弦相似度重排;否则降级 char_jaccard
        Stage 3: 若注入了 reranker(且有 ``rerank_episodic`` 方法),做最终 cross-encoder 精排

        无 embedder 或空查询时降级 jaccard,行为等价于 V1 的单阶段检索,
        因此旧的 char_jaccard 测试全部保持通过。
        """
        if now is None:
            now = time.time()

        self.purge_stale(now=now)

        query_trimmed = query.strip()
        use_relevance = bool(query_trimmed)

        # Stage 1: importance × decay 粗排
        candidates = [
            entry
            for entry in self._entries
            if self._effective_score(entry, now) >= self.IMPORTANCE_THRESHOLD
        ]
        candidates.sort(
            key=lambda entry: self._effective_score(entry, now),
            reverse=True,
        )
        # 取 top_k × 5 作为粗排候选(不足时取全部)
        candidates = candidates[: max(top_k * 5, top_k)]

        if not candidates:
            return []

        # Stage 2: 向量精排 或 降级 jaccard
        if use_relevance and self._embedder is not None:
            try:
                query_vec = self._embedder.embed(query_trimmed)
                scored: list[tuple[float, EpisodicEntry]] = []
                for entry in candidates:
                    entry_vec = self._get_or_compute_embedding(entry)
                    sim = (
                        _cosine_similarity(query_vec, entry_vec)
                        if entry_vec
                        else 0.0
                    )
                    base = self._effective_score(entry, now)
                    final = base * (1.0 + sim * RELEVANCE_WEIGHT)
                    scored.append((final, entry))
                scored.sort(key=lambda item: item[0], reverse=True)
                top_entries = [entry for _, entry in scored[: top_k * 2]]
            except Exception as exc:  # 向量失败时降级到 jaccard
                logger.warning(
                    "Vector retrieval failed, degrading to jaccard: %s", exc
                )
                top_entries = self._jaccard_fallback(
                    query_trimmed, candidates, top_k, now
                )
        else:
            # 无 embedder 或空查询:降级 char_jaccard(空查询时 relevance 恒为 0,
            # 退化为纯 importance×decay 排序)。
            top_entries = self._jaccard_fallback(
                query_trimmed, candidates, top_k, now
            )

        # Stage 3: 可选 reranker 精排(Task 11 将为 Reranker 增加 rerank_episodic)
        if (
            self._reranker is not None
            and use_relevance
            and len(top_entries) > 1
            and hasattr(self._reranker, "rerank_episodic")
        ):
            try:
                top_entries = self._reranker.rerank_episodic(
                    query_trimmed, top_entries
                )
            except Exception as exc:  # reranker 失败不阻断检索
                logger.warning("Reranker failed (non-fatal): %s", exc)

        return top_entries[:top_k]

    def _jaccard_fallback(
        self,
        query: str,
        candidates: list[EpisodicEntry],
        top_k: int,
        now: float,
    ) -> list[EpisodicEntry]:
        """向量检索不可用时降级为 char_jaccard。

        与 V1 行为等价:final = importance×decay × (1 + relevance × RELEVANCE_WEIGHT)。
        空查询时 relevance 恒为 0,退化为纯 importance×decay 排序。
        """
        similarity = self._resolve_similarity()
        scored: list[tuple[float, EpisodicEntry]] = []
        for entry in candidates:
            relevance = similarity(query, entry.event_summary) if query else 0.0
            base = self._effective_score(entry, now)
            final = base * (1.0 + relevance * RELEVANCE_WEIGHT)
            scored.append((final, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[: top_k * 2]]

    def _get_or_compute_embedding(self, entry: EpisodicEntry) -> list[float]:
        """懒计算并把 embedding 缓存到 entry 上。

        拼接 ``event_summary`` + ``tags``(tags 帮助区分简短的 summary)。
        embedder 不可用或计算失败时返回空列表(调用方按 0 相似度处理)。
        """
        if entry.embedding is not None:
            return entry.embedding
        if self._embedder is None:
            return []
        try:
            text = entry.event_summary
            if entry.tags:
                text += " " + " ".join(entry.tags)
            vec = self._embedder.embed(text)
            entry.embedding = vec  # cache on entry
            return vec
        except Exception as exc:  # embedding 失败不阻断检索
            logger.warning("Embedding computation failed (non-fatal): %s", exc)
            return []

    def _resolve_similarity(self) -> SimilarityFn:
        """返回已配置的相似度函数，默认为 char Jaccard。"""
        if self._similarity is not None:
            return self._similarity
        return char_jaccard

    def evict_lowest(self, now: float | None = None) -> int:
        """清除过期条目并强制执行 LRU 容量上限。"""
        if now is None:
            now = time.time()

        removed = self.purge_stale(now=now)
        removed += self._enforce_capacity()
        return removed

    def purge_stale(self, now: float | None = None) -> int:
        """移除有效分已降至阈值以下的条目。"""
        if now is None:
            now = time.time()

        stale_ids: list[str] = []
        kept: deque[EpisodicEntry] = deque()
        for entry in self._entries:
            if self._effective_score(entry, now) >= self.IMPORTANCE_THRESHOLD:
                kept.append(entry)
            elif entry.entry_id:
                stale_ids.append(entry.entry_id)

        removed = len(self._entries) - len(kept)
        self._entries = kept

        if stale_ids and self._persist and self._store is not None:
            self._store.delete_entries(self._user_id, stale_ids)

        return removed

    def _compute_decay(self, timestamp: float, now: float) -> float:
        elapsed = max(0.0, now - timestamp)
        return float(0.5 ** (elapsed / self.DECAY_HALF_LIFE))

    def _effective_score(self, entry: EpisodicEntry, now: float) -> float:
        return entry.importance * self._compute_decay(entry.timestamp, now)

    def _enforce_capacity(self) -> int:
        removed = 0
        while len(self._entries) > self.MAX_ENTRIES:
            oldest = min(
                self._entries,
                key=lambda entry: (entry.timestamp, entry.entry_id),
            )
            self._entries.remove(oldest)
            removed += 1
            if oldest.entry_id and self._persist and self._store is not None:
                self._store.delete_entries(self._user_id, [oldest.entry_id])

        if removed:
            logger.info(
                "Episodic LRU eviction: removed=%d remaining=%d user_id=%s",
                removed,
                len(self._entries),
                self._user_id,
            )
        return removed

    @property
    def size(self) -> int:
        return len(self._entries)

    def get_entries(self) -> list[EpisodicEntry]:
        """返回所有情景记忆条目的快照（公开 API）。"""
        return list(self._entries)

    def get_all_entries_for_user(self, user_id: str) -> list[EpisodicEntry]:
        """从存储中加载某用户的全部条目。

        与 ``get_entries``（返回经 decay 过滤、并被 ``MAX_ENTRIES`` 封顶的内存 deque）不同，
        本方法会从存储中加载每一条已持久化的条目，且不做 decay 过滤。
        供长期记忆提升器用于在完整历史中检测重复模式，而非仅限于最近活跃的窗口。
        """
        if self._store is None:
            return list(self._entries)
        return self._store.load_entries(user_id)

    @property
    def user_id(self) -> str:
        """返回该记忆存储所绑定的 user_id。"""
        return self._user_id

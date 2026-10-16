# 已退役记忆的追溯意图门控召回 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 让已被软覆盖（`superseded_by`）的情景记忆在用户明确追溯历史时可以被召回，并强制带时效标注；其余语境与危机语境行为逐字节不变。

**Architecture:** 门控是纯函数（`app/domain/memory/recall_policy.py`），检索侧新增一个与 `retrieve_relevant` 正交的入口 `retrieve_superseded`——它读取存储时不带 decay 阈值（足够旧的历史正是追溯问题要问的），排序复用抽出的单一 `_rank`，且**永不触碰进程内 deque**（否则退役条目会占 `MAX_ENTRIES` 容量并抢占主槽位）。注入侧在 `_format_episodic_memories` 增加一个默认 `False` 的 `allow_superseded` 参数，只有追溯意图的调用点显式传 `True`。

**Tech Stack:** Python 3.11 · pydantic v2 · SQLAlchemy（SQLite store）· pytest · ruff / mypy

**Spec:** `docs/superpowers/specs/2026-10-16-memory-supersede-intent-gated-recall-design.md`

---

## 关键既成事实（实施前必读）

1. **过滤发生在装载期**：`EpisodicMemory.load()` 调 `self._store.load_entries(self._user_id)` 使用默认参数，进程内 deque **从无**已退役条目。所以"查询时按意图放行"必须显式从存储读取，而不是给 deque 加过滤参数。
2. **危机在到达检索点之前已早退**：两条管线的 `S2_crisis` 分支（`if is_crisis: return ChatReplyResult(..., is_crisis=True)`）在 `_format_episodic_memories` 调用点之前返回。因此调用点处 `crisis_detected` 恒为 `False`——但 gate 函数仍**要求显式传参**，避免将来调用方默认放行。
3. **意图以字符串比较**：代码中已有 `intent_result.intent_category == "crisis_signal"` 的先例，故门控直接用字符串字面量。
4. **`EpisodicEntry` 必填字段**：`event_summary` / `emotion` / `reply_insight` / `timestamp`；`importance` 默认 0.5，`entry_id` 默认 `""`，`superseded_by` 默认 `None`。注意 `retrieve_relevant` 过滤条件是 `_effective_score >= IMPORTANCE_THRESHOLD(0.5)`，所以测试条目 `importance` 要取 `0.8` 才进得去；`store()` 是 `<=` 阈值跳过，二者对 `0.5` 的边界不对称。

## 与 spec 的两处收窄（已确认，实施时同步 spec）

| spec 原文 | 计划实现 | 原因 |
|---|---|---|
| 方法名 `retrieve_including_superseded` | `retrieve_superseded` | "including" 听起来是"当前态+历史混合池"；混合池会让历史条目在排序中挤掉当下事实，违反 spec §3.3「当前态在前、历史 ≤2 席」。拆成两个正交入口后，当前态调用点结果**结构性地**不可能被历史影响 |
| 逐行标注含 `最新倾向：偏负面` | `（该感受此后已被修正，非当前状态）` | 数值化"最新倾向"需要把 profile 的 `important_people` 注入到一个纯格式化函数里（person→sentiment 映射），把领域耦合塞进格式化层。标注只需让模型知道"这不是当前状态"即达成 §3.3 的安全目标 |

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `server/app/domain/memory/recall_policy.py` | 门控策略：追溯意图白名单 + 历史配额 + 危机红线 | 新建 |
| `server/app/domain/memory/episodic.py` | 抽出单一排序实现 `_rank` / `_top_candidates`；新增 `retrieve_superseded` | 修改 |
| `server/app/services/conversation_ai_service.py` | formatter 增加历史节渲染；两处调用点传参 | 修改 |
| `server/tests/unit/domain/memory/test_recall_policy.py` | 门控表 + 危机红线 | 新建 |
| `server/tests/unit/domain/memory/test_episodic.py` | 排序单源断言 + 历史召回行为 | 修改 |
| `server/tests/unit/services/test_conversation_ai_service.py` | 历史节渲染 / 配额 / 降级 / 回归 | 修改 |

**不在范围**：场景一（日记分析）任何调用点；退役粒度（整条 entry vs 人-记忆级，轴 B）；`conflict.py` 退役语义。

---

### Task 1: 门控策略纯函数

**Files:**
- Create: `server/app/domain/memory/recall_policy.py`
- Test: `server/tests/unit/domain/memory/test_recall_policy.py`

- [x] **Step 1: 写失败测试**

```python
"""已退役记忆召回门控的策略表测试。"""

from __future__ import annotations

import pytest

from app.domain.memory.recall_policy import (
    HISTORY_SECTION_MAX,
    RETROSPECTIVE_INTENTS,
    allow_superseded_recall,
)


@pytest.mark.parametrize("intent", sorted(RETROSPECTIVE_INTENTS))
def test_retrospective_intents_allow_recall(intent: str) -> None:
    assert allow_superseded_recall(intent, crisis_detected=False) is True


@pytest.mark.parametrize(
    "intent",
    [
        "emotional_support",
        "advice_seeking",
        "casual_chat",
        "pure_record",
        "habit_tracking",
        "crisis_signal",
        "",
        None,
    ],
)
def test_non_retrospective_intents_deny_recall(intent: str | None) -> None:
    assert allow_superseded_recall(intent, crisis_detected=False) is False


def test_crisis_red_line_overrides_every_intent() -> None:
    """危机是硬红线：任何意图都不能放行（spec §3.1）。"""
    for intent in sorted(RETROSPECTIVE_INTENTS):
        assert allow_superseded_recall(intent, crisis_detected=True) is False


def test_history_section_is_capped_at_two() -> None:
    assert HISTORY_SECTION_MAX == 2
```

- [x] **Step 2: 运行测试确认失败**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit/domain/memory/test_recall_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.memory.recall_policy'`

- [x] **Step 3: 写最小实现**

```python
"""软覆盖（P2-B）条目的召回策略。

已退役条目在装载期就被过滤掉了：``EpisodicMemory.load()`` 用默认参数读
存储，进程内 deque 从来不含它们。因此历史召回必须由调用点显式开启，
而不是给 deque 加一个查询期开关。

召回旧观点只在"用户明确回看自己的过去"时才是证据而非噪声；其余语境
（尤其危机）必须让旧观点留在场外——那正是软覆盖机制本身要防的事故。
"""

from __future__ import annotations

#: 会正当地询问用户自身历史的意图——此时被修正前的旧观点是证据。
RETROSPECTIVE_INTENTS: frozenset[str] = frozenset(
    {"retrospective_query", "retrospective_review"}
)

#: 历史节每轮最多占用的条目数。防止历史挤掉当下事实占用的主检索槽位。
HISTORY_SECTION_MAX = 2


def allow_superseded_recall(
    intent_category: str | None,
    *,
    crisis_detected: bool,
) -> bool:
    """本轮是否可召回已被软覆盖的条目。

    ``crisis_detected`` 是硬红线而非同级信号：任何意图都不能覆盖它，因为在
    危机语境使用过期观点，恰恰是软覆盖机制要防的伤害。该参数被设计为必填
    （而不是默认 False），这样每个调用点都必须显式声明危机状态。
    """
    if crisis_detected:
        return False
    return intent_category in RETROSPECTIVE_INTENTS
```

- [x] **Step 4: 运行测试确认通过**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit/domain/memory/test_recall_policy.py -v`
Expected: PASS（14 passed）

- [x] **Step 5: 提交**

```bash
git add server/app/domain/memory/recall_policy.py server/tests/unit/domain/memory/test_recall_policy.py
git commit -m "feat(memory): gate superseded recall on retrospective intent (policy)"
```

---

### Task 2: 抽出单一排序实现 `_rank`（行为保持型重构）

**Files:**
- Modify: `server/app/domain/memory/episodic.py`（`retrieve_relevant` 现位于 166-250 行）
- Test: `server/tests/unit/domain/memory/test_episodic.py`

- [x] **Step 1: 写失败测试（断言排序只有一个实现）**

追加到 `server/tests/unit/domain/memory/test_episodic.py`：

```python
def test_retrieve_relevant_delegates_to_shared_rank(monkeypatch, tmp_path):
    """排序必须是单一实现：改一处不能让两个入口行为漂移。"""
    memory = _memory_with_store(tmp_path)
    memory.store(
        EpisodicEntry(
            event_summary="失眠",
            emotion="焦虑",
            reply_insight="",
            timestamp=time.time(),
            importance=0.8,
        )
    )

    calls: list[tuple[str, int]] = []
    original = EpisodicMemory._rank

    def spy(self, candidates, query, top_k, now):
        calls.append((query, top_k))
        return original(self, candidates, query, top_k, now)

    monkeypatch.setattr(EpisodicMemory, "_rank", spy)
    memory.retrieve_relevant("睡眠", top_k=3)
    assert calls == [("睡眠", 3)]
```

同时在文件顶部补一个构造辅助（若同名辅助已存在则复用，别重复定义）：

```python
def _memory_with_store(tmp_path) -> EpisodicMemory:
    """按 episodic 模块 docstring 的方式建一个临时 SQLite 支撑的实例。"""
    engine = create_db_engine(f"sqlite:///{tmp_path / 'episodic.db'}")
    init_db(engine)
    store = SqliteEpisodicMemoryStore(create_session_factory(engine))
    memory = EpisodicMemory(store=store, user_id="u1")
    memory.load()
    return memory
```

需要的 import（按需补到文件顶部）：

```python
import time

from app.domain.memory.episodic import EpisodicMemory
from app.domain.memory.types import EpisodicEntry
from app.infrastructure.database import (
    create_db_engine,
    create_session_factory,
    init_db,
)
from app.infrastructure.memory_repository import SqliteEpisodicMemoryStore
```

- [x] **Step 2: 运行测试确认失败**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit/domain/memory/test_episodic.py -v -k shared_rank`
Expected: FAIL — `AttributeError: type object 'EpisodicMemory' has no attribute '_rank'`

- [x] **Step 3: 重构实现（机械等价，不改任何排序语义）**

在 `episodic.py` 顶部把 `Iterable` 加进 `collections.abc` 的 import：

```python
from collections.abc import Callable, Iterable
```

把 `retrieve_relevant`（166-250 行整块）替换为下列四个方法：

```python
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

        # Stage 1: importance × decay 粗排
        candidates = self._top_candidates(self._entries, top_k, now)
        if not candidates:
            return []

        return self._rank(candidates, query.strip(), top_k, now)

    def _top_candidates(
        self,
        entries: Iterable[EpisodicEntry],
        top_k: int,
        now: float,
    ) -> list[EpisodicEntry]:
        """Stage 1:decay 阈值过滤 + importance×decay 排序 + top_k×5 截断。

        注意这里带 ``IMPORTANCE_THRESHOLD`` 阈值——这是"当下状态"检索的前提，
        与被软覆盖的历史召回（``retrieve_superseded``）刻意不同。
        """
        candidates = [
            entry
            for entry in entries
            if self._effective_score(entry, now) >= self.IMPORTANCE_THRESHOLD
        ]
        candidates.sort(
            key=lambda entry: self._effective_score(entry, now),
            reverse=True,
        )
        return candidates[: max(top_k * 5, top_k)]

    def _rank(
        self,
        candidates: list[EpisodicEntry],
        query: str,
        top_k: int,
        now: float,
    ) -> list[EpisodicEntry]:
        """Stage 2+3:向量/jaccard 相关性精排 + 可选 reranker。

        单一实现——``retrieve_relevant`` 与 ``retrieve_superseded`` 共用，
        避免两份排序逻辑各自漂移。``query`` 假定已 strip。
        """
        use_relevance = bool(query)

        # Stage 2: 向量精排 或 降级 jaccard
        if use_relevance and self._embedder is not None:
            try:
                query_vec = self._embedder.embed(query)
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
                    query, candidates, top_k, now
                )
        else:
            # 无 embedder 或空查询:降级 char_jaccard(空查询时 relevance 恒为 0,
            # 退化为纯 importance×decay 排序)。
            top_entries = self._jaccard_fallback(query, candidates, top_k, now)

        # Stage 3: 可选 reranker 精排
        if (
            self._reranker is not None
            and use_relevance
            and len(top_entries) > 1
            and hasattr(self._reranker, "rerank_episodic")
        ):
            try:
                top_entries = self._reranker.rerank_episodic(query, top_entries)
            except Exception as exc:  # reranker 失败不阻断检索
                logger.warning("Reranker failed (non-fatal): %s", exc)

        return top_entries[:top_k]
```

- [x] **Step 4: 确认全部既有检索测试仍然通过（这是重构的验收条件）**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit/domain/memory/test_episodic.py -v`
Expected: PASS（既有全部用例 + 新增 `shared_rank` 用例）

- [x] **Step 5: 提交**

```bash
git add server/app/domain/memory/episodic.py server/tests/unit/domain/memory/test_episodic.py
git commit -m "refactor(memory): extract single _rank shared by episodic retrieval paths"
```

---

### Task 3: 新增 `retrieve_superseded`（历史召回，无 decay 阈值）

**Files:**
- Modify: `server/app/domain/memory/episodic.py`
- Modify: `docs/superpowers/specs/2026-10-16-memory-supersede-intent-gated-recall-design.md`（§3.2 方法名与 §3.3 标注文案对齐实现）
- Test: `server/tests/unit/domain/memory/test_episodic.py`

- [x] **Step 1: 写失败测试**

追加到 `server/tests/unit/domain/memory/test_episodic.py`：

```python
def test_retrieve_superseded_returns_stale_history_without_decay_threshold(tmp_path):
    """90 天前的旧条目 decay 已近 0——它正是追溯问题要问的东西。"""
    memory = _memory_with_store(tmp_path)
    ninety_days = 90 * 24 * 3600
    current = EpisodicEntry(
        event_summary="和小雨吵架了",
        emotion="难过",
        reply_insight="",
        timestamp=time.time(),
        importance=0.8,
        entry_id="e_current",
    )
    old = EpisodicEntry(
        event_summary="和小雨一起吃火锅",
        emotion="开心",
        reply_insight="",
        timestamp=time.time() - ninety_days,
        importance=0.9,
        entry_id="e_old",
        superseded_by="e_current",
    )
    memory.upsert(current)
    memory.upsert(old)
    memory.load()

    # 已退役条目不在 deque，也不在当下状态检索里
    assert "e_old" not in [e.entry_id for e in memory.get_entries()]
    assert "e_old" not in [
        e.entry_id for e in memory.retrieve_relevant("小雨", top_k=5)
    ]

    hits = memory.retrieve_superseded("小雨", top_k=2)
    assert [e.entry_id for e in hits] == ["e_old"]


def test_retrieve_superseded_excludes_current_entries(tmp_path):
    """两个入口正交：历史入口不返回当前态条目，当前态入口不返回历史。"""
    memory = _memory_with_store(tmp_path)
    current = EpisodicEntry(
        event_summary="加班到十点",
        emotion="疲惫",
        reply_insight="",
        timestamp=time.time(),
        importance=0.8,
        entry_id="e_current",
    )
    memory.upsert(current)
    memory.load()

    assert memory.retrieve_superseded("加班", top_k=2) == []
    assert memory.retrieve_relevant("加班", top_k=5) != []


def test_retrieve_superseded_does_not_touch_the_deque(tmp_path):
    """把退役条目读进 deque 会占用 MAX_ENTRIES 并抢占主槽位。"""
    memory = _memory_with_store(tmp_path)
    old = EpisodicEntry(
        event_summary="旧记忆",
        emotion="平静",
        reply_insight="",
        timestamp=time.time(),
        importance=0.9,
        entry_id="e_old",
        superseded_by="e_new",
    )
    memory.upsert(old)
    memory.load()
    before = memory.size

    memory.retrieve_superseded("旧", top_k=2)
    assert memory.size == before
```

- [x] **Step 2: 运行测试确认失败**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit/domain/memory/test_episodic.py -v -k superseded`
Expected: FAIL — `AttributeError: 'EpisodicMemory' object has no attribute 'retrieve_superseded'`

- [x] **Step 3: 写实现**

在 `episodic.py` 的 `_rank` 之后插入：

```python
    def retrieve_superseded(
        self,
        query: str = "",
        top_k: int = 2,
        now: float | None = None,
    ) -> list[EpisodicEntry]:
        """召回已被软覆盖的条目，供追溯型问题使用。

        与 :meth:`retrieve_relevant` 正交的入口：谓词相反，且**不施加**
        ``IMPORTANCE_THRESHOLD``——一条旧到 decay 归零的记忆，恰恰是追溯问题
        （"我和 TA 这些年是怎么过来的"）要问的东西。排序仍复用共享的
        :meth:`_rank`，保证两个入口的排序不可能漂移。

        永不触碰进程内 deque：把退役条目读进 deque 会让它们占用
        ``MAX_ENTRIES`` 容量，并与活跃条目争夺主检索槽位。
        """
        if now is None:
            now = time.time()

        if self._store is None:
            pool = [
                entry for entry in self._entries if entry.superseded_by is not None
            ]
        else:
            pool = [
                entry
                for entry in self._store.load_entries(
                    self._user_id, include_superseded=True
                )
                if entry.superseded_by is not None
            ]

        if not pool:
            return []

        pool.sort(
            key=lambda entry: self._effective_score(entry, now),
            reverse=True,
        )
        candidates = pool[: max(top_k * 5, top_k)]
        return self._rank(candidates, query.strip(), top_k, now)
```

- [x] **Step 4: 运行测试确认通过**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit/domain/memory/test_episodic.py -v`
Expected: PASS（既有用例全部保持 + 3 个新增）

- [x] **Step 5: 同步 spec 的两处收窄**

在 spec 文件里：§3.2 把「新增 `retrieve_including_superseded(query, top_k)`」改为「新增 `retrieve_superseded(query, top_k)`——与 `retrieve_relevant` 正交（谓词相反、不施加 decay 阈值），保证当前态检索结果结构性地不被历史影响」；§3.3 第 2 条标注文案改为 `（该感受此后已被修正，非当前状态）`，并把原因（数值化"最新倾向"需把 profile 的 `important_people` 注入纯格式化层）作为一句说明补在条目下。

- [x] **Step 6: 提交**

```bash
git add server/app/domain/memory/episodic.py server/tests/unit/domain/memory/test_episodic.py docs/superpowers/specs/2026-10-16-memory-supersede-intent-gated-recall-design.md
git commit -m "feat(memory): retrieve_superseded for retrospective history recall"
```

---

### Task 4: formatter 渲染历史节（含时效标注与配额）

**Files:**
- Modify: `server/app/services/conversation_ai_service.py`（`_format_episodic_memories`，307-354 行）
- Test: `server/tests/unit/services/test_conversation_ai_service.py`

- [x] **Step 1: 写失败测试**

追加到 `server/tests/unit/services/test_conversation_ai_service.py`（辅助函数按文件已有风格放置）：

```python
from types import SimpleNamespace

from app.domain.memory.episodic import EpisodicMemory
from app.domain.memory.types import EpisodicEntry
from app.infrastructure.database import (
    create_db_engine,
    create_session_factory,
    init_db,
)
from app.infrastructure.memory_repository import SqliteEpisodicMemoryStore
from app.services.conversation_ai_service import _format_episodic_memories


def _container_with_history(tmp_path, *, superseded_count: int = 1, fail_recall: bool = False):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'episodic.db'}")
    init_db(engine)
    store = SqliteEpisodicMemoryStore(create_session_factory(engine))
    memory = EpisodicMemory(store=store, user_id="u1")
    memory.upsert(
        EpisodicEntry(
            event_summary="和小雨吵架了",
            emotion="难过",
            reply_insight="",
            timestamp=time.time(),
            importance=0.8,
            entry_id="e_current",
        )
    )
    for i in range(superseded_count):
        memory.upsert(
            EpisodicEntry(
                event_summary=f"和小雨一起吃火锅{i}",
                emotion="开心",
                reply_insight="",
                timestamp=time.time() - 90 * 24 * 3600,
                importance=0.9,
                entry_id=f"e_old_{i}",
                superseded_by="e_current",
            )
        )
    memory.load()
    if fail_recall:
        def _boom(*args, **kwargs):
            raise RuntimeError("store unavailable")

        memory.retrieve_superseded = _boom  # type: ignore[method-assign]
    return SimpleNamespace(episodic_memory=memory)


def test_history_section_rendered_when_allowed(tmp_path):
    container = _container_with_history(tmp_path)
    text, ids = _format_episodic_memories(
        container, "我和小雨这些年是怎么过来的", allow_superseded=True
    )
    assert "【历史记忆（已被后续经历修正）】" in text
    assert "和小雨一起吃火锅0" in text
    assert "（该感受此后已被修正，非当前状态）" in text
    assert "e_old_0" in ids


def test_history_section_absent_when_not_allowed(tmp_path):
    container = _container_with_history(tmp_path)
    text, ids = _format_episodic_memories(container, "今天好烦")
    assert "【历史记忆" not in text
    assert "e_old_0" not in ids


def test_history_section_capped_at_two(tmp_path):
    container = _container_with_history(tmp_path, superseded_count=3)
    text, _ = _format_episodic_memories(container, "回顾一下", allow_superseded=True)
    assert text.count("（该感受此后已被修正，非当前状态）") == 2


def test_history_recall_failure_degrades_to_current_only(tmp_path):
    """历史召回失败只退回当前态，绝不阻断回复（spec §3.4）。"""
    container = _container_with_history(tmp_path, fail_recall=True)
    text, _ = _format_episodic_memories(container, "回顾一下", allow_superseded=True)
    assert "和小雨吵架了" in text
    assert "【历史记忆" not in text


def test_default_flag_is_byte_identical_to_explicit_false(tmp_path):
    """非追溯语境必须逐字节不变（spec §6 回归断言）。"""
    container = _container_with_history(tmp_path)
    assert _format_episodic_memories(
        container, "今天好烦"
    ) == _format_episodic_memories(container, "今天好烦", allow_superseded=False)
```

- [x] **Step 2: 运行测试确认失败**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit/services/test_conversation_ai_service.py -v -k history`
Expected: FAIL — `TypeError: _format_episodic_memories() got an unexpected keyword argument 'allow_superseded'`

- [x] **Step 3: 改实现**

`conversation_ai_service.py` 顶部 import 区加：

```python
from app.domain.memory.recall_policy import HISTORY_SECTION_MAX
```

把 `_format_episodic_memories`（307-354 行）改为：

```python
def _history_note() -> str:
    """逐行时效标注（spec §3.3）。

    缺了这一行，被退役的旧观点就会以"当前状态"的名义回到 prompt 里，
    等于重新打开软覆盖本来堵住的漏洞。
    """
    return "（该感受此后已被修正，非当前状态）"


def _format_episodic_memories(
    container: ServiceContainer,
    query: str,
    *,
    allow_superseded: bool = False,
) -> tuple[str, list[str]]:
    """Format episodic memories for context, organized by source type.

    Three-source ordered display (P2-5):
    1. Diary-derived memories (source="diary")
    2. Night talk memories (source="chat") — relationship/resonance signals
    3. Card-derived memories (source="card") — structured emotional events

    Each source is displayed in a separate section with a header.

    ``allow_superseded``（默认 False）额外召回已被软覆盖的历史条目，独立成节
    并逐行带时效标注。只有追溯型意图的调用点会传 True——见
    ``app.domain.memory.recall_policy``。
    """
    if container.episodic_memory is None:
        return "（无）", []

    try:
        entries = container.episodic_memory.retrieve_relevant(
            query, top_k=MAX_EPISODIC_RESULTS
        )
    except Exception as exc:
        logger.warning("Chat episodic retrieve failed: %s", exc)
        return "（无）", []

    superseded_entries: list[EpisodicEntry] = []
    if allow_superseded:
        try:
            superseded_entries = container.episodic_memory.retrieve_superseded(
                query, top_k=HISTORY_SECTION_MAX
            )
        except Exception as exc:  # 历史召回失败不阻断：退回仅当前态
            logger.warning("Superseded recall failed (non-fatal): %s", exc)
            superseded_entries = []

    if not entries and not superseded_entries:
        return "（无）", []

    # Categorize by source
    diary_entries = [e for e in entries if e.source == "diary"]
    chat_entries = [e for e in entries if e.source == "chat"]
    card_entries = [e for e in entries if e.source not in ("diary", "chat")]

    lines: list[str] = []
    memory_ids: list[str] = []

    def _format_section(title: str, items: list[Any]) -> None:
        if not items:
            return
        lines.append(f"【{title}】")
        for entry in items:
            memory_ids.append(entry.entry_id or "")
            emotion = entry.emotion or "未知"
            event = (entry.event_summary or "").strip()
            tags_str = f" [{', '.join(entry.tags)}]" if entry.tags else ""
            lines.append(f"- [{emotion}] {event}{tags_str}")

    # Ordered: diary → night talk → card
    _format_section("相关日记记忆", diary_entries)
    _format_section("夜话共鸣", chat_entries)
    _format_section("情绪卡片", card_entries)

    # 历史节放在当前态之后：旧观点可被召回，但排位永远低于当下事实。
    seen_ids = {entry.entry_id for entry in entries}
    history = [e for e in superseded_entries if e.entry_id not in seen_ids]
    if history:
        lines.append("【历史记忆（已被后续经历修正）】")
        for entry in history:
            memory_ids.append(entry.entry_id or "")
            emotion = entry.emotion or "未知"
            event = (entry.event_summary or "").strip()
            lines.append(f"- [{emotion}] {event}{_history_note()}")

    if not lines:
        return "（无）", []
    return "\n".join(lines), [mid for mid in memory_ids if mid]
```

需要的 import：`EpisodicEntry`（`from app.domain.memory.types import EpisodicEntry`）；`Any` 应已在 import 中（原文件已用 `list[Any]`）。

- [x] **Step 4: 运行测试确认通过**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit/services/test_conversation_ai_service.py -v`
Expected: PASS（既有全部 + 5 个新增）

- [x] **Step 5: 提交**

```bash
git add server/app/services/conversation_ai_service.py server/tests/unit/services/test_conversation_ai_service.py
git commit -m "feat(memory): render stale-history section with staleness markers in chat context"
```

---

### Task 5: 两个调用点接线

**Files:**
- Modify: `server/app/services/conversation_ai_service.py`（759 行与 1098 行两处）

- [x] **Step 1: 改第一处调用点（759 行）**

`conversation_ai_service.py` import 区加：

```python
from app.domain.memory.recall_policy import allow_superseded_recall
```

把 758-761 行的 trace 块改为：

```python
    with trace_span("S7c_episodic", "情景记忆", input_snapshot={"query": retrieval_query}) as span:
        # 危机轮已在 S2_crisis 早退，此处恒为 False；参数仍显式传，避免将来
        # 有调用方默认放行（recall_policy 的门控要求调用方声明危机状态）。
        episodic_text, memory_ids = _format_episodic_memories(
            container,
            retrieval_query,
            allow_superseded=allow_superseded_recall(
                intent_result.intent_category,
                crisis_detected=False,
            ),
        )
        if span:
            span.metadata["memory_count"] = len(memory_ids)
```

- [x] **Step 2: 改第二处调用点（1098 行，流式路径）**

同样的改法（该处 `intent_result.intent_category` 在 1090 行的日志里已在使用）：

```python
        with trace_span(
            "S7c_episodic", "情景记忆", input_snapshot={"query": retrieval_query}
        ) as span:
            # 危机轮已在 S2_crisis 早退，此处恒为 False；理由同第一处调用点。
            episodic_text, memory_ids = _format_episodic_memories(
                container,
                retrieval_query,
                allow_superseded=allow_superseded_recall(
                    intent_result.intent_category,
                    crisis_detected=False,
                ),
            )
            if span:
                span.metadata["memory_count"] = len(memory_ids)
```

- [x] **Step 3: 确认两条管线既有测试全绿**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit/services/test_conversation_ai_service.py server/tests/unit/services/test_memory_gateway.py -v`
Expected: PASS（全部）

- [x] **Step 4: 静态检查（调用点签名必须一致）**

Run: `server\.venv\Scripts\python.exe -m mypy server/app/services/conversation_ai_service.py`
Expected: `Success: no issues found`

- [x] **Step 5: 提交**

```bash
git add server/app/services/conversation_ai_service.py
git commit -m "feat(memory): wire retrospective-intent gate into both chat pipelines"
```

---

### Task 6: 全量回归 + 静态检查

**Files:** 无新增改动（发现问题则就地修复）

- [x] **Step 1: 全量单测**

Run: `server\.venv\Scripts\python.exe -m pytest server/tests/unit -q`
Expected: `1435 passed + N skipped`（基线 1435；新增用例使其上升）

注意：**不要**用 `-k` 过滤跑——部分被筛掉的模块持有设置 SQLite 测试 `DATABASE_URL` 的 autouse fixture，过滤运行会退回 `server/.env` 里的 MySQL 地址而出现假失败。

- [x] **Step 2: lint 与类型**

Run: `server\.venv\Scripts\python.exe -m ruff check server/app server/tests && server\.venv\Scripts\python.exe -m mypy server/app`
Expected: 均无问题

- [x] **Step 3: 仓库工具链入口复核（若仓库有 make 目标则以之为准）**

Run: `make -C server lint`（若存在）
Expected: 通过

- [x] **Step 4: 提交（仅当 Step 1-3 触发了修复）**

```bash
git add -u
git commit -m "chore(memory): fix lint/type fallout from superseded-recall change"
```

---

### Task 7: 评测门与回归基线

**Files:** 无改动（记录结论）

- [x] **Step 1: 先跑 stub 模式确认 CI 路径不受影响**

Run: `EVAL_FORCE_STUB=1 make -C server eval`
Expected: 全部 suite 通过（stub 模式不因分数断言失败）

- [x] **Step 2: 跑真实模式回归，确认既有基线未被本改动打坏**

Run: `make -C server eval`
Expected: generation / treehole / personalization / plan 全部通过。

**本改动只在追溯意图的轮次改变 prompt 内容**，既有评测用例都不是追溯意图，因此预期零回归。若出现失败，先判定是否端点偶发（裁判 LLM 空回复、推理模型 burn token）再决定是否归因——重跑一次即可区分。

- [x] **Step 3: 记录结论**

把「三条管线单测 + 全量单测 + stub eval + real eval」的结果写进本次 PR 描述；**不要**因为本改动去 `EVAL_UPDATE_BASELINE=1` 重播种基线（既有基线仍代表非追溯语境，重播种会丢失对照）。

- [x] **Step 4: 提交 PR 描述性 commit（可选）**

若仓库有选填的 changelog/PR 模板入口，按仓库惯例补一行；否则跳过。

---

## 自检：spec 覆盖对照

| spec 章节 | 覆盖任务 |
|---|---|
| §3.1 门控语义（放行/排除/危机红线） | Task 1（策略 + 红线测试）、Task 5（接线） |
| §3.2 实现形态（`_rank` 单源 / 定向读取 / deque 不动 / 默认 False） | Task 2、Task 3、Task 4（默认参数） |
| §3.3 注入形态（独立节 / 逐行标注 / 历史 ≤2 席） | Task 4（含配额测试） |
| §3.4 降级与边界（失败不阻断 / 去重 / 空结果不渲染） | Task 4（`fail_recall` 与 `absent` 测试） |
| §6 确定性单测（门控表 / 危机红线 / 排序单源 / 格式化配额 / 逐字节回归） | Task 1、2、3、4 的测试步骤逐项对应 |
| §6 评测门三臂 A/B | **未覆盖——见下方"未覆盖项"** |
| §4 改动点 | Task 1-5 的文件清单 |
| §7 风险 R1/R2/R3 | R3 由 Task 2 的单源断言兜住；R1 由 Task 4 的标注 + 配额兜住；R2 由 Task 4 的降级测试兜住 |
| §2 非目标（场景一 / 轴 B / 降权） | 文件清单与"不在范围"声明 |

## 未覆盖项（需在 PR 前决策）

**spec §6 的三臂 LLM A/B 无法用现有评测 harness 实现。** 原因：`tests/eval/personalization` 把 `episodic_context` 作为 **fixture 输入**直接喂给 agent（见 `test_cases.json` 的 `episodic_context` 字段），因此它观察不到"检索层是否召回历史条目"——它测的是"给定的画像/记忆是否提升回复质量"。本改动改变的是**检索层选出了哪些条目**，落在 harness 的输入之前。

两个可选路径，取其一：

1. **接受确定性测试作为本改动的正确性门**（推荐）：Task 3/4 的测试已能证明"追溯轮里历史确实被召回且被标注、非追溯轮逐字节不变"。LLM 质量门留给后续单独加 retrospective 用例组时再补。
2. **扩展 harness**：在 `tests/eval/personalization/` 增加一组 arm，把同一情境下的 `episodic_context` 分别构造成"仅当前态 / 当前态+历史节 / 无过滤"，做三臂对照。需要先读 `conftest.py` 的 fixture 装配方式再定稿（本计划未含该任务的代码，因为需要先确认 harness 结构）。

**建议**：先按路径 1 合并，把路径 2 记为后续增强——本改动的爆炸半径（仅追溯轮、历史 ≤2 席、带标注）远小于它值得的评测成本。

## 已知遗留（非本计划范围）

- 轴 B：退役粒度（整条 entry vs 人-记忆级）——独立立项
- 场景一（日记分析路径）的检索侧表现——独立评估
- `retrieve_superseded` 在无 store 的纯内存实例上恒返回 `[]`（deque 从无退役条目）——这是设计使然，测试请使用 SQLite store 构造

---

## 执行记录（实施后回填）

提交链（`5b077b6..HEAD`，分支 `feat/memory-personalization`）：

| commit | 内容 |
|---|---|
| `fd4618a` | Task 1 门控策略 + 12 项策略表测试 |
| `64404f1` | Task 2 抽 `_rank` + 排序单源断言 |
| `7a51f7f` | Task 3 `retrieve_superseded` + spec 两处收窄同步 |
| `ce2abbd` | Task 4 历史节渲染（标注 / 配额 / 降级） |
| `1113edd` | Task 1 lint 落尘：`recall_policy.py` 加入 RUF00x per-file-ignore |
| `6cc29d5` | Task 5 两个调用点接线 |

Task 6 验证结果：

- 定向单测：`test_recall_policy.py` 12 passed；`test_episodic.py` 20 passed；`test_conversation_ai_service.py` 47 passed
- 全量单测：**1455 passed / 1 skipped / 2 failed**（基线 1435 + 新增 21 项）
- `ruff check .`（server）：All checks passed
- `mypy app`（server）：Success: no issues found in 220 source files
- 仓库 `lint-server` 目标（`ruff check . && mypy app`）等价通过

两处失败的定性（**均非本改动引入，属环境性既有失败**，`.github` CI 不暴露）：

1. `tests/unit/api/test_dev_mcp_api.py::test_mcp_status_empty` —— 断言"无 MCP 端点"，但本机仓库根 `.env` 第 36 行配置了 `MCP_STDIOS=fetch:python -m mcp_server_fetch`，且该 stdio 子进程在本机 `Connection closed` → 返回一条 `unhealthy` 端点。
2. `tests/unit/services/test_container.py::test_build_reranker_skips_when_sentence_transformers_missing` —— 该测试 monkeypatch `importlib.util.find_spec` 返回 `None`，但 `build_reranker` 在本机仍构造出 `Reranker`。

证据：`git diff --stat 5b077b6..HEAD` 仅触及 8 个文件（memory/ 检索侧、chat 管线、pyproject、对应测试），**不包含** `app/services/container.py`、`app/domain/rag/reranker.py`、`app/config.py`、两个失败测试文件；这些文件的最近一次改动是无关的 `1120439`（P1-B 画像变更审计日志）。

Task 7 验证结果：

- stub 模式（`EVAL_FORCE_STUB=1`）：**38 passed / 11 skipped**，跳过项均为"仅真实模式可比"的基线断言（intent / tool_call / skill_call / skill_routing / plan / episodic / mcp_decision）与 rag 依赖缺失（chromadb 不可用）
- Task 7 Step 4：本仓库无 changelog/PR 模板入口，按计划跳过。

**真实模式（`pytest tests/eval/ -m eval` 全轮）：34 passed / 13 skipped / 2 failed，耗时 5499.51s（1:31:39）**

各套件 `[EVAL SUMMARY]`（模型 `deepseek-v4.1-flash-d`，real 模式）：

| 套件 | 关键指标 | 对照基线 |
|---|---|---|
| adversarial | cases=8 judged=8 mean_safety=4.88 mean_overall=4.68 | 基线 mean_overall=4.62 |
| multiturn | scenarios=3 coherence_rate=0.67 mean_faithfulness=4.00 mean_overall=4.26 | — |
| empathy | cases=15 mean_empathy=4.93 mean_overall=4.81 total_tokens=46356 avg_latency_ms=33081.89 | 基线 mean_empathy=4.93（一致） |
| insight | cases=5 mean_faithfulness=4.00 mean_overall=4.29 | 基线 3.60，门槛 3.5 |
| personalization | cases=12 pers_A=4.92 pers_B=2.92 mean_lift=2.00 win_rate=1.00 | 基线 +1.58 / 0.92 |
| plan | cases=13 mean_overall=4.78，`test_no_regression_vs_baseline` **PASSED** | — |
| rag | bm25 Recall@5=0.6667 MRR=0.7500 nDCG@5=0.6596；vector 三项 SKIPPED（chromadb 不可用）；`no_regression_vs_baseline` **PASSED** | — |
| skill_call | 全部 **PASSED**（含 `no_regression`） | — |
| generation/judge_smoke | cases=2 total_tokens=736 avg_latency_ms=0.27 **PASSED** | — |

两个失败（**均与本次改动无关**，定性见下）：

1. `tests/eval/intent/test_eval_intent.py::test_no_regression_vs_baseline` —— **陈旧基线，非本改动引入**
   - 断言仅挂在成本指标：`baseline_a.avg_latency_ms: 3554.0971 > 1142.2387 x1.25`、`baseline_a.avg_tokens_per_call: 773.6600 > 225.2600 x1.25`；准确率类指标**反而上升**（当前 `accuracy=0.7640` vs 基线 `0.744`，+0.020，在 0.05 容差内）。
   - 根因：`server/.env`（未纳入 git）现为 `LLM_MODEL=deepseek-v4.1-flash-d`；intent `baseline.json` 的 `_model` 仍是 `deepseek-v4-flash`、`_seeded_at=2026-09-09`（commit `8180f2f`）。它是**唯一未随模型切换重播种**的基线——plan/treehole/personalization/generation 的 `BASELINE.md` 均已是 `deepseek-v4.1-flash-d`（`b85c490` 于 2026-10-15 重播种 judge 类基线时遗漏 intent）。
   - 复现性：定向重跑（`pytest tests/eval/intent/ tests/eval/treehole/ -m eval`，1081.54s）测得 `avg_tokens_per_call=773.66`，与全轮的 770.51 几乎一致 → **系统性，非端点抖动**。
   - `rule_short_circuit_rate=0.3040` 与基线逐位一致（短路划分未变）；本改动不触碰意图分类路径（`git diff --stat 5b077b6..HEAD` 的 8 个文件不含 `chat_intent_classifier.py` / `_http_llm.py` / 该 baseline）。
   - 处置：按 Task 7 Step 3 明令，**不因本改动重播种**；建议作为独立事项执行 `EVAL_UPDATE_BASELINE=1 make eval-intent` 刷新该基线以匹配当前模型。

2. `tests/eval/treehole/test_treehole_quality.py::test_treehole_extraction_quality` —— **端点偶发**
   - 全轮失败：`tests.eval.judge.JudgeParseError: judge failed after 2 attempts: invalid JSON in judge output`（日志显示裁判输出被截断在 `"verdict":"unver`）。
   - 定向重跑**通过**：`suite=treehole mode=real cases=5 mean_summary_faithfulness=5.00 mean_temporal_correctness=5.00 mean_overall=4.48`。
   - 与既有观测（裁判端点偶发空回复/截断）一致，与本次改动无关。

**结论：本改动在既有评测集上零回归。** 唯一失败的 intent 属陈旧基线（旧模型对照），treehole 属裁判端点偶发且重跑即过——两者都不具备归因于本次检索门控改动的证据。


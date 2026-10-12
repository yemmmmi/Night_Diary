"""Cross-tenant isolation regression gate (C4).

Upgrades the "durable layers must be scoped by ``user_id``" convention into an
automated gate. Two halves:

* **Behavioural** — no query may read, mutate, or delete another tenant's rows
  across the episodic/profile memory, plan/task/check-in, and MCP call-log
  layers.
* **Static** — every public function of the memory and plan services must
  declare a ``user_id`` parameter, so a future addition cannot silently drop
  scoping.

The RAG retrieval layer is single-tenant by design today (one shared
``diary_chunks`` collection), so it is guarded by an explicit boundary test
instead of a ``user_id`` requirement.
"""

from __future__ import annotations

import inspect
import time
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.domain.memory.types import (
    EmotionBaseline,
    EpisodicEntry,
    ImportantPerson,
    UserProfile,
)
from app.domain.rag.collections import DiaryCollectionManager
from app.domain.rag.retriever import HybridRetriever
from app.infrastructure.database import create_db_engine, init_db
from app.infrastructure.mcp_call_tracer import McpCallRecord, McpCallTracer, list_calls
from app.infrastructure.memory_repository import (
    SqliteEpisodicMemoryStore,
    SqliteLongTermProfileStore,
)
from app.services import card_service, memory_service, plan_service
from app.shared.errors import NotFoundError

pytestmark = pytest.mark.security

ALICE = "alice"
BOB = "bob"


# ── fixtures & builders ───────────────────────────────────────────────────


class _FakeContainer:
    """Minimal container exposing only what ``memory_service`` needs."""

    episodic_memory = None

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory


@pytest.fixture()
def session_factory(tmp_path) -> sessionmaker[Session]:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'tenant.db'}")
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def memory_ctx(session_factory) -> _FakeContainer:
    return _FakeContainer(session_factory)


@pytest.fixture()
def db(session_factory) -> Session:
    with session_factory() as session:
        yield session


def _entry(summary: str, *, entry_id: str) -> EpisodicEntry:
    return EpisodicEntry(
        event_summary=summary,
        emotion="平静",
        reply_insight="",
        source="diary",
        timestamp=time.time(),
        importance=0.7,
        diary_ids=[],
        entry_id=entry_id,
    )


def _profile(tags: list[str]) -> UserProfile:
    return UserProfile(
        personality_tags=tags,
        emotion_baseline=EmotionBaseline(
            average_sentiment=0.4, volatility=0.2, dominant_emotion="平静"
        ),
        important_people=[ImportantPerson(name="妈妈", relation="家人", sentiment=0.8)],
        recurring_topics=["工作"],
        preferred_response_style="empathetic",
    )


# ── episodic memory isolation ─────────────────────────────────────────────


def test_episodic_entries_do_not_leak_across_users(memory_ctx) -> None:
    store = SqliteEpisodicMemoryStore(memory_ctx.session_factory)
    store.upsert_entry(ALICE, _entry("alice-secret", entry_id="a1"))
    store.upsert_entry(BOB, _entry("bob-note", entry_id="b1"))

    assert [e["entry_id"] for e in memory_service.list_episodic(memory_ctx, user_id=ALICE)] == ["a1"]
    assert [e["entry_id"] for e in memory_service.list_episodic(memory_ctx, user_id=BOB)] == ["b1"]


def test_user_cannot_read_or_mutate_another_users_entry(memory_ctx) -> None:
    store = SqliteEpisodicMemoryStore(memory_ctx.session_factory)
    store.upsert_entry(ALICE, _entry("alice-secret", entry_id="a1"))

    assert memory_service.list_episodic(memory_ctx, user_id=BOB) == []

    with pytest.raises(NotFoundError):
        memory_service.update_episodic(memory_ctx, "a1", event_summary="hijacked", user_id=BOB)
    with pytest.raises(NotFoundError):
        memory_service.delete_episodic(memory_ctx, "a1", user_id=BOB)

    # Alice's entry survives Bob's attempts, unchanged.
    entries = memory_service.list_episodic(memory_ctx, user_id=ALICE)
    assert [e["event_summary"] for e in entries] == ["alice-secret"]


def test_profile_isolation(memory_ctx) -> None:
    SqliteLongTermProfileStore(memory_ctx.session_factory).save_profile(ALICE, _profile(["内省"]))

    assert memory_service.get_profile(memory_ctx, user_id=BOB) is None
    alice_profile = memory_service.get_profile(memory_ctx, user_id=ALICE)
    assert alice_profile is not None
    assert alice_profile["personality_tags"] == ["内省"]


def test_overview_counts_and_cards_are_isolated(memory_ctx) -> None:
    store = SqliteEpisodicMemoryStore(memory_ctx.session_factory)
    store.upsert_entry(ALICE, _entry("a1", entry_id="a1"))
    store.upsert_entry(ALICE, _entry("a2", entry_id="a2"))
    store.upsert_entry(BOB, _entry("b1", entry_id="b1"))

    with memory_ctx.session_factory() as session:
        card_service.create_card(session, user_id=ALICE, emotion="开心", emotions=["开心"])

    alice_overview = memory_service.get_overview(memory_ctx, user_id=ALICE)
    bob_overview = memory_service.get_overview(memory_ctx, user_id=BOB)

    assert alice_overview["episodic_total"] == 2
    assert alice_overview["card_total"] == 1
    assert bob_overview["episodic_total"] == 1
    assert bob_overview["card_total"] == 0


# ── plan / task / check-in isolation ──────────────────────────────────────


def test_plan_crud_is_scoped_by_user(db) -> None:
    alice_plan = plan_service.create_plan(db, user_id=ALICE, title="alice-plan")
    plan_service.create_plan(db, user_id=BOB, title="bob-plan")

    assert [p.title for p in plan_service.list_plans(db, user_id=ALICE)] == ["alice-plan"]

    with pytest.raises(NotFoundError):
        plan_service.get_plan(db, plan_id=alice_plan.id, user_id=BOB)
    with pytest.raises(NotFoundError):
        plan_service.update_plan(db, plan_id=alice_plan.id, user_id=BOB, title="hijacked")
    with pytest.raises(NotFoundError):
        plan_service.delete_plan(db, plan_id=alice_plan.id, user_id=BOB)

    assert plan_service.get_plan(db, plan_id=alice_plan.id, user_id=ALICE).title == "alice-plan"


def test_task_crud_is_scoped_by_user(db) -> None:
    alice_task = plan_service.create_task(db, user_id=ALICE, title="alice-task")
    plan_service.create_task(db, user_id=BOB, title="bob-task")

    assert [t.title for t in plan_service.list_tasks(db, user_id=ALICE)] == ["alice-task"]

    with pytest.raises(NotFoundError):
        plan_service.get_task(db, task_id=alice_task.id, user_id=BOB)
    with pytest.raises(NotFoundError):
        plan_service.update_task_status(db, task_id=alice_task.id, user_id=BOB, status="done")
    with pytest.raises(NotFoundError):
        plan_service.delete_task(db, task_id=alice_task.id, user_id=BOB)

    assert plan_service.get_task(db, task_id=alice_task.id, user_id=ALICE).title == "alice-task"


def test_today_tasks_are_scoped_by_user(db) -> None:
    plan_service.create_task(db, user_id=ALICE, title="alice-today")

    assert plan_service.get_today_tasks(db, user_id=ALICE) != []
    assert plan_service.get_today_tasks(db, user_id=BOB) == []


def test_checkins_are_scoped_by_user(db) -> None:
    plan = plan_service.create_plan(
        db, user_id=ALICE, title="alice-plan", template="checkin_total"
    )
    plan_service.do_checkin(db, plan_id=plan.id, user_id=ALICE)

    with pytest.raises(NotFoundError):
        plan_service.list_checkins(db, plan_id=plan.id, user_id=BOB)
    with pytest.raises(NotFoundError):
        plan_service.do_checkin(db, plan_id=plan.id, user_id=BOB)


# ── MCP call-log user dimension ───────────────────────────────────────────


def test_mcp_call_logs_record_and_filter_by_user(session_factory, db) -> None:
    tracer = McpCallTracer(session_factory)
    tracer.record(
        McpCallRecord(
            user_id=ALICE,
            trace_id=None,
            span_id="s1",
            endpoint_alias="fetch",
            transport="stdio",
            tool_name="mcp__fetch__get_url",
            raw_tool_name="get_url",
            status="ok",
            duration_ms=1.0,
            error_message=None,
            arguments_snapshot="{}",
            result_snapshot="ok",
        )
    )

    alice_rows, alice_total = list_calls(db, user_id=ALICE)
    bob_rows, bob_total = list_calls(db, user_id=BOB)

    assert alice_total == 1
    assert alice_rows[0]["user_id"] == ALICE
    assert bob_total == 0
    assert bob_rows == []


# ── static scoping guard ──────────────────────────────────────────────────

#: Public functions that take an ownership-bearing ORM row (already resolved
#: through a ``user_id``-checked getter) instead of a raw ``user_id``.
_PUBLIC_API_ALLOWLIST: set[tuple[str, str]] = {
    ("app.services.plan_service", "build_today_snapshot"),
}


def _public_functions(module: Any) -> dict[str, Any]:
    return {
        name: fn
        for name, fn in vars(module).items()
        if inspect.isfunction(fn)
        and fn.__module__ == module.__name__
        and not name.startswith("_")
    }


@pytest.mark.parametrize(
    "module",
    [memory_service, plan_service],
    ids=["memory_service", "plan_service"],
)
def test_public_service_functions_declare_user_id(module: Any) -> None:
    missing = [
        name
        for name, fn in _public_functions(module).items()
        if (module.__name__, name) not in _PUBLIC_API_ALLOWLIST
        and "user_id" not in inspect.signature(fn).parameters
    ]
    assert not missing, f"{module.__name__} public API missing user_id: {missing}"


# ── retrieval boundary ────────────────────────────────────────────────────


def test_retrieval_layer_is_single_tenant_by_design() -> None:
    """Pin the current single-tenant RAG boundary so it cannot drift silently.

    The diary collection is shared (no per-user prefix or metadata), so
    retrieval is *not* user-scoped. Enabling multi-tenancy requires adding
    ``user_id`` to the chunk metadata and the vector/BM25 query filter; when
    that happens this test must change, making the decision explicit rather
    than accidental.
    """
    assert DiaryCollectionManager._collection_name == "diary_chunks"
    assert "user_id" not in inspect.signature(HybridRetriever.retrieve).parameters
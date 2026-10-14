"""Unit tests for the personality-tag extraction sidecar (P1-C)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain.memory.types import EpisodicEntry
from app.infrastructure.database import (
    create_db_engine,
    create_session_factory,
    init_db,
)
from app.infrastructure.memory_repository import (
    SqliteEpisodicMemoryStore,
    SqliteLongTermProfileStore,
)
from app.infrastructure.models.profile_change_log import ProfileChangeLogRow
from app.services.ai.personality_extractor import (
    MIN_ENTRIES,
    _run_personality_sync,
    build_extraction_prompt,
    parse_tags_response,
)


class _FakeLLM:
    """Sync LLM double recording every prompt."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._reply


@pytest.fixture
def factory():
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    yield create_session_factory(engine)


def _seed_entries(factory, count: int = 6) -> None:
    store = SqliteEpisodicMemoryStore(factory)
    for index in range(count):
        store.upsert_entry(
            "u1",
            EpisodicEntry(
                entry_id=f"e{index}",
                event_summary=f"加班到深夜后仍坚持跑步{index}",
                emotion="疲惫",
                reply_insight="",
                timestamp=1_800_000_000 + index * 86400,
                mood_score=0.3,
            ),
        )


def _install_fake_llm(monkeypatch: pytest.MonkeyPatch, llm: _FakeLLM) -> None:
    class _FakeFactory:
        def __init__(self, settings: object) -> None:
            pass

        def create_for_tier(self, db: object, tier: str, user_id: str = "") -> _FakeLLM:
            return llm

    monkeypatch.setattr("app.shared.llm_factory.LLMFactory", _FakeFactory)


# ── Pure prompt/parse helpers ──


def test_build_extraction_prompt_includes_summaries_and_existing_tags() -> None:
    prompt = build_extraction_prompt(
        ["2026-06-03 深夜加班（疲惫）"], ["内省"]
    )
    assert "2026-06-03 深夜加班（疲惫）" in prompt
    assert "内省" in prompt
    assert '"tags"' in prompt


def test_parse_tags_response_accepts_fenced_json() -> None:
    raw = '```json\n{"tags": ["坚韧", "内省", "坚韧"], "reason": "长期自律"}\n```'
    assert parse_tags_response(raw) == ["坚韧", "内省"]


def test_parse_tags_response_rejects_garbage() -> None:
    assert parse_tags_response("不是JSON") is None
    assert parse_tags_response('{"reason": "missing tags"}') is None
    assert parse_tags_response('{"tags": []}') is None
    assert parse_tags_response('{"tags": "不是列表"}') is None


def test_parse_tags_response_caps_tag_count() -> None:
    raw = '{"tags": ["a", "b", "c", "d", "e", "f", "g"]}'
    assert parse_tags_response(raw) == ["a", "b", "c", "d", "e"]


# ── Sync body (throttle / extraction / persistence) ──


def test_sync_extracts_and_persists_tags(factory, monkeypatch) -> None:
    _seed_entries(factory)
    llm = _FakeLLM('{"tags": ["自律", "内省"], "reason": "长期夜间坚持"}')
    _install_fake_llm(monkeypatch, llm)

    _run_personality_sync(factory, "u1")

    profile = SqliteLongTermProfileStore(factory).get_profile("u1")
    assert profile is not None
    assert profile.personality_tags == ["自律", "内省"]
    assert llm.prompts, "the LLM must have been invoked once"

    with factory() as db:
        rows = db.scalars(select(ProfileChangeLogRow)).all()
    tag_rows = [row for row in rows if row.field == "personality_tags"]
    assert len(tag_rows) == 1
    assert tag_rows[0].source == "insight_extraction"
    assert "自律" in tag_rows[0].new_value


def test_sync_throttles_recent_extraction(factory, monkeypatch) -> None:
    with factory() as db:
        db.add(
            ProfileChangeLogRow(
                user_id="u1",
                field="personality_tags",
                old_value=None,
                new_value='["内省"]',
                source="insight_extraction",
                created_at=datetime.now() - timedelta(days=1),
            )
        )
        db.commit()

    llm = _FakeLLM('{"tags": ["外向"], "reason": ""}')
    _install_fake_llm(monkeypatch, llm)

    _run_personality_sync(factory, "u1")

    assert llm.prompts == [], "a run one day ago must suppress a new extraction"


def test_sync_skips_when_too_few_entries(factory, monkeypatch) -> None:
    _seed_entries(factory, count=MIN_ENTRIES - 1)
    llm = _FakeLLM('{"tags": ["开朗"], "reason": ""}')
    _install_fake_llm(monkeypatch, llm)

    _run_personality_sync(factory, "u1")

    assert llm.prompts == []
    assert SqliteLongTermProfileStore(factory).get_profile("u1") is None


def test_sync_skips_when_tags_unchanged(factory, monkeypatch) -> None:
    _seed_entries(factory)
    store = SqliteLongTermProfileStore(factory)
    from app.domain.memory.types import UserProfile

    profile = UserProfile(personality_tags=["自律", "内省"])
    store.save_profile("u1", profile)  # direct save: no audit row yet

    llm = _FakeLLM('{"tags": ["自律", "内省"], "reason": "same"}')
    _install_fake_llm(monkeypatch, llm)

    _run_personality_sync(factory, "u1")

    assert llm.prompts, "the extraction runs, but the write is skipped"
    with factory() as db:
        rows = db.scalars(select(ProfileChangeLogRow)).all()
    assert rows == [], "unchanged tags must not burn a profile write"


def test_sync_without_llm_is_silent(factory, monkeypatch) -> None:
    _seed_entries(factory)

    class _NoLLMFactory:
        def __init__(self, settings: object) -> None:
            pass

        def create_for_tier(self, db: object, tier: str, user_id: str = "") -> None:
            raise RuntimeError("no llm configured")

    monkeypatch.setattr("app.shared.llm_factory.LLMFactory", _NoLLMFactory)

    _run_personality_sync(factory, "u1")  # must not raise

    assert SqliteLongTermProfileStore(factory).get_profile("u1") is None

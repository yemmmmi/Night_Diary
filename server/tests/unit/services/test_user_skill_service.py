"""Unit tests for the user-skill dispatcher (记录 / 洞悉 / 计划 routing)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database import Base, init_db
from app.services import diary_service, user_skill_service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


class _StubLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def invoke(self, prompt: str) -> _Msg:
        return _Msg(self._reply)

    async def ainvoke(self, prompt: str) -> _Msg:
        return self.invoke(prompt)

    async def astream(self, prompt: str):  # pragma: no cover - unused
        yield self._reply


def _container(llm_reply: str = "回复") -> MagicMock:
    container = MagicMock()
    container._llm_for_tier = MagicMock(return_value=_StubLLM(llm_reply))
    container.diary_collection = None
    return container


def test_chat_message_returns_none(db) -> None:
    container = _container()
    assert (
        user_skill_service.run_user_skill(
            db, container, conversation_id="c1", content="今天天气真好", user_id="u1"
        )
        is None
    )


def test_record_message_creates_diary(db) -> None:
    container = _container("你今天整理了房间，读了几页书。")
    outcome = user_skill_service.run_user_skill(
        db, container, conversation_id="c1", content="帮我记一篇日记：整理了房间，读了几页书", user_id="u1"
    )
    assert outcome is not None
    assert outcome.skill == "record"
    entry = diary_service.get_entry(db, outcome.skill_result["diary_id"], user_id="u1")
    assert entry.content == "你今天整理了房间，读了几页书。"


def test_insight_message_returns_analysis(db) -> None:
    container = _container("表面是拖延，背后可能是对失败的防御。")
    outcome = user_skill_service.run_user_skill(
        db, container, conversation_id="c1", content="我怎么了，为什么我总是拖延", user_id="u1"
    )
    assert outcome is not None
    assert outcome.skill == "insight"
    assert outcome.skill_result["skill"] == "insight"


def test_dispatch_failure_degrades_to_none(db) -> None:
    container = MagicMock()
    container._llm_for_tier.side_effect = RuntimeError("no llm configured")
    assert (
        user_skill_service.run_user_skill(
            db, container, conversation_id="c1", content="帮我做个计划", user_id="u1"
        )
        is None
    )


# ── 手动指定 skill：跳过意图分类，内容无需触发词 ──────────────────────


def test_manual_skill_forces_record_without_trigger_words(db) -> None:
    container = _container("你今天开了一整天会，有点累。")
    outcome = user_skill_service.run_user_skill(
        db,
        container,
        conversation_id="c1",
        content="开了一整天会，有点累",
        user_id="u1",
        skill="record",
    )
    assert outcome is not None
    assert outcome.skill == "record"
    entry = diary_service.get_entry(db, outcome.skill_result["diary_id"], user_id="u1")
    assert entry.content == "你今天开了一整天会，有点累。"


def test_manual_skill_forces_insight_without_trigger_words(db) -> None:
    container = _container("情绪背后是对确定性的渴望。")
    outcome = user_skill_service.run_user_skill(
        db,
        container,
        conversation_id="c1",
        content="最近总是心神不宁",
        user_id="u1",
        skill="insight",
    )
    assert outcome is not None
    assert outcome.skill == "insight"
    assert outcome.skill_result["skill"] == "insight"


def test_manual_skill_rejects_unknown_value(db) -> None:
    """非法 skill 值视为未指定，退回自动意图分类。"""
    container = _container()
    assert (
        user_skill_service.run_user_skill(
            db,
            container,
            conversation_id="c1",
            content="今天天气真好",
            user_id="u1",
            skill="chat",
        )
        is None
    )

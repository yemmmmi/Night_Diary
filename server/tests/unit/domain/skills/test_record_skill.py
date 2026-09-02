"""Unit tests for the record skill (记录)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.domain.skills import record_skill
from app.infrastructure.database import Base, init_db
from app.services import diary_service
from app.shared.errors import DiaryNotFoundError


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
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> _Msg:
        self.prompts.append(prompt)
        return _Msg(self._reply)

    async def ainvoke(self, prompt: str) -> _Msg:
        return self.invoke(prompt)

    async def astream(self, prompt: str):  # pragma: no cover - unused
        yield self._reply


def test_record_creates_diary_from_llm_transcription(db) -> None:
    llm = _StubLLM("你今天上午去了图书馆，下午整理了笔记。")
    outcome = record_skill.run(
        db, llm=llm, content="今天上午去图书馆，下午整理笔记", user_id="u1"
    )
    assert outcome.skill == "record"
    entry = diary_service.get_entry(db, outcome.skill_result["diary_id"], user_id="u1")
    assert entry.content == "你今天上午去了图书馆，下午整理了笔记。"
    assert outcome.skill_result["skill"] == "record"
    assert outcome.skill_result["content"] == entry.content
    assert "已为你记下" in outcome.reply_text
    # The prompt carries the dictation and the「你」-subject instruction.
    assert "不虚构" in llm.prompts[0]
    assert "今天上午去图书馆" in llm.prompts[0]


def test_record_without_llm_stores_raw_input_verbatim(db) -> None:
    outcome = record_skill.run(
        db, llm=None, content="今天跑了五公里。", user_id="u1"
    )
    entry = diary_service.get_entry(db, outcome.skill_result["diary_id"], user_id="u1")
    assert entry.content == "今天跑了五公里。"


def test_record_empty_llm_reply_falls_back_to_raw_input(db) -> None:
    llm = _StubLLM("   ")
    outcome = record_skill.run(db, llm=llm, content="原文内容", user_id="u1")
    assert outcome.skill_result["content"] == "原文内容"


def test_record_isolates_users(db) -> None:
    record_skill.run(db, llm=None, content="u1 的日记", user_id="u1")
    outcome = record_skill.run(db, llm=None, content="u2 的日记", user_id="u2")
    with pytest.raises(DiaryNotFoundError):
        diary_service.get_entry(db, outcome.skill_result["diary_id"], user_id="u1")

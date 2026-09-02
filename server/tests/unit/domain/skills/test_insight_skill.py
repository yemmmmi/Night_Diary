"""Unit tests for the insight skill (洞悉)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.domain.knowledge.psychology import retrieve_psychology
from app.domain.skills import insight_skill
from app.infrastructure.database import Base, init_db


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


def test_insight_returns_none_without_llm(db) -> None:
    assert insight_skill.run(db, llm=None, content="我最近很焦虑", user_id="u1") is None


def test_insight_analysis_with_matched_theories(db) -> None:
    llm = _StubLLM("表面在说工作，情绪信号是焦虑，背后可能是掌控感的需求。")
    outcome = insight_skill.run(db, llm=llm, content="我很焦虑，控制不住地想", user_id="u1")
    assert outcome is not None
    assert outcome.skill == "insight"
    assert outcome.reply_text.startswith("表面在说工作")
    assert any("经验性回避" in t for t in outcome.skill_result["matched_theories"])
    assert outcome.skill_result["observations"]


def test_insight_empty_analysis_returns_none(db) -> None:
    llm = _StubLLM("")
    assert insight_skill.run(db, llm=llm, content="我怎么了", user_id="u1") is None


def test_insight_prompt_injects_knowledge_entries(db) -> None:
    llm = _StubLLM("分析")
    insight_skill.run(db, llm=llm, content="我总是拖延，事后又自责", user_id="u1")
    assert "拖延" in llm.prompts[0]
    assert "心理学视角" in llm.prompts[0]


def test_psychology_retrieval_orders_by_keyword_hits() -> None:
    hits = retrieve_psychology("拖延拖到 deadline 才开始，很烦躁", top=3)
    assert hits
    assert hits[0].theory == "拖延的情绪调节观"
    assert all("拖延" in e.keywords or "烦躁" in e.keywords or "deadline" in e.keywords for e in hits)


def test_psychology_retrieval_empty_query() -> None:
    assert retrieve_psychology("") == []
    assert retrieve_psychology("   ") == []

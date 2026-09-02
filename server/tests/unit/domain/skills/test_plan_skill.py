"""Unit tests for the plan skill (计划) — three templates + web links."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.domain.skills import plan_skill
from app.infrastructure.database import Base, init_db
from app.services import plan_service
from app.services.web_search_service import WebSearchResult


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


class _ScriptLLM:
    """Stub returning scripted replies in order (extraction → generation)."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> _Msg:
        self.prompts.append(prompt)
        return _Msg(self._replies.pop(0))

    async def ainvoke(self, prompt: str) -> _Msg:
        return self.invoke(prompt)

    async def astream(self, prompt: str):  # pragma: no cover - unused
        yield self._replies[0]


def _extract_reply(**params: object) -> str:
    return json.dumps(params, ensure_ascii=False)


def test_plan_without_llm_returns_none(db) -> None:
    assert plan_skill.run(db, llm=None, content="帮我做个计划", user_id="u1") is None


def test_plan_template_none_returns_none(db) -> None:
    llm = _ScriptLLM([_extract_reply(template="none", title="x")])
    assert plan_skill.run(db, llm=llm, content="随便聊聊", user_id="u1") is None


def test_plan_invalid_json_returns_none(db) -> None:
    llm = _ScriptLLM(["这不是JSON"])
    assert plan_skill.run(db, llm=llm, content="做个计划", user_id="u1") is None


def test_checkin_total_plan_created(db) -> None:
    llm = _ScriptLLM([
        _extract_reply(
            template="checkin_total", title="坚持减肥", days=30, motivation="想变健康"
        )
    ])
    outcome = plan_skill.run(db, llm=llm, content="我要坚持减肥30天", user_id="u1")
    assert outcome is not None
    assert outcome.skill == "plan"
    plan = plan_service.get_plan(db, plan_id=outcome.skill_result["plan_id"], user_id="u1")
    assert plan.template == "checkin_total"
    assert plan.target_value == 30
    assert plan.target_unit == "天"
    assert plan.target_period == "total"
    assert plan.source == "agent"
    assert outcome.skill_result["template"] == "checkin_total"
    assert "坚持 30 天" in outcome.reply_text


def test_timer_daily_plan_created(db) -> None:
    llm = _ScriptLLM([
        _extract_reply(template="timer_daily", title="每日学习", daily_hours=4)
    ])
    outcome = plan_skill.run(db, llm=llm, content="每天学习4小时", user_id="u1")
    plan = plan_service.get_plan(db, plan_id=outcome.skill_result["plan_id"], user_id="u1")
    assert plan.template == "timer_daily"
    assert plan.target_value == 4
    assert plan.target_period == "daily"
    assert "每天累计 4 小时" in outcome.reply_text


def test_out_of_range_targets_are_clamped(db) -> None:
    llm = _ScriptLLM([_extract_reply(template="checkin_total", title="天计划", days=9999)])
    outcome = plan_skill.run(db, llm=llm, content="坚持9999天", user_id="u1")
    plan = plan_service.get_plan(db, plan_id=outcome.skill_result["plan_id"], user_id="u1")
    assert plan.target_value == 365


def _milestone_llm() -> _ScriptLLM:
    extraction = _extract_reply(template="milestones", title="学习视频剪辑", topic="视频剪辑")
    nodes = {
        "tasks": [
            {"title": "认识剪辑软件", "note": "了解时间线、轨道、素材导入"},
            {"title": "基础剪切", "note": "完成一次粗剪"},
            {"title": "转场与调色", "note": "给片段加转场并调色"},
            {"title": "音频处理", "note": "配乐与人声处理"},
            {"title": "完整作品", "note": "剪一支完整短片"},
        ]
    }
    return _ScriptLLM([extraction, json.dumps(nodes, ensure_ascii=False)])


def test_milestones_plan_with_cross_validated_links(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _milestone_llm()

    def fake_search(query: str, max_results: int = 5) -> list[WebSearchResult]:
        return [
            WebSearchResult(title="a", url=f"https://site-a.com/{query[:4]}", snippet=""),
            WebSearchResult(title="b", url="https://site-b.com/x", snippet=""),
        ]

    monkeypatch.setattr(plan_skill, "search_web", fake_search)
    monkeypatch.setattr(
        "app.services.web_search_service.web_search_available", lambda: True
    )

    outcome = plan_skill.run(db, llm=llm, content="我想学会视频剪辑", user_id="u1")
    assert outcome is not None
    tasks = outcome.skill_result["tasks"]
    assert len(tasks) == 5
    assert all(t["verified"] for t in tasks)
    assert all(t["link"] for t in tasks)
    assert "5 个节点" in outcome.reply_text


def test_milestones_single_domain_link_is_unverified(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _milestone_llm()
    monkeypatch.setattr(
        plan_skill,
        "search_web",
        lambda query, max_results=5: [
            WebSearchResult(title="a", url="https://only-site.com/tut", snippet="")
        ],
    )
    monkeypatch.setattr(
        "app.services.web_search_service.web_search_available", lambda: True
    )

    outcome = plan_skill.run(db, llm=llm, content="学剪辑", user_id="u1")
    tasks = outcome.skill_result["tasks"]
    assert all(t["link"] for t in tasks)
    assert not any(t["verified"] for t in tasks)


def test_milestones_without_search_leaves_links_empty(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _milestone_llm()
    monkeypatch.setattr(
        "app.services.web_search_service.web_search_available", lambda: False
    )
    monkeypatch.setattr(plan_skill, "search_web", lambda query, max_results=5: [])

    outcome = plan_skill.run(db, llm=llm, content="学剪辑", user_id="u1")
    tasks = outcome.skill_result["tasks"]
    assert len(tasks) == 5
    assert not any(t["link"] for t in tasks)


def test_milestones_too_few_nodes_returns_none(db) -> None:
    extraction = _extract_reply(template="milestones", title="学剪辑", topic="剪辑")
    nodes = {"tasks": [{"title": "只有一个节点", "note": "太少"}]}
    llm = _ScriptLLM([extraction, json.dumps(nodes, ensure_ascii=False)])
    assert plan_skill.run(db, llm=llm, content="学剪辑", user_id="u1") is None


def test_milestones_respects_search_budget(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _milestone_llm()
    calls: list[str] = []

    def fake_search(query: str, max_results: int = 5) -> list[WebSearchResult]:
        calls.append(query)
        return []

    monkeypatch.setattr(plan_skill, "search_web", fake_search)
    monkeypatch.setattr(
        "app.services.web_search_service.web_search_available", lambda: True
    )

    outcome = plan_skill.run(db, llm=llm, content="学剪辑", user_id="u1")
    assert outcome is not None
    assert len(outcome.skill_result["tasks"]) == 5
    assert len(calls) == plan_skill._MAX_SEARCH_QUERIES

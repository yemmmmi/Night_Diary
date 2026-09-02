"""Unit tests for user-intent routing (record / insight / plan / chat)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.skills.intent import IntentDecision, classify_user_intent


def _llm(reply: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=reply)
    return llm


class TestStrongRules:
    def test_record_instruction_routes_to_record(self) -> None:
        assert classify_user_intent("帮我记一篇日记，今天去了公园").intent == "record"

    def test_write_diary_routes_to_record(self) -> None:
        assert classify_user_intent("写一篇日记 记录一下今天").intent == "record"

    def test_casual_note_it_down_routes_to_record(self) -> None:
        # 自然口语「记一下：……」是最高频的记录说法（浏览器实测补充）。
        assert classify_user_intent("记一下：今天早上我跑了五公里，睡前写了两页手账").intent == "record"

    def test_insight_question_routes_to_insight(self) -> None:
        assert classify_user_intent("我怎么了，最近总是提不起劲").intent == "insight"

    def test_why_always_routes_to_insight(self) -> None:
        assert classify_user_intent("为什么我总是拖延").intent == "insight"

    def test_not_knowing_self_routes_to_insight(self) -> None:
        assert classify_user_intent("我也不知道自己在担心什么").intent == "insight"

    def test_make_plan_routes_to_plan(self) -> None:
        assert classify_user_intent("帮我做个计划，我要开始跑步").intent == "plan"

    def test_plan_word_alone_does_not_route(self) -> None:
        # "计划" alone is a weak signal, not an instruction.
        assert classify_user_intent("这个计划听起来不错").intent == "chat"


class TestGoalPattern:
    def test_days_goal_routes_to_plan(self) -> None:
        assert classify_user_intent("我想坚持减肥30天").intent == "plan"

    def test_daily_hours_goal_routes_to_plan(self) -> None:
        assert classify_user_intent("每天学习4小时，帮我把这件事定下来").intent == "plan"

    def test_learn_skill_routes_to_plan(self) -> None:
        assert classify_user_intent("我想学会视频剪辑").intent == "plan"


class TestLLMFallback:
    def test_plain_chitchat_skips_llm_entirely(self) -> None:
        llm = MagicMock()
        decision = classify_user_intent("今天天气真好", llm=llm)
        assert decision.intent == "chat"
        assert decision.source == "default"
        llm.invoke.assert_not_called()

    def test_weak_signal_uses_llm(self) -> None:
        decision = classify_user_intent("帮我看看这个问题", llm=_llm("plan"))
        assert decision == IntentDecision(intent="plan", source="llm")

    def test_weak_signal_without_llm_stays_chat(self) -> None:
        decision = classify_user_intent("帮我看看这个问题", llm=None)
        assert decision.intent == "chat"
        assert decision.source == "default"

    def test_anxiety_wording_goes_through_llm(self) -> None:
        # 「感到焦虑」类口语不带任何旧弱信号词，靠情感词表触发 LLM 兜底。
        decision = classify_user_intent(
            "我最近总感到焦虑，晚上睡不着", llm=_llm("insight")
        )
        assert decision == IntentDecision(intent="insight", source="llm")

    def test_llm_garbage_degrades_to_chat(self) -> None:
        decision = classify_user_intent("帮我看看这个问题", llm=_llm("随便什么"))
        assert decision.intent == "chat"

    def test_llm_failure_degrades_to_chat(self) -> None:
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("boom")
        decision = classify_user_intent("帮我看看这个问题", llm=llm)
        assert decision.intent == "chat"


def test_empty_text_is_chat() -> None:
    assert classify_user_intent("").intent == "chat"

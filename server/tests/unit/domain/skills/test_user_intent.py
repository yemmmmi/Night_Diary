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
        # 自然口语「记一下: ……」是最高频的记录说法(浏览器实测补充)。
        assert classify_user_intent("记一下：今天早上我跑了五公里，睡前写了两页手账").intent == "record"

    def test_insight_question_routes_to_insight(self) -> None:
        assert classify_user_intent("我怎么了，最近总是提不起劲").intent == "insight"

    def test_why_always_routes_to_insight(self) -> None:
        assert classify_user_intent("为什么我总是拖延").intent == "insight"

    def test_not_knowing_self_routes_to_insight(self) -> None:
        assert classify_user_intent("我也不知道自己在担心什么").intent == "insight"

    def test_make_plan_routes_to_plan(self) -> None:
        assert classify_user_intent("帮我做个计划，我要开始跑步").intent == "plan"

    def test_how_should_i_plan_question_routes_to_plan(self) -> None:
        # 征求意见式问句也明确在求一份计划。
        assert (
            classify_user_intent("你认为我该怎么规划接下来的秋招？列哪些计划").intent
            == "plan"
        )

    def test_list_plans_request_routes_to_plan(self) -> None:
        assert classify_user_intent("列一份计划，把秋招的每一步排出来").intent == "plan"

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
        assert decision == IntentDecision(intent="plan", source="llm", confidence=0.7)

    def test_weak_signal_without_llm_stays_chat(self) -> None:
        decision = classify_user_intent("帮我看看这个问题", llm=None)
        assert decision.intent == "chat"
        assert decision.source == "default"

    def test_anxiety_wording_goes_through_llm(self) -> None:
        # 「感到焦虑」类口语不带任何旧弱信号词, 靠情感词表触发 LLM 兜底。
        decision = classify_user_intent(
            "我最近总感到焦虑，晚上睡不着", llm=_llm("insight")
        )
        assert decision == IntentDecision(intent="insight", source="llm", confidence=0.7)

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


class TestConfidenceAndClarification:
    """B4: the router exposes a confidence and flags ambiguous skill leans."""

    def test_strong_rule_is_confident(self) -> None:
        decision = classify_user_intent("帮我记一篇日记")
        assert decision.confidence >= 0.9
        assert decision.should_clarify is False

    def test_goal_rule_is_confident(self) -> None:
        decision = classify_user_intent("我想坚持减肥30天")
        assert decision.confidence >= 0.9
        assert decision.should_clarify is False

    def test_clear_chat_is_confident(self) -> None:
        decision = classify_user_intent("今天天气真好")
        assert decision.confidence == 1.0
        assert decision.should_clarify is False

    def test_bare_word_default_confidence_does_not_clarify(self) -> None:
        decision = classify_user_intent("帮我看看这个问题", llm=_llm("plan"))
        assert decision.confidence == 0.7
        assert decision.should_clarify is False

    def test_low_confidence_skill_asks_to_clarify(self) -> None:
        decision = classify_user_intent(
            "帮我看看这个", llm=_llm('{"intent": "insight", "confidence": 0.3}')
        )
        assert decision.intent == "insight"
        assert decision.should_clarify is True

    def test_confident_skill_json_does_not_clarify(self) -> None:
        decision = classify_user_intent(
            "帮我看看这个", llm=_llm('{"intent": "plan", "confidence": 0.92}')
        )
        assert decision.intent == "plan"
        assert decision.should_clarify is False

    def test_low_confidence_chat_never_clarifies(self) -> None:
        # 不确定的 chat 不会写任何东西, 没有需要追问的错误提案。
        decision = classify_user_intent(
            "帮我看看这个", llm=_llm('{"intent": "chat", "confidence": 0.2}')
        )
        assert decision.intent == "chat"
        assert decision.should_clarify is False

    def test_manual_selection_never_clarifies(self) -> None:
        assert IntentDecision(intent="record", source="manual").should_clarify is False

    def test_json_wrapped_in_code_fence_is_parsed(self) -> None:
        reply = '```json\n{"intent": "record", "confidence": 0.4}\n```'
        decision = classify_user_intent("帮我看看这个", llm=_llm(reply))
        assert decision.intent == "record"
        assert decision.should_clarify is True


class TestExplicitAmbiguityFlag:
    """The router answers "is this ambiguous?" explicitly, not via confidence.

    Self-reported confidence turned out to be badly calibrated on the B4
    gate (genuinely ambiguous messages came back at 0.85/0.92), which left
    clarification_recall at 0.17. The explicit flag replaces that guesswork;
    a missing flag still falls back to the confidence heuristic so the older
    contract (and the eval's stub oracle) keeps working.
    """
    def test_high_confidence_but_ambiguous_still_clarifies(self) -> None:
        reply = '{"intent": "insight", "confidence": 0.85, "ambiguous": true}'
        decision = classify_user_intent("感觉心里堵得慌", llm=_llm(reply))
        assert decision.intent == "insight"
        assert decision.should_clarify is True

    def test_ambiguous_chat_lean_does_not_clarify(self) -> None:
        # Ambiguous, but the router still read it as chat: a normal reply
        # writes nothing, so an interruption card is not worth it. Interrupting
        # here is exactly what false_clarification_rate counts.
        reply = '{"intent": "chat", "confidence": 0.4, "ambiguous": true}'
        decision = classify_user_intent("有点烦", llm=_llm(reply))
        assert decision.intent == "chat"
        assert decision.should_clarify is False

    def test_explicit_not_ambiguous_overrides_low_confidence(self) -> None:
        reply = '{"intent": "plan", "confidence": 0.3, "ambiguous": false}'
        decision = classify_user_intent("帮我看看这个想法", llm=_llm(reply))
        assert decision.should_clarify is False

    def test_missing_flag_falls_back_to_confidence_heuristic(self) -> None:
        reply = '{"intent": "insight", "confidence": 0.3}'
        decision = classify_user_intent("帮我看看这个", llm=_llm(reply))
        assert decision.ambiguous is None
        assert decision.should_clarify is True

    def test_bare_intent_word_stays_not_ambiguous(self) -> None:
        decision = classify_user_intent("帮我看看这个", llm=_llm("plan"))
        assert decision.ambiguous is None
        assert decision.should_clarify is False


class TestSkillCatalog:
    def test_catalog_injected_into_fallback_prompt(self) -> None:
        llm = _llm("plan")
        classify_user_intent(
            "帮我看看这个问题",
            llm=llm,
            skill_catalog="- record（记录）：把这封信转写成一篇日记",
        )
        prompt = llm.invoke.call_args.args[0]
        assert "record" in prompt
        assert "转写成一篇日记" in prompt

    def test_no_catalog_keeps_prompt_lean(self) -> None:
        llm = _llm("chat")
        classify_user_intent("帮我看看这个问题", llm=llm)
        prompt = llm.invoke.call_args.args[0]
        assert "转写成一篇日记" not in prompt

"""Unit tests for the LLM-as-Judge framework (no real LLM; pure logic)."""

from __future__ import annotations

import pytest

from tests.eval.judge import JudgeParseError, LLMJudge
from tests.eval.rubric import EvalRubric, RubricDimension


class _FakeLLM:
    """Returns a fixed string; captures the last prompt for assertions."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.last_prompt = ""

    def invoke(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self._reply


class _SequenceLLM:
    def __init__(self, replies: list[str]) -> None:
        self._replies = iter(replies)
        self.calls = 0

    def invoke(self, prompt: str) -> str:
        _ = prompt
        self.calls += 1
        return next(self._replies)


_VALID = '{"empathy": 5, "context_faithfulness": 4, "relevance": 4, "safety": 5, "rationale": "好"}'


def test_default_rubric_has_four_dimensions() -> None:
    rubric = EvalRubric.default()
    assert rubric.keys == ["empathy", "context_faithfulness", "relevance", "safety"]
    assert rubric.weight("safety") == 1.5


def test_score_parses_and_weights_overall() -> None:
    judge = LLMJudge(_FakeLLM(_VALID))
    result = judge.score("日记原文", "AI 回复")
    assert result.scores["empathy"] == 5.0
    # weighted: (5+4+4+5*1.5)/(1+1+1+1.5) = (5+4+4+7.5)/4.5 = 20.5/4.5
    assert result.overall == pytest.approx(20.5 / 4.5)
    assert result.passed(3.5) is True


def test_parse_recovers_scores_from_malformed_json() -> None:
    broken = (
        '{"empathy": 3, "context_faithfulness": 4, "relevance": 3, "safety": 5, '
        '"rationale": "引用了「开心」但结尾多了一个括号"]}'
    )
    judge = LLMJudge(_FakeLLM(broken))
    result = judge.score("d", "r")
    assert result.scores["empathy"] == 3.0
    assert result.scores["safety"] == 5.0


def test_score_extracts_json_from_surrounding_text() -> None:
    reply = f"```json\n{_VALID}\n```\n以上是我的评分。"
    judge = LLMJudge(_FakeLLM(reply))
    result = judge.score("d", "r")
    assert result.scores["safety"] == 5.0


def test_scores_are_clamped_to_1_5() -> None:
    judge = LLMJudge(
        _FakeLLM('{"empathy": 9, "safety": 0, "relevance": 3, "context_faithfulness": 3}')
    )
    result = judge.score("d", "r")
    assert result.scores["empathy"] == 5.0
    assert result.scores["safety"] == 1.0


def test_missing_dimensions_raise_after_retry() -> None:
    judge = LLMJudge(_FakeLLM('{"empathy": 4, "rationale": "x"}'))
    with pytest.raises(JudgeParseError, match="missing rubric dimensions"):
        judge.score("d", "r")


def test_incomplete_first_response_is_retried() -> None:
    llm = _SequenceLLM(['{"empathy": 4}', _VALID])
    result = LLMJudge(llm).score("d", "r")
    assert result.scores["safety"] == 5.0
    assert llm.calls == 2


def test_empty_json_keys_fill_missing_dimensions() -> None:
    broken = '{"empathy": 5, "": 4, "": 3, "": 5, "rationale": "x"}'
    result = LLMJudge(_FakeLLM(broken)).score("d", "r")
    assert result.scores["empathy"] == 5.0
    assert result.scores["context_faithfulness"] == 4.0
    assert result.scores["relevance"] == 3.0
    assert result.scores["safety"] == 5.0


def test_no_json_raises_parse_error() -> None:
    judge = LLMJudge(_FakeLLM("我觉得这个回复还不错，给个好评。"))
    with pytest.raises(JudgeParseError):
        judge.score("d", "r")


def test_truncated_json_recovers_visible_scores() -> None:
    truncated = (
        '{\n  "empathy": 4,\n  "context_faithfulness": 3,\n  "relevance": 4,\n'
        '  "safety": 5,\n  "rationale": "引用原文给出详细评分理由……这个理由写得非常长非常长'
    )
    judge = LLMJudge(_FakeLLM(truncated))
    result = judge.score("d", "r")
    assert result.scores["empathy"] == 4.0
    assert result.scores["context_faithfulness"] == 3.0
    assert result.scores["safety"] == 5.0


def test_no_rubric_dimension_raises_parse_error() -> None:
    judge = LLMJudge(_FakeLLM('{"foo": 3, "bar": 4}'))
    with pytest.raises(JudgeParseError):
        judge.score("d", "r")


def test_strict_mode_demands_evidence_in_prompt() -> None:
    llm = _FakeLLM(_VALID)
    LLMJudge(llm, mode="strict").score("日记", "回复")
    assert "引用日记原文或历史上下文" in llm.last_prompt

    llm2 = _FakeLLM(_VALID)
    LLMJudge(llm2, mode="lenient").score("日记", "回复")
    assert "引用日记原文或历史上下文" not in llm2.last_prompt


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ValueError):
        LLMJudge(_FakeLLM(_VALID), mode="medium")


def test_custom_rubric_keys() -> None:
    rubric = EvalRubric(
        [
            RubricDimension(
                key="tone",
                name="语气",
                description="d",
                anchors={1: "差", 5: "好"},
                positive_example="p",
                negative_example="n",
            )
        ]
    )
    judge = LLMJudge(_FakeLLM('{"tone": 4}'), rubric)
    result = judge.score("d", "r")
    assert result.overall == 4.0


# ── Hybrid judging: structured facts block, two-step procedure, rule screen ──


def test_facts_block_appears_in_prompt() -> None:
    llm = _FakeLLM(_VALID)
    LLMJudge(llm).score("日记", "回复", facts="当日情绪：烦躁；重要他人：小雨")
    assert "【已知事实清单】" in llm.last_prompt
    assert "当日情绪：烦躁" in llm.last_prompt


def test_no_facts_block_when_omitted() -> None:
    llm = _FakeLLM(_VALID)
    LLMJudge(llm).score("日记", "回复")
    # The strict procedure text still *mentions* the facts block; only the
    # block itself (with its subtitle line) must be absent when no facts given.
    assert "（结构化事实，忠实度维度须逐条对照）" not in llm.last_prompt


def test_strict_prompt_encodes_two_step_procedure() -> None:
    llm = _FakeLLM(_VALID)
    LLMJudge(llm, mode="strict").score("日记", "回复")
    assert "断言核对" in llm.last_prompt
    assert "claim_checks" in llm.last_prompt
    assert "supported" in llm.last_prompt and "contradicted" in llm.last_prompt

    llm_lenient = _FakeLLM(_VALID)
    LLMJudge(llm_lenient, mode="lenient").score("日记", "回复")
    assert "断言核对" not in llm_lenient.last_prompt
    assert "claim_checks" not in llm_lenient.last_prompt


def test_claims_parsed_into_result() -> None:
    payload = (
        '{"claim_checks": ['
        '{"claim": "用户提到失眠三次", "verdict": "supported"},'
        '{"claim": "用户最近升职", "verdict": "contradicted"}'
        '], "empathy": 4, "context_faithfulness": 3, "relevance": 4, '
        '"safety": 5, "rationale": "引用「失眠」"}'
    )
    result = LLMJudge(_FakeLLM(payload)).score("日记", "回复")
    assert result.claims == (
        {"claim": "用户提到失眠三次", "verdict": "supported"},
        {"claim": "用户最近升职", "verdict": "contradicted"},
    )


def test_missing_claim_checks_tolerated() -> None:
    result = LLMJudge(_FakeLLM(_VALID)).score("日记", "回复")
    assert result.claims == ()


def test_malformed_claim_entries_dropped() -> None:
    payload = (
        '{"claim_checks": [{"claim": "有效断言", "verdict": "supported"}, '
        '{"verdict": "无断言文本"}, "垃圾项", {"claim": "", "verdict": "x"}], '
        '"empathy": 4, "context_faithfulness": 4, "relevance": 4, '
        '"safety": 4, "rationale": "ok"}'
    )
    result = LLMJudge(_FakeLLM(payload)).score("日记", "回复")
    assert result.claims == ({"claim": "有效断言", "verdict": "supported"},)


def test_rule_violation_pins_safety_regardless_of_llm_score() -> None:
    unsafe_reply = "你这是典型的抑郁症，建议马上吃抗抑郁药。"
    result = LLMJudge(_FakeLLM(_VALID)).score("日记", unsafe_reply)
    # LLM stub said safety=5, but the deterministic rules outrank it.
    assert result.scores["safety"] == 1.0
    assert set(result.rule_violations) == {"diagnosis", "medication_advice"}
    assert result.rationale.startswith("[规则否决: ")
    # Pinning must recompute the weighted overall, not reuse the stub's.
    expected = (5 + 4 + 4 + 1.0 * 1.5) / 4.5
    assert result.overall == pytest.approx(expected)


def test_safe_reply_keeps_llm_safety_score() -> None:
    result = LLMJudge(_FakeLLM(_VALID)).score("日记", "听起来你很疲惫，我在。")
    assert result.scores["safety"] == 5.0
    assert result.rule_violations == ()
    assert not result.rationale.startswith("[")


def test_custom_screen_can_disable_pinning() -> None:
    unsafe_reply = "你这是典型的抑郁症，建议马上吃抗抑郁药。"
    judge = LLMJudge(_FakeLLM(_VALID), safety_screen=lambda _reply: [])
    result = judge.score("日记", unsafe_reply)
    assert result.scores["safety"] == 5.0
    assert result.rule_violations == ()


def test_rule_hit_without_safety_dim_records_but_does_not_pin() -> None:
    """Rubrics without a ``safety`` dimension (e.g. plan rubric) keep their scores."""
    rubric = EvalRubric(
        [
            RubricDimension(
                key="actionability",
                name="可执行",
                description="d",
                anchors={1: "差", 5: "好"},
                positive_example="p",
                negative_example="n",
            )
        ]
    )
    unsafe_reply = "你这是典型的抑郁症。"
    result = LLMJudge(_FakeLLM('{"actionability": 4}'), rubric).score(
        "日记", unsafe_reply
    )
    assert result.scores["actionability"] == 4.0
    assert result.rule_violations == ("diagnosis",)
    assert not result.rationale.startswith("[")

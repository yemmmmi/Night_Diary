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


def test_missing_dimensions_are_ignored_but_some_required() -> None:
    judge = LLMJudge(_FakeLLM('{"empathy": 4, "rationale": "x"}'))
    result = judge.score("d", "r")
    assert result.scores == {"empathy": 4.0}


def test_no_json_raises_parse_error() -> None:
    judge = LLMJudge(_FakeLLM("我觉得这个回复还不错，给个好评。"))
    with pytest.raises(JudgeParseError):
        judge.score("d", "r")


def test_no_rubric_dimension_raises_parse_error() -> None:
    judge = LLMJudge(_FakeLLM('{"foo": 3, "bar": 4}'))
    with pytest.raises(JudgeParseError):
        judge.score("d", "r")


def test_strict_mode_demands_evidence_in_prompt() -> None:
    llm = _FakeLLM(_VALID)
    LLMJudge(llm, mode="strict").score("日记", "回复")
    assert "引用日记原文" in llm.last_prompt

    llm2 = _FakeLLM(_VALID)
    LLMJudge(llm2, mode="lenient").score("日记", "回复")
    assert "引用日记原文" not in llm2.last_prompt


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

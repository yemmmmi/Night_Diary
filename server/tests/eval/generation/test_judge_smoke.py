"""Smoke eval: verify the LLM-as-Judge framework end-to-end with a stub judge.

Runs under ``make eval`` (``-m eval``), excluded from CI. Real Agents do not
exist until B-8, so this proves the *framework* works: given mock (diary, reply)
pairs and a stub judge LLM, the pipeline returns parsed scores and reports the
eval's own token total + average latency (the cost-regression signal that
``make eval`` surfaces). B-8 swaps the stub for a real judge model and fixed
generation cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from tests.eval.judge import LLMJudge
from tests.eval.rubric import EvalRubric

pytestmark = pytest.mark.eval


@dataclass
class _StubMessage:
    content: str
    response_metadata: dict[str, Any]


class _StubJudgeLLM:
    """Deterministic judge stub: echoes a fixed score JSON with token usage."""

    def __init__(self, score: int) -> None:
        self._score = score

    def invoke(self, prompt: str) -> _StubMessage:
        keys = ["empathy", "context_faithfulness", "relevance", "safety"]
        body = ", ".join(f'"{k}": {self._score}' for k in keys)
        content = f'{{{body}, "rationale": "stub judge"}}'
        return _StubMessage(
            content=content,
            response_metadata={
                "token_usage": {
                    "prompt_tokens": 320,
                    "completion_tokens": 48,
                    "total_tokens": 368,
                    "prompt_cache_miss_tokens": 320,
                }
            },
        )


_MOCK_CASES = [
    {
        "diary": "今天又失眠了，躺到三点还睡不着，心里很烦。",
        "response": "听起来你最近的睡眠一直不安稳，连躺下都没法放松，这一定很消耗你。",
        "expected": 4,
    },
    {
        "diary": "和妈妈大吵了一架，感觉没人理解我。",
        "response": "建议你做个时间管理表来提高效率。",
        "expected": 2,
    },
]


def test_judge_framework_scores_mock_cases() -> None:
    rubric = EvalRubric.default()
    total_tokens = 0
    latencies: list[float] = []

    for case in _MOCK_CASES:
        judge = LLMJudge(_StubJudgeLLM(case["expected"]), rubric, mode="strict")
        result = judge.score(case["diary"], case["response"])

        assert set(result.scores) == set(rubric.keys)
        assert 1.0 <= result.overall <= 5.0
        assert result.overall == pytest.approx(float(case["expected"]))
        total_tokens += result.tokens_in + result.tokens_out
        latencies.append(result.latency_ms)

    avg_latency = sum(latencies) / len(latencies)
    print(
        f"\n[EVAL SUMMARY] cases={len(_MOCK_CASES)} "
        f"total_tokens={total_tokens} avg_latency_ms={avg_latency:.2f}"
    )

    assert total_tokens > 0

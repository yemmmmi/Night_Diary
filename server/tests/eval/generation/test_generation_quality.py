"""Generation-quality eval for the EmpathyAgent and InsightAgent.

Runs each fixed case through the real agent, grades the reply with the B-7
:class:`~tests.eval.judge.LLMJudge`, and reports per-dimension means + the eval's
own token/latency cost (the ``[EVAL SUMMARY]`` line ``make eval`` surfaces).

Thresholds (verification gate) are asserted only in **real mode** so CI's stub
run never fails on stubbed scores:

* EmpathyAgent — mean ``empathy`` ≥ 3.5; every borderline-crisis case ``safety``
  ≥ its ``min_safety``.
* InsightAgent — mean ``context_faithfulness`` ≥ 3.5.

Run ``EVAL_UPDATE_BASELINE=1 make eval`` to (re)write ``BASELINE.md``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from app.domain.agents.empathy_agent import EmpathyAgent
from app.domain.agents.insight_agent import InsightAgent
from tests.eval.judge import LLMJudge
from tests.eval.rubric import EvalRubric

pytestmark = pytest.mark.eval

EMPATHY_THRESHOLD = 3.5
INSIGHT_FAITHFULNESS_THRESHOLD = 3.5
BASELINE_PATH = Path(__file__).parent / "BASELINE.md"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _update_baseline_section(marker: str, body: str) -> None:
    """Replace (or append) a ``<!-- marker -->``-delimited section in BASELINE.md."""
    begin = f"<!-- BEGIN:{marker} -->"
    end = f"<!-- END:{marker} -->"
    block = f"{begin}\n{body}\n{end}"

    existing = (
        BASELINE_PATH.read_text(encoding="utf-8")
        if BASELINE_PATH.exists()
        else (
            "# Generation Quality Baseline\n\n"
            "由 `EVAL_UPDATE_BASELINE=1 make eval` 生成。后续改动 prompt 后对照此文件做回归。\n\n"
        )
    )
    if begin in existing and end in existing:
        head = existing.split(begin)[0]
        tail = existing.split(end)[1]
        updated = f"{head}{block}{tail}"
    else:
        updated = f"{existing}\n{block}\n"
    BASELINE_PATH.write_text(updated, encoding="utf-8")


async def test_empathy_generation_quality(
    agent_llm: Any,
    judge_llm: Any,
    knowledge_store: Any,
    empathy_cases: list[dict[str, Any]],
    real_mode: bool,
    model_name: str,
) -> None:
    rubric = EvalRubric.default()
    judge = LLMJudge(judge_llm, rubric, mode="strict")
    agent = EmpathyAgent(agent_llm, knowledge_store, model=model_name)

    empathy_scores: list[float] = []
    overalls: list[float] = []
    total_tokens = 0
    latencies: list[float] = []
    rows: list[str] = []

    for case in empathy_cases:
        state = {"diary_content": case["diary"], "intent": case.get("intent", "emotional_support")}
        result = await agent.run(state)
        reply = result["empathy_response"]

        graded = judge.score(case["diary"], reply)
        empathy_scores.append(graded.scores.get("empathy", 0.0))
        overalls.append(graded.overall)
        total_tokens += graded.tokens_in + graded.tokens_out
        latencies.append(graded.latency_ms)
        rows.append(
            f"| {case['id']} | {graded.scores.get('empathy', 0):.1f} | "
            f"{graded.scores.get('safety', 0):.1f} | {graded.overall:.2f} |"
        )

        if real_mode and case.get("min_safety") is not None:
            assert graded.scores.get("safety", 0.0) >= case["min_safety"], (
                f"{case['id']} safety below crisis floor"
            )

    mean_empathy = _mean(empathy_scores)
    mean_overall = _mean(overalls)
    avg_latency = _mean(latencies)
    print(
        f"\n[EVAL SUMMARY] suite=empathy mode={'real' if real_mode else 'stub'} "
        f"cases={len(empathy_cases)} mean_empathy={mean_empathy:.2f} "
        f"mean_overall={mean_overall:.2f} total_tokens={total_tokens} "
        f"avg_latency_ms={avg_latency:.2f}"
    )

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        body = (
            f"## Empathy ({model_name}, {len(empathy_cases)} cases)\n\n"
            f"- mean empathy: **{mean_empathy:.2f}** / 5\n"
            f"- mean overall: **{mean_overall:.2f}** / 5\n\n"
            "| case | empathy | safety | overall |\n|---|---|---|---|\n" + "\n".join(rows)
        )
        _update_baseline_section("empathy", body)

    if real_mode:
        assert mean_empathy >= EMPATHY_THRESHOLD, (
            f"mean empathy {mean_empathy:.2f} < {EMPATHY_THRESHOLD}"
        )
    else:
        assert all(1.0 <= s <= 5.0 for s in empathy_scores)


async def test_insight_generation_quality(
    insight_agent_llm: Any,
    judge_llm: Any,
    knowledge_store: Any,
    insight_cases: list[dict[str, Any]],
    real_mode: bool,
    model_name: str,
) -> None:
    rubric = EvalRubric.default()
    judge = LLMJudge(judge_llm, rubric, mode="strict")
    agent = InsightAgent(insight_agent_llm, knowledge_store, model=model_name)

    faithfulness_scores: list[float] = []
    overalls: list[float] = []
    total_tokens = 0
    latencies: list[float] = []
    rows: list[str] = []

    for case in insight_cases:
        state: dict[str, Any] = {
            "diary_content": case["diary"],
            "intent": case.get("intent", "retrospective_review"),
        }
        if "episodic_context" in case:
            state["episodic_context"] = case["episodic_context"]
        if "long_term_profile" in case:
            state["long_term_profile"] = case["long_term_profile"]

        result = await agent.run(state)
        reply = result["insight_response"]

        graded = judge.score(case["diary"], reply)
        faithfulness_scores.append(graded.scores.get("context_faithfulness", 0.0))
        overalls.append(graded.overall)
        total_tokens += graded.tokens_in + graded.tokens_out
        latencies.append(graded.latency_ms)
        rows.append(
            f"| {case['id']} | {graded.scores.get('context_faithfulness', 0):.1f} | "
            f"{graded.overall:.2f} |"
        )

    mean_faithfulness = _mean(faithfulness_scores)
    mean_overall = _mean(overalls)
    avg_latency = _mean(latencies)
    print(
        f"\n[EVAL SUMMARY] suite=insight mode={'real' if real_mode else 'stub'} "
        f"cases={len(insight_cases)} mean_faithfulness={mean_faithfulness:.2f} "
        f"mean_overall={mean_overall:.2f} total_tokens={total_tokens} "
        f"avg_latency_ms={avg_latency:.2f}"
    )

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        body = (
            f"## Insight ({model_name}, {len(insight_cases)} cases)\n\n"
            f"- mean context_faithfulness: **{mean_faithfulness:.2f}** / 5\n"
            f"- mean overall: **{mean_overall:.2f}** / 5\n\n"
            "| case | faithfulness | overall |\n|---|---|---|\n" + "\n".join(rows)
        )
        _update_baseline_section("insight", body)

    if real_mode:
        assert mean_faithfulness >= INSIGHT_FAITHFULNESS_THRESHOLD, (
            f"mean faithfulness {mean_faithfulness:.2f} < {INSIGHT_FAITHFULNESS_THRESHOLD}"
        )
    else:
        assert all(1.0 <= s <= 5.0 for s in faithfulness_scores)

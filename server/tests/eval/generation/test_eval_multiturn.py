"""Multi-turn generation eval — memory coherence across diary turns.

Drives the **full B-9 pipeline** (Supervisor + Skill integration + asyncio graph
+ the three Worker agents) over the fixed 3-turn scenarios in
``tests/eval/rag/test_cases_multiturn.json``. Earlier turns are replayed into the
final turn's ``episodic_context`` (and a stub retriever surfaces them as
``retrieval_context``); the test then checks that the synthesized final reply
actually *references the earlier topics* — i.e. the pipeline carries memory
across turns instead of treating each turn in isolation.

Modes mirror the rest of the generation suite:

* **Real mode** (``LLM_API_KEY`` set) — asserts a coherence-rate gate and writes
  the ``multiturn`` section of ``BASELINE.md`` under ``EVAL_UPDATE_BASELINE=1``.
* **Stub mode** — the fixed stub reply can't echo topics, so we only assert the
  pipeline runs end to end and every turn yields a non-empty reply.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.domain.agents.empathy_agent import EmpathyAgent
from app.domain.agents.graph import create_multi_agent_graph
from app.domain.agents.insight_agent import InsightAgent
from app.domain.agents.intent_classifier import IntentClassifier
from app.domain.agents.retrieval_agent import RetrievalAgent
from app.domain.agents.supervisor import SupervisorAgent
from app.domain.rag.types import RetrievalResult
from app.domain.skills.registry import create_default_registry
from tests.eval.generation.test_generation_quality import _mean, _update_baseline_section
from tests.eval.judge import LLMJudge
from tests.eval.rubric import EvalRubric

pytestmark = pytest.mark.eval

MULTITURN_CASES = (
    Path(__file__).resolve().parents[1] / "rag" / "test_cases_multiturn.json"
)
COHERENCE_THRESHOLD = 0.66  # ≥ 2 of 3 scenarios must reference earlier topics


class _StubRetriever:
    """Return the scenario's earlier turns as retrieval hits (no Chroma/BM25)."""

    def __init__(self, results: list[RetrievalResult]) -> None:
        self._results = results

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        _ = query
        return self._results[:top_k]


@pytest.fixture(scope="session")
def multiturn_cases() -> list[dict[str, Any]]:
    return json.loads(MULTITURN_CASES.read_text(encoding="utf-8"))


def _episodic_from_turns(prior_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for turn in prior_turns:
        seed = turn.get("memory_seed", {})
        entries.append(
            {
                "event": seed.get("event", ""),
                "emotion": seed.get("emotion", ""),
                "content": turn.get("content", ""),
                "date": turn.get("date", ""),
            }
        )
    return entries


def _retrieval_from_turns(prior_turns: list[dict[str, Any]]) -> list[RetrievalResult]:
    return [
        RetrievalResult(
            doc_id=turn.get("diary_id", ""),
            diary_id=turn.get("diary_id", ""),
            content=turn.get("content", ""),
            score=0.9,
            date=turn.get("date", ""),
        )
        for turn in prior_turns
    ]


def _build_graph(agent_llm: Any, knowledge_store: Any, model_name: str, retriever: Any) -> Any:
    supervisor = SupervisorAgent(
        IntentClassifier(agent_llm, model=model_name),
        create_default_registry(),
        llm=agent_llm,
        model=model_name,
    )
    return create_multi_agent_graph(
        supervisor,
        EmpathyAgent(agent_llm, knowledge_store, model=model_name),
        RetrievalAgent(retriever, knowledge_store),
        InsightAgent(agent_llm, knowledge_store, model=model_name),
    )


async def test_multiturn_memory_coherence(
    agent_llm: Any,
    judge_llm: Any,
    knowledge_store: Any,
    multiturn_cases: list[dict[str, Any]],
    real_mode: bool,
    model_name: str,
) -> None:
    rubric = EvalRubric.default()
    judge = LLMJudge(judge_llm, rubric, mode="strict")

    coherent_flags: list[bool] = []
    faithfulness_scores: list[float] = []
    overalls: list[float] = []
    rows: list[str] = []

    for scenario in multiturn_cases:
        turns = scenario["turns"]
        prior_turns, final_turn = turns[:-1], turns[-1]
        topics = final_turn.get("expect", {}).get("must_reference_topics", [])

        graph = _build_graph(
            agent_llm,
            knowledge_store,
            model_name,
            _StubRetriever(_retrieval_from_turns(prior_turns)),
        )
        state: dict[str, Any] = {
            "diary_id": final_turn.get("diary_id", ""),
            "diary_content": final_turn["content"],
            "episodic_context": _episodic_from_turns(prior_turns),
        }
        result = await graph.invoke(state)
        reply = result.get("final_response", "")

        assert reply, f"{scenario['scenario_id']} produced an empty reply"

        coherent = any(topic in reply for topic in topics)
        coherent_flags.append(coherent)

        graded = judge.score(final_turn["content"], reply)
        faithfulness_scores.append(graded.scores.get("context_faithfulness", 0.0))
        overalls.append(graded.overall)
        rows.append(
            f"| {scenario['scenario_id']} | {'✅' if coherent else '❌'} | "
            f"{graded.scores.get('context_faithfulness', 0):.1f} | {graded.overall:.2f} |"
        )

    coherence_rate = sum(coherent_flags) / len(coherent_flags) if coherent_flags else 0.0
    mean_faithfulness = _mean(faithfulness_scores)
    mean_overall = _mean(overalls)
    print(
        f"\n[EVAL SUMMARY] suite=multiturn mode={'real' if real_mode else 'stub'} "
        f"scenarios={len(multiturn_cases)} coherence_rate={coherence_rate:.2f} "
        f"mean_faithfulness={mean_faithfulness:.2f} mean_overall={mean_overall:.2f}"
    )

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        body = (
            f"## Multi-turn ({model_name}, {len(multiturn_cases)} scenarios)\n\n"
            f"- coherence rate: **{coherence_rate:.2f}** "
            f"({sum(coherent_flags)}/{len(coherent_flags)})\n"
            f"- mean context_faithfulness: **{mean_faithfulness:.2f}** / 5\n"
            f"- mean overall: **{mean_overall:.2f}** / 5\n\n"
            "| scenario | references memory | faithfulness | overall |\n"
            "|---|---|---|---|\n" + "\n".join(rows)
        )
        _update_baseline_section("multiturn", body)

    if real_mode:
        assert coherence_rate >= COHERENCE_THRESHOLD, (
            f"coherence rate {coherence_rate:.2f} < {COHERENCE_THRESHOLD}"
        )

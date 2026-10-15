"""Personalization A/B eval — quantify the lift the memory system adds (P0-A).

Every case runs twice through the REAL worker agent:

* **Arm A (personalized)** — the full production-shaped state:
  ``long_term_profile`` + ``episodic_context``, exactly what MemoryGateway
  assembles for a returning user.
* **Arm B (cold)** — diary + intent only: a brand-new user the system has
  never seen.

Both replies are graded by the SAME judge with the SAME ground-truth context
(profile + memory rendered into the judge's ``history`` block), so the per-case
lift ``personalization(A) - personalization(B)`` isolates the memory system's
contribution from case difficulty.

The custom rubric reuses the default rubric's ``empathy`` dimension (guard:
personalization must not come at the cost of empathy) plus a new
``personalization`` dimension (weighted 1.5).

Gates:

* **Real mode** — mean lift > 0 (memory must add measurable value), win rate
  ≥ 0.5, and arm-A mean empathy ≥ 3.5.
* **Stub mode (CI)** — the stub agent only personalizes when the profile
  actually reached the prompt, so lift == 3.0 and win rate == 1.0
  deterministically; this proves the state → prompt → reply → judge wiring.

Run ``EVAL_UPDATE_BASELINE=1 make eval-personalization`` to (re)seed BASELINE.md.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from app.domain.agents.empathy_agent import EmpathyAgent
from app.domain.agents.insight_agent import InsightAgent
from tests.eval.judge import LLMJudge
from tests.eval.rubric import EvalRubric, RubricDimension

pytestmark = pytest.mark.eval

EMPATHY_FLOOR = 3.5
WIN_RATE_FLOOR = 0.5
BASELINE_PATH = Path(__file__).parent / "BASELINE.md"


def personalization_rubric() -> EvalRubric:
    """personalization (new) + empathy (reused from the default rubric)."""
    empathy_dim = next(d for d in EvalRubric.default().dimensions if d.key == "empathy")
    personalization_dim = RubricDimension(
        key="personalization",
        name="个性化贴合度",
        description=(
            "回复是否利用了历史上下文中的用户画像与记忆（稳定偏好、反复话题、"
            "性格特征、重要他人、近期事件、情绪基线）做出贴合这个具体用户的回应，"
            "而非任何用户都适用的通用回复。"
        ),
        anchors={
            1: "完全通用的模板回复，未体现任何对该用户的了解",
            2: "几乎通用，最多泛泛提及「你最近」",
            3: "部分贴合，自然用到一处画像或记忆信息",
            4: "明显贴合，具体引用画像或历史中的信息",
            5: "高度个性化：自然关联多处画像与历史信息，回应这个用户作为独特个体的持续状态",
        },
        positive_example="你上次也提到加班到十点，这周已经是第三次了，这种连轴转真的会耗竭人。",
        negative_example="注意休息，保持良好心态，一切都会好起来的。",
        weight=1.5,
    )
    return EvalRubric([personalization_dim, empathy_dim])


def _render_ground_truth(case: dict[str, Any]) -> str:
    """Render the profile + memory ground truth shown to the judge for BOTH arms."""
    profile = case.get("long_term_profile") or {}
    lines: list[str] = []

    style = profile.get("preferred_response_style")
    if style:
        lines.append(f"偏好回应风格：{style}")
    topics = profile.get("recurring_topics") or []
    if topics:
        lines.append(f"反复关注的话题：{'、'.join(str(t) for t in topics[:5])}")
    tags = profile.get("personality_tags") or []
    if tags:
        lines.append(f"性格特征：{'、'.join(str(t) for t in tags[:5])}")
    baseline = profile.get("emotion_baseline") or {}
    if baseline.get("dominant_emotion"):
        lines.append(f"近期主导情绪：{baseline['dominant_emotion']}")
    people = profile.get("important_people") or []
    if people:
        rendered = "、".join(
            f"{p.get('name', '')}（{p.get('relation', '')}）" for p in people[:3] if isinstance(p, dict)
        )
        if rendered:
            lines.append(f"重要他人：{rendered}")

    memories = case.get("episodic_context") or []
    if memories:
        mem_lines = [
            f"- {e.get('event_summary', '')}（情绪：{e.get('emotion', '')}）"
            for e in memories[:5]
            if isinstance(e, dict) and e.get("event_summary")
        ]
        if mem_lines:
            lines.append("近期记录到的记忆：\n" + "\n".join(mem_lines))

    return "\n".join(lines)


def _update_baseline_section(marker: str, body: str) -> None:
    """Replace (or append) a ``<!-- marker -->``-delimited section in BASELINE.md."""
    begin = f"<!-- BEGIN:{marker} -->"
    end = f"<!-- END:{marker} -->"
    block = f"{begin}\n{body}\n{end}"

    existing = (
        BASELINE_PATH.read_text(encoding="utf-8")
        if BASELINE_PATH.exists()
        else (
            "# Personalization A/B Baseline\n\n"
            "由 `EVAL_UPDATE_BASELINE=1 make eval-personalization` 生成。\n\n"
        )
    )
    if begin in existing and end in existing:
        head = existing.split(begin)[0]
        tail = existing.split(end)[1]
        updated = f"{head}{block}{tail}"
    else:
        updated = f"{existing}\n{block}\n"
    BASELINE_PATH.write_text(updated, encoding="utf-8")


async def test_personalization_lift(
    agent_llm: Any,
    judge_llm: Any,
    knowledge_store: Any,
    personalization_cases: list[dict[str, Any]],
    real_mode: bool,
    model_name: str,
) -> None:
    rubric = personalization_rubric()
    judge = LLMJudge(judge_llm, rubric, mode="strict")
    agents: dict[str, Any] = {
        "empathy": EmpathyAgent(agent_llm, knowledge_store, model=model_name),
        "insight": InsightAgent(agent_llm, knowledge_store, model=model_name),
    }

    pers_a: list[float] = []
    pers_b: list[float] = []
    empathy_a: list[float] = []
    lifts: list[float] = []
    wins = 0
    total_tokens = 0
    rows: list[str] = []

    for case in personalization_cases:
        diary = case["diary"]
        intent = case.get("intent", "emotional_support")
        agent = agents[case["agent"]]

        # Arm A: full production-shaped state (profile + episodic memory).
        state_a: dict[str, Any] = {
            "diary_content": diary,
            "intent": intent,
            "long_term_profile": case.get("long_term_profile", {}),
            "episodic_context": case.get("episodic_context", []),
        }
        # Arm B: cold state — a brand-new user with no memory.
        state_b: dict[str, Any] = {"diary_content": diary, "intent": intent}

        result_a = await agent.run(state_a)
        result_b = await agent.run(state_b)
        reply_a = result_a.get("empathy_response") or result_a.get("insight_response") or ""
        reply_b = result_b.get("empathy_response") or result_b.get("insight_response") or ""

        ground_truth = _render_ground_truth(case)
        graded_a = judge.score(diary, reply_a, history=ground_truth)
        graded_b = judge.score(diary, reply_b, history=ground_truth)

        score_a = graded_a.scores["personalization"]
        score_b = graded_b.scores["personalization"]
        emp_a = graded_a.scores["empathy"]
        lift = score_a - score_b

        pers_a.append(score_a)
        pers_b.append(score_b)
        empathy_a.append(emp_a)
        lifts.append(lift)
        if score_a > score_b:
            wins += 1
        total_tokens += graded_a.tokens_in + graded_a.tokens_out
        total_tokens += graded_b.tokens_in + graded_b.tokens_out
        outcome = "win" if lift > 0 else ("tie" if lift == 0 else "loss")
        rows.append(
            f"| {case['id']} | {case['agent']} | {score_a:.1f} | {score_b:.1f} | "
            f"{lift:+.1f} | {emp_a:.1f} | {outcome} |"
        )

    n = len(personalization_cases)
    mean_a = sum(pers_a) / n
    mean_b = sum(pers_b) / n
    mean_lift = sum(lifts) / n
    mean_empathy_a = sum(empathy_a) / n
    win_rate = wins / n

    print(
        f"\n[EVAL SUMMARY] suite=personalization mode={'real' if real_mode else 'stub'} "
        f"cases={n} pers_A={mean_a:.2f} pers_B={mean_b:.2f} mean_lift={mean_lift:.2f} "
        f"win_rate={win_rate:.2f} empathy_A={mean_empathy_a:.2f} total_tokens={total_tokens}"
    )

    if os.getenv("EVAL_UPDATE_BASELINE") == "1":
        body = (
            f"## Personalization A/B ({model_name}, {n} cases)\n\n"
            f"- mean personalization arm A (with memory): **{mean_a:.2f}** / 5\n"
            f"- mean personalization arm B (cold): **{mean_b:.2f}** / 5\n"
            f"- mean lift (A − B): **{mean_lift:+.2f}**\n"
            f"- win rate (A > B): **{win_rate:.2f}** ({wins}/{n})\n"
            f"- arm A mean empathy: **{mean_empathy_a:.2f}** / 5\n\n"
            "| case | agent | pers_A | pers_B | lift | empathy_A | outcome |\n"
            "|---|---|---|---|---|---|---|\n" + "\n".join(rows)
        )
        _update_baseline_section("personalization", body)

    if real_mode:
        assert mean_lift > 0, (
            f"personalization lift {mean_lift:+.2f} <= 0 — memory adds no measurable value"
        )
        assert win_rate >= WIN_RATE_FLOOR, f"win rate {win_rate:.2f} < {WIN_RATE_FLOOR}"
        assert mean_empathy_a >= EMPATHY_FLOOR, (
            f"arm A mean empathy {mean_empathy_a:.2f} < {EMPATHY_FLOOR} — "
            "personalization must not break empathy quality"
        )
    else:
        # Deterministic wiring proof: the stub only personalizes when profile
        # markers reached the prompt, so every case must be a clean win.
        assert mean_lift == pytest.approx(3.0), (
            f"stub wiring broken: mean lift {mean_lift:+.2f} != 3.0 "
            "(profile/memory not reaching the agent prompt?)"
        )
        assert win_rate == 1.0, f"stub wiring broken: win rate {win_rate:.2f} != 1.0"
        assert all(1.0 <= s <= 5.0 for s in pers_a + pers_b + empathy_a)

"""Fixtures for the offline plan-proposal quality eval (V3 P5 / Task 4-5).

Runs the *real* :class:`~app.domain.agents.planner_agent.PlannerAgent` and grades
the emitted ``plan_proposal`` protocol block with the shared
:class:`~tests.eval.judge.LLMJudge` + the plan rubric
(:mod:`tests.eval.plan.rubric_plan`). Excluded from CI (``-m eval``); two modes:

* **Real mode** — when ``LLM_API_KEY`` is set, the planner LLM and the judge LLM
  are the shared OpenAI-compatible :class:`~tests.eval._http_llm.HttpLLM` adapter.
  This is the run that produces a meaningful quality baseline.
* **Stub mode** — when ``LLM_API_KEY`` is absent (CI, local dev), a deterministic
  ``StubPlannerLLM`` (returns a fixed valid-JSON plan) + ``StubPlanJudgeLLM``
  (returns fixed per-dimension scores) keep ``make eval-plan`` green and prove
  the framework wiring without any network call.

The planner publishes its proposal to the :class:`TraceEventBus`; a
``capture_plan_proposal`` helper subscribes, runs one case, drains the queue and
returns the ``plan_proposal`` block data (or ``None`` when the agent short-circuits
to a clarification / crisis-safe response).
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, ClassVar

import pytest

from tests.eval._http_llm import REAL_MODE, HttpLLM, Message, usage_block
from tests.eval._http_llm import is_auth_error as _is_auth_error

DATA_DIR = Path(__file__).parent


# --------------------------------------------------------------------------- #
# Stub LLMs (deterministic; CI / no-API-key mode)
# --------------------------------------------------------------------------- #
_GOAL_RE = re.compile(r"用户目标：(.+?)(?:\n|$)")


class StubPlannerLLM:
    """Deterministic planner LLM that returns a valid-JSON plan proposal.

    Echoes the user's goal (parsed from the planner prompt) so the stub output
    is at least goal-anchored; the rest is a fixed, gentle, multi-step plan.
    This exercises the PlannerAgent's JSON-parse path (not its fallback) and
    gives the stub judge something concrete-shaped to (fixedly) score.
    """

    _TASKS: ClassVar[list[dict[str, Any]]] = [
        {"title": "选一个最小的起步动作", "note": "从你确定能做到的最小一步开始", "due_date": None},
        {
            "title": "固定一个每天的触发时机",
            "note": "绑定到已有的日常动作（如洗漱后）",
            "due_date": None,
        },
        {"title": "记录一次完成情况", "note": "写一句话即可，做到没做到都没关系", "due_date": None},
    ]

    def _plan_json(self, prompt: str) -> str:
        match = _GOAL_RE.search(prompt)
        goal = match.group(1).strip() if match else "你的目标"
        plan = {
            "title": f"关于「{goal}」的小步计划",
            "motivation": "基于本次对话的建议，先从一个小尝试开始，慢慢来。",
            "tasks": list(self._TASKS),
        }
        return json.dumps(plan, ensure_ascii=False)

    def invoke(self, prompt: str) -> Message:  # pragma: no cover - sync mirror
        return Message(content=self._plan_json(prompt), response_metadata=usage_block(220, 90))

    async def ainvoke(self, prompt: str) -> Message:
        return Message(content=self._plan_json(prompt), response_metadata=usage_block(220, 90))


class StubPlanJudgeLLM:
    """Deterministic judge returning fixed mid-high plan-rubric scores.

    Mirrors ``StubJudgeLLM`` but emits the *plan* rubric dimensions
    (actionability / gentleness / context_faithfulness / safety) so the shared
    :class:`~tests.eval.judge.LLMJudge` parses them via its (rubric-driven)
    normal path. Safety is pinned at 5 since stub output is generic but benign.
    """

    _SCORES: ClassVar[dict[str, int]] = {
        "actionability": 4,
        "gentleness": 4,
        "context_faithfulness": 4,
        "safety": 5,
    }

    def invoke(self, prompt: str) -> Message:
        body = ", ".join(f'"{k}": {v}' for k, v in self._SCORES.items())
        return Message(
            content=f'{{{body}, "rationale": "stub plan judge"}}',
            response_metadata=usage_block(300, 48),
        )


# --------------------------------------------------------------------------- #
# Auth preflight + mode fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _llm_auth_preflight() -> None:
    """Skip the whole plan eval (with a clear message) on a dead LLM key.

    A single cheap call in real mode: if the LLM rejects the key (401/403),
    every downstream planner/judge call would otherwise raise mid-suite and
    abort the remaining cases. We turn that into a clean ``skip``. Stub mode
    never hits the network, so it is a no-op there.
    """
    if not REAL_MODE:
        return
    try:
        HttpLLM(max_tokens=1, max_retries=1).invoke("ping")
    except Exception as exc:
        if _is_auth_error(exc):
            pytest.skip(f"LLM auth failed (check LLM_API_KEY in server/.env): {exc}")


@pytest.fixture(scope="session")
def real_mode() -> bool:
    return REAL_MODE


@pytest.fixture(scope="session")
def model_name() -> str:
    from tests.eval._http_llm import MODEL

    return MODEL if REAL_MODE else "stub"


# --------------------------------------------------------------------------- #
# Injectable LLMs (real HttpLLM vs deterministic stub)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def planner_llm() -> Any:
    # Planner is generative: a higher temperature yields more varied proposals.
    # Module-scoped so the (expensive, real-mode) eval runs once per suite and
    # both the quality test and the regression test share one LLM pass.
    return HttpLLM(temperature=0.7, max_tokens=900) if REAL_MODE else StubPlannerLLM()


@pytest.fixture(scope="module")
def judge_llm() -> Any:
    if REAL_MODE:
        # Plan proposals carry more structure (title + motivation + up to 5
        # tasks) than a single empathy reply, so the judge reasons longer
        # before emitting JSON — give it ample room to avoid truncation.
        return HttpLLM(temperature=0.0, max_tokens=3000, json_mode=True)
    return StubPlanJudgeLLM()


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def plan_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# PlannerAgent + plan capture
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def planner_agent(planner_llm: Any) -> Any:
    """A real PlannerAgent wired with the (real or stub) planner LLM.

    Uses the production :class:`~app.shared.crisis_guard.CrisisGuard` (default)
    so the eval exercises the real crisis short-circuit — dataset cases are
    intentionally non-crisis, so a short-circuit would itself be a finding.
    """
    from app.domain.agents.planner_agent import PlannerAgent

    return PlannerAgent(llm=planner_llm)


async def capture_plan_proposal(
    planner_agent: Any,
    case: dict[str, Any],
    trace_id: str,
) -> dict[str, Any] | None:
    """Run one case through the planner and return its ``plan_proposal`` data.

    Subscribes to the :class:`TraceEventBus` for ``trace_id``, builds a
    :class:`~app.domain.agents.planner_agent.PlannerInput` from the case (goal →
    ``user_input``, diary → ``prior_context``, episodic history → ``source_refs``),
    runs the agent, drains the queue and returns the first ``plan_proposal``
    block's ``data`` dict. Returns ``None`` when the agent emitted no proposal
    (clarification request or crisis short-circuit).
    """
    from app.domain.agents.planner_agent import PlannerInput
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    source_refs = [
        {"text": ctx, "category": "episodic"} for ctx in case.get("episodic_context", [])
    ]
    inp = PlannerInput(
        user_input=case["plan_request"],
        prior_context=case.get("diary_content", ""),
        trace_id=trace_id,
        user_id="eval",
        conversation_id=f"eval-{case['case_id']}",
        source_refs=source_refs,
    )

    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)
    try:
        await planner_agent.run(inp)
        # Let the bus fan-out complete before draining.
        await asyncio.sleep(0)
        events: list[dict[str, Any]] = []
        while not queue.empty():
            events.append(queue.get_nowait())
    finally:
        await bus.unsubscribe(trace_id, queue)

    for event in events:
        if event.get("type") == StreamingEventType.PROTOCOL_BLOCK:
            block = event.get("block", {})
            if block.get("block_type") == "plan_proposal":
                return block.get("data")  # type: ignore[return-value]
    return None


__all__ = [
    "StubPlanJudgeLLM",
    "StubPlannerLLM",
    "capture_plan_proposal",
    "judge_llm",
    "model_name",
    "plan_cases",
    "planner_agent",
    "planner_llm",
    "real_mode",
]

"""Plan information completeness assessment.

Determines whether the user has provided enough information (what + how)
for the PlannerAgent to generate a plan proposal, or whether a
clarification round is needed.

This is intentionally a lightweight rule-based check (zero LLM cost) —
the PlannerAgent LLM call is only invoked once the user has provided at
least a goal (what). The LLM then decides whether to propose a plan or
ask a follow-up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompletenessResult:
    """Result of assessing plan information completeness."""

    is_complete: bool
    what: str | None = None
    how: str | None = None
    when: str | None = None
    missing_fields: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


# 启发式信号词
_GOAL_SIGNALS = re.compile(
    r"(想|要|希望|打算|计划|开始|养成|坚持|戒掉|改掉|完成|实现|达到)"
)
_METHOD_SIGNALS = re.compile(
    r"(怎么|如何|通过|用|靠|方式|方法|步骤|具体|每天|每周|定时|固定)"
)


def assess_plan_completeness(current_input: str, prior_context: str = "") -> CompletenessResult:
    """Assess whether current + prior input contain enough to propose a plan.

    A "complete" plan request needs at least:
    - ``what``: a goal (what the user wants to achieve) — REQUIRED
    - ``how``: a method (optionally, how they plan to do it) — OPTIONAL

    If ``how`` is missing, the PlannerAgent may either propose a default
    method (with source refs) or ask for clarification based on its
    prompt logic.
    """
    combined = f"{prior_context} {current_input}".strip()
    has_what = bool(_GOAL_SIGNALS.search(combined)) and len(combined) > 2
    has_how = bool(_METHOD_SIGNALS.search(combined))

    missing: list[str] = []
    if not has_what:
        missing.append("what")
    if not has_how:
        missing.append("how")

    return CompletenessResult(
        is_complete=has_what,  # what 足够即可生成 proposal（how 可由 Agent 建议）
        what=current_input.strip() if has_what else None,
        how=current_input.strip() if has_how else None,
        missing_fields=missing,
        context={"raw_input": current_input, "prior": prior_context},
    )

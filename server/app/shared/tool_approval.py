"""Write-tool approval gate — the proposal-confirm principle, enforced (C2).

Night Diary's agent is read-only by design: it *proposes* plans/tasks and the
user *confirms* before anything is written. That principle used to be a
convention; this module turns it into a mechanism. Any tool registered in
:data:`WRITE_TOOLS` is refused unless it is explicitly approved for
auto-execution via ``Settings.approved_write_tools`` — there is deliberately no
"YOLO" bypass.

The gate is enforced in two places that share this single evaluator so they can
never diverge:

* :func:`app.services.ai.conversation_loop._execute_tool` — the hard gate on
  every tool execution path.
* :class:`app.shared.middleware.approval.ToolApprovalMiddleware` — the same
  decision surfaced through the ``pre_tool_call`` hook (D3).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Tools that mutate persisted state. Empty today (the agent has no write
#: access); register future write tools here so the gate covers them by default.
WRITE_TOOLS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Outcome of a ``pre_tool_call`` approval check."""

    allowed: bool
    reason: str = ""
    #: Optional replacement args (unused by the gate; reserved for hook middleware).
    args: dict[str, object] | None = None


def is_write_tool(name: str) -> bool:
    """Return True when ``name`` is a registered state-mutating tool."""
    return name in WRITE_TOOLS


def evaluate_tool_call(
    name: str,
    *,
    approved: frozenset[str] = frozenset(),
) -> ApprovalDecision:
    """Decide whether ``name`` may execute.

    Read tools always pass. Write tools pass only when present in ``approved``
    (the config-driven auto-approve list); otherwise they are blocked and must
    go through the proposal-confirm flow instead.
    """
    if not is_write_tool(name):
        return ApprovalDecision(True)
    if name in approved:
        return ApprovalDecision(True, reason="auto-approved (low risk)")
    return ApprovalDecision(False, reason=f"写工具 {name} 未获批准：须走提案-确认流程")


__all__ = [
    "WRITE_TOOLS",
    "ApprovalDecision",
    "evaluate_tool_call",
    "is_write_tool",
]
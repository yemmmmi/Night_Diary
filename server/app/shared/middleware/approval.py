"""ToolApprovalMiddleware — C2 approval gate surfaced as a lifecycle hook.

Delegates to :func:`app.shared.tool_approval.evaluate_tool_call`, the same
evaluator the loop's hard gate uses, so the ``pre_tool_call`` hook and the
enforcement point can never disagree. It contributes no opinion for read tools
and returns a blocking decision for unapproved write tools.
"""

from __future__ import annotations

from typing import Any

from app.shared.middleware.base import MiddlewareBase, MiddlewareContext
from app.shared.tool_approval import ApprovalDecision, evaluate_tool_call


class ToolApprovalMiddleware(MiddlewareBase):
    """Block unapproved write tools at the ``pre_tool_call`` hook."""

    name = "tool_approval"

    def __init__(self, approved_write_tools: frozenset[str] = frozenset()) -> None:
        self._approved = approved_write_tools

    def pre_tool_call(
        self, tool_name: str, tool_args: dict[str, Any], ctx: MiddlewareContext
    ) -> ApprovalDecision | None:
        return evaluate_tool_call(tool_name, approved=self._approved)


__all__ = ["ToolApprovalMiddleware"]
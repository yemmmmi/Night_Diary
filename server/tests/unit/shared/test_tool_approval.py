"""Unit tests for the C2 write-tool approval gate and its D3 hook surface.

Covers:
- ``evaluate_tool_call``: read tools always pass; write tools blocked by default,
  allowed only when explicitly approved (config-driven whitelist).
- ``ToolApprovalMiddleware``: same decision surfaced through ``pre_tool_call``.
- ``_execute_tool`` integration: the hard gate blocks unapproved write tools and
  the ``pre_tool_call`` / ``post_tool_call`` hooks wrap execution.
"""

from __future__ import annotations

from typing import Any

from app.services.ai.conversation_loop import _execute_tool
from app.shared.middleware import MiddlewareBase, MiddlewareContext, MiddlewarePipeline
from app.shared.middleware.approval import ToolApprovalMiddleware
from app.shared.tool_approval import (
    WRITE_TOOLS,
    ApprovalDecision,
    evaluate_tool_call,
    is_write_tool,
)

_WRITE = "write_note"


def _ctx() -> MiddlewareContext:
    return MiddlewareContext(scenario="conversation", user_id="u1")


# ── evaluate_tool_call ────────────────────────────────────────────────


def test_read_tool_always_allowed():
    """读工具（未登记为写工具）永远放行。"""
    decision = evaluate_tool_call("search_diary")
    assert decision.allowed is True
    assert decision.reason == ""


def test_write_tool_blocked_by_default(monkeypatch):
    """写工具默认被拒（无 YOLO 绕过）。"""
    monkeypatch.setattr("app.shared.tool_approval.WRITE_TOOLS", frozenset({_WRITE}))
    assert is_write_tool(_WRITE) is True
    decision = evaluate_tool_call(_WRITE)
    assert decision.allowed is False
    assert _WRITE in decision.reason


def test_write_tool_allowed_when_approved(monkeypatch):
    """写工具在配置白名单内时自动放行。"""
    monkeypatch.setattr("app.shared.tool_approval.WRITE_TOOLS", frozenset({_WRITE}))
    decision = evaluate_tool_call(_WRITE, approved=frozenset({_WRITE}))
    assert decision.allowed is True


def test_write_tools_default_is_empty():
    """出厂 WRITE_TOOLS 为空 —— 现网 Agent 仍零写权限。"""
    assert not WRITE_TOOLS


# ── ToolApprovalMiddleware ────────────────────────────────────────────


def test_approval_middleware_allows_read_tool():
    mw = ToolApprovalMiddleware()
    decision = mw.pre_tool_call("search_diary", {}, _ctx())
    assert decision is not None and decision.allowed is True


def test_approval_middleware_blocks_write_tool(monkeypatch):
    monkeypatch.setattr("app.shared.tool_approval.WRITE_TOOLS", frozenset({_WRITE}))
    mw = ToolApprovalMiddleware()
    decision = mw.pre_tool_call(_WRITE, {}, _ctx())
    assert decision is not None and decision.allowed is False


def test_approval_middleware_honours_approved_set(monkeypatch):
    monkeypatch.setattr("app.shared.tool_approval.WRITE_TOOLS", frozenset({_WRITE}))
    mw = ToolApprovalMiddleware(frozenset({_WRITE}))
    decision = mw.pre_tool_call(_WRITE, {}, _ctx())
    assert decision is not None and decision.allowed is True


# ── _execute_tool integration ─────────────────────────────────────────


def test_execute_tool_runs_and_fences_output():
    """普通读工具执行，结果被 C1 信任边界包裹。"""
    tools = {"echo": lambda text: f"echo:{text}"}
    out = _execute_tool("echo", {"text": "hi"}, tools)
    assert out.startswith("[echo]: ")
    assert "<tool_output" in out and "echo:hi" in out


def test_execute_tool_unknown_tool():
    assert "未知工具" in _execute_tool("nope", {}, {})


def test_execute_tool_blocks_unapproved_write_tool(monkeypatch):
    """硬门：未批准的写工具即便已注册也不执行。"""
    monkeypatch.setattr("app.shared.tool_approval.WRITE_TOOLS", frozenset({_WRITE}))
    called: list[Any] = []
    tools = {_WRITE: lambda **kw: called.append(kw) or "written"}
    out = _execute_tool(_WRITE, {}, tools)
    assert "blocked" in out
    assert called == []


def test_execute_tool_allows_approved_write_tool(monkeypatch):
    monkeypatch.setattr("app.shared.tool_approval.WRITE_TOOLS", frozenset({_WRITE}))
    tools = {_WRITE: lambda **kw: "written"}
    out = _execute_tool(_WRITE, {}, tools, approved_write_tools=frozenset({_WRITE}))
    assert "written" in out


class _ResultRewriter(MiddlewareBase):
    name = "rewriter"

    def post_tool_call(self, tool_name: str, result: str, ctx: MiddlewareContext) -> str:
        return result + "|hooked"


def test_execute_tool_applies_post_tool_call_hook():
    """post_tool_call 钩子在结果回灌前生效。"""
    pipeline = MiddlewarePipeline([_ResultRewriter()])
    tools = {"echo": lambda: "raw"}
    out = _execute_tool("echo", {}, tools, middleware_pipeline=pipeline, ctx=_ctx())
    assert "hooked" in out


class _Denier(MiddlewareBase):
    name = "denier"

    def pre_tool_call(
        self, tool_name: str, tool_args: dict[str, Any], ctx: MiddlewareContext
    ) -> ApprovalDecision:
        return ApprovalDecision(False, reason="denied by hook")


def test_execute_tool_hook_deny_blocks_execution():
    """pre_tool_call 钩子拒绝 → 工具不执行。"""
    called: list[Any] = []
    tools = {"echo": lambda: called.append(1) or "raw"}
    pipeline = MiddlewarePipeline([_Denier()])
    out = _execute_tool("echo", {}, tools, middleware_pipeline=pipeline, ctx=_ctx())
    assert "denied by hook" in out
    assert called == []


def test_execute_tool_swallows_tool_exception():
    def boom() -> str:
        raise RuntimeError("kaboom")

    out = _execute_tool("boom", {}, {"boom": boom})
    assert "error" in out and "kaboom" in out
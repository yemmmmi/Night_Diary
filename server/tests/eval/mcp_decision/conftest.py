"""Fixtures for the MCP tool-decision eval.

CI uses deterministic oracle responses solely to exercise native/text-tag
parsing and metric wiring. Set ``MCP_DECISION_REAL=1`` with ``LLM_API_KEY`` to
run the optional real-model path; stub scores are not product-quality scores.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.shared.tool_protocol import ToolSpec
from tests.eval._http_llm import API_KEY, MODEL, HttpLLM, is_auth_error
from tests.eval._stub_llm import ProgrammableStubLLM

DATA_DIR = Path(__file__).parent
REAL_MODE = os.getenv("MCP_DECISION_REAL") == "1" and bool(API_KEY)

_TOOL_SPECS = {
    "mcp__calendar__list_events": ToolSpec(
        name="mcp__calendar__list_events",
        description="查询用户日历中指定日期的事件。",
        parameters={
            "type": "object",
            "properties": {"date": {"type": "string"}},
            "required": ["date"],
        },
    ),
    "mcp__maps__search_places": ToolSpec(
        name="mcp__maps__search_places",
        description="按地点和条件搜索现实中的场所。",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    ),
    "mcp__web__search": ToolSpec(
        name="mcp__web__search",
        description="搜索需要最新公开信息的网页内容。",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    ),
    "mcp__project__list_tasks": ToolSpec(
        name="mcp__project__list_tasks",
        description="查询项目系统中的任务。",
        parameters={
            "type": "object",
            "properties": {"status": {"type": "string"}},
        },
    ),
}


def tool_specs_for(case: dict[str, Any]) -> list[ToolSpec]:
    return [_TOOL_SPECS[name] for name in case["enabled_tools"]]


def oracle_text(case: dict[str, Any]) -> str:
    """Encode annotations as tool tags for deterministic parser validation."""
    expected = case["expected"]
    if not expected["should_call_tool"]:
        return "不需要调用外部工具。"
    blocks: list[str] = []
    for call in expected["expected_tool_calls"]:
        args = dict(call.get("args_match", {}))
        for key in call.get("args_required", []):
            args.setdefault(key, "oracle-placeholder")
        blocks.append(
            f"<tool>{call['name']}</tool>"
            f"<args>{json.dumps(args, ensure_ascii=False)}</args>"
        )
    return " ".join(blocks)


@pytest.fixture(scope="session")
def mcp_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def real_mode() -> bool:
    return REAL_MODE


@pytest.fixture(scope="session")
def model_name() -> str:
    return MODEL if REAL_MODE else "stub-oracle"


@pytest.fixture(scope="session")
def oracle_llm(mcp_cases: list[dict[str, Any]]) -> ProgrammableStubLLM:
    responses = [
        (f"[{case['case_id']}]", oracle_text(case))
        for case in mcp_cases
    ]
    return ProgrammableStubLLM(responses, default_response="不需要调用外部工具。")


@pytest.fixture(scope="session")
def decision_llm(
    real_mode: bool, oracle_llm: ProgrammableStubLLM
) -> Any:
    if real_mode:
        return HttpLLM(temperature=0.0, max_tokens=500)
    return oracle_llm


@pytest.fixture(scope="session", autouse=True)
def _real_mode_auth_preflight(real_mode: bool) -> None:
    if not real_mode:
        return
    try:
        HttpLLM(max_tokens=1, max_retries=1).invoke("ping")
    except Exception as exc:
        if is_auth_error(exc):
            pytest.skip(f"MCP decision eval auth failed: {exc}")
        raise

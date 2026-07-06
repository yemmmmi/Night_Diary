"""Fixtures for the tool-call accuracy eval (B-tool).

Two protocol paths are exercised against the same 40-case annotated dataset:

* **Native** — ``HttpLLM.bind_tools`` (real mode, needs ``LLM_API_KEY``) or
  ``ProgrammableStubLLM.bind_tools`` (stub mode, CI-safe). The bound LLM
  returns ``tool_calls`` parsed by ``extract_native_tool_calls``.
* **Fallback** — always a ``ProgrammableStubLLM`` returning preset
  ``<tool>name</tool><args>json</args>`` text; parsed by
  ``parse_text_tag_calls``. This verifies the text-tag parsing pipeline
  deterministically (no real LLM needed).

``RecordingTool`` wraps each tool fn so the eval can record which tools were
actually *executed* (a secondary signal beyond the LLM's decision).

Set ``EVAL_UPDATE_BASELINE=1`` to (re)write ``baseline.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.ai.tool_factory import build_tool_specs
from app.shared.tool_protocol import ToolSpec
from tests.eval._http_llm import MODEL, REAL_MODE, HttpLLM, is_auth_error
from tests.eval._stub_llm import ProgrammableStubLLM

DATA_DIR = Path(__file__).parent


# --------------------------------------------------------------------------- #
# RecordingTool
# --------------------------------------------------------------------------- #
class RecordingTool:
    """Wrap a tool fn and record every invocation (name + args).

    The eval never wires real tool dependencies (retriever / db / Neo4j); the
    wrapped fn defaults to a no-op so recording works in any environment.
    """

    def __init__(self, name: str, fn: Any = None) -> None:
        self.name = name
        self._fn = fn
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> str:
        self.calls.append(dict(kwargs))
        if self._fn is not None:
            try:
                return self._fn(**kwargs)
            except Exception:
                return f"[recorder:{self.name}] tool fn error"
        return f"[recorder:{self.name}] ok"

    def reset(self) -> None:
        self.calls.clear()

    @property
    def call_count(self) -> int:
        return len(self.calls)


# --------------------------------------------------------------------------- #
# Stub response builder (shared by native-stub + fallback)
# --------------------------------------------------------------------------- #
def build_stub_text(case: dict[str, Any]) -> str:
    """Build the preset ``<tool>`` text-tag response for a case.

    For no-tool cases returns a plain empathetic reply (no tags). For tool
    cases returns one ``<tool>name</tool><args>json</args>`` block per expected
    call. Required args missing from ``args_match`` are filled with an empty
    string placeholder so presence checks still pass.
    """
    exp = case["expected"]
    if not exp["should_call_tool"]:
        return "好的，我理解你的感受，我会一直陪着你。"
    parts: list[str] = []
    for tc in exp.get("expected_tool_calls", []):
        name = tc["name"]
        args = dict(tc.get("args_match", {}))
        for key in tc.get("args_required", []):
            if key not in args:
                args[key] = ""
        args_json = json.dumps(args, ensure_ascii=False)
        parts.append(f"<tool>{name}</tool><args>{args_json}</args>")
    return " ".join(parts)


def _stub_key(case_id: str) -> str:
    """Substring matched inside the stub prompt — bracketed for uniqueness."""
    return f"[{case_id}]"


# --------------------------------------------------------------------------- #
# Auth preflight (real mode only): skip the suite on a dead key
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _native_auth_preflight() -> None:
    if not REAL_MODE:
        return
    try:
        HttpLLM(max_tokens=1, max_retries=1).invoke("ping")
    except Exception as exc:
        if is_auth_error(exc):
            pytest.skip(f"LLM auth failed (check LLM_API_KEY in server/.env): {exc}")


# --------------------------------------------------------------------------- #
# Mode + dataset fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def real_mode() -> bool:
    return REAL_MODE


@pytest.fixture(scope="session")
def model_name() -> str:
    return MODEL if REAL_MODE else "stub"


@pytest.fixture(scope="session")
def eval_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def tool_specs() -> list[ToolSpec]:
    return build_tool_specs()


@pytest.fixture(scope="session")
def recording_tools() -> dict[str, RecordingTool]:
    """No-op recording wrappers for all 5 built-in tools."""
    return {spec.name: RecordingTool(spec.name) for spec in build_tool_specs()}


# --------------------------------------------------------------------------- #
# LLM fixtures: native (real-or-stub) + fallback (always stub)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def stub_responses(eval_cases: list[dict[str, Any]]) -> dict[str, str]:
    """Map ``case_id`` -> preset text-tag response text."""
    return {c["case_id"]: build_stub_text(c) for c in eval_cases}


@pytest.fixture(scope="session")
def fallback_llm(stub_responses: dict[str, str]) -> ProgrammableStubLLM:
    """Always-stub LLM for the fallback (text-tag) path.

    Matches by ``[case_id]`` substring so each case gets its preset response.
    """
    responses = [(_stub_key(cid), text) for cid, text in stub_responses.items()]
    return ProgrammableStubLLM(responses, default_response="好的，我理解你。")


@pytest.fixture(scope="session")
def native_llm(real_mode: bool, fallback_llm: ProgrammableStubLLM) -> Any:
    """Native-path LLM.

    Real mode: ``HttpLLM`` (the test binds tools per-case and sends the raw
    user message). Stub mode: reuse ``fallback_llm`` so ``bind_tools`` returns
    a :class:`BoundProgrammableStub` that converts text-tags to ``tool_calls``.
    """
    if real_mode:
        return HttpLLM(temperature=0.0, max_tokens=800)
    return fallback_llm


__all__ = [
    "RecordingTool",
    "build_stub_text",
    "fallback_llm",
    "native_llm",
    "recording_tools",
    "stub_responses",
    "tool_specs",
]

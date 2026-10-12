"""Fixtures for the skill-routing clarification eval (B4 acceptance gate).

The production router (:func:`app.domain.skills.intent.classify_user_intent`)
is exercised against an annotated dataset of 31 cases across 7 categories.
Each case carries the *outcome* the router should produce:

* ``clarify`` — weak signal + the router LLM leans toward a skill but is
  unsure (confidence < ``CLARIFY_THRESHOLD``): ask the user to disambiguate.
* ``record`` / ``insight`` / ``plan`` — route to that skill.
* ``chat`` — normal chat, no skill.

Two LLM strategies are exercised on top of the *identical* rule layer:

* **stub mode** — :class:`ProgrammableStubLLM` returns the case's annotated
  ``stub_intent`` / ``stub_confidence`` (oracle input). This proves the
  routing wiring + clarification decision are correct deterministically in CI
  (no API key needed). The stub only answers on the weak-signal path; strong
  rules / goal rules / no-signal cases never consult it.
* **real mode** — :class:`HttpLLM` makes a real router call; the LLM's own
  intent + confidence decide the outcome. This is the quality signal worth
  tracking for regression.

Set ``EVAL_UPDATE_BASELINE=1`` to (re)write ``baseline.json``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from app.domain.skills.intent import classify_user_intent
from tests.eval._http_llm import MODEL, REAL_MODE, HttpLLM, is_auth_error
from tests.eval._stub_llm import ProgrammableStubLLM
from tests.eval.skill_routing.metrics import CaseOutcome, outcome_from_case

DATA_DIR = Path(__file__).parent
DATASET_PATH = DATA_DIR / "test_cases.json"


def _stub_json(intent: str, confidence: float) -> str:
    """Render the router's JSON contract ``{"intent": ..., "confidence": ...}``."""
    return json.dumps({"intent": intent, "confidence": confidence}, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# RecordingLLM — wraps an inner LLM to capture token usage + invocation flag
# --------------------------------------------------------------------------- #
class RecordingLLM:
    """Transparent wrapper recording per-call token usage and call count."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.last_latency_ms: float = 0.0
        self.last_tokens: int = 0
        self.call_count: int = 0

    def reset(self) -> None:
        self.last_latency_ms = 0.0
        self.last_tokens = 0
        self.call_count = 0

    @staticmethod
    def _tokens_of(msg: Any) -> int:
        usage = getattr(msg, "response_metadata", {}) or {}
        return int((usage.get("token_usage") or {}).get("total_tokens", 0))

    def invoke(self, prompt: str) -> Any:
        started = time.perf_counter()
        msg = self._inner.invoke(prompt)
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        self.last_tokens = self._tokens_of(msg)
        self.call_count += 1
        return msg

    async def ainvoke(self, prompt: str) -> Any:
        started = time.perf_counter()
        msg = await self._inner.ainvoke(prompt)
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        self.last_tokens = self._tokens_of(msg)
        self.call_count += 1
        return msg


# --------------------------------------------------------------------------- #
# Auth preflight (real mode only): skip the suite on a dead key
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _routing_auth_preflight() -> None:
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
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# LLM fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def stub_llm(eval_cases: list[dict[str, Any]]) -> ProgrammableStubLLM:
    """Oracle stub returning each case's annotated intent + confidence.

    Matched by ``用户输入：<text>`` — the router prompt's own user-content anchor.
    Matching on the bare text is unsafe: the prompt template itself contains
    phrases like ``制定一个计划``, which would shadow several cases. Responses are
    ordered longest-first so a more specific case never loses to a shorter
    substring match. Empty-input cases never consult the LLM, so they are
    omitted (their anchor would collide with every prompt).
    """
    pairs = sorted(
        (
            (f"用户输入：{c['text']}", _stub_json(c["stub_intent"], c["stub_confidence"]))
            for c in eval_cases
            if c["text"].strip()
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    return ProgrammableStubLLM(pairs, default_response=_stub_json("chat", 0.9))


@pytest.fixture(scope="session")
def router_llm(real_mode: bool, stub_llm: ProgrammableStubLLM) -> RecordingLLM:
    """Router LLM: HttpLLM (real, JSON mode) or oracle stub (CI placeholder)."""
    inner: Any = HttpLLM(temperature=0.0, max_tokens=200, json_mode=True) if real_mode else stub_llm
    return RecordingLLM(inner)


# --------------------------------------------------------------------------- #
# Per-case runner
# --------------------------------------------------------------------------- #
def run_case(case: dict[str, Any], router_llm: RecordingLLM) -> CaseOutcome:
    """Route one case and align the predicted outcome against its expectation.

    The predicted outcome collapses the router decision to the 5-way space:
    ``clarify`` when :attr:`IntentDecision.should_clarify`, otherwise the
    routed intent (``record`` / ``insight`` / ``plan`` / ``chat``).
    """
    recording = router_llm
    recording.reset()
    started = time.perf_counter()
    decision = classify_user_intent(case["text"], llm=recording, skill_catalog="")
    latency_ms = (time.perf_counter() - started) * 1000

    llm_invoked = recording.call_count > 0
    tokens = recording.last_tokens if llm_invoked else 0
    predicted_outcome = "clarify" if decision.should_clarify else decision.intent

    return outcome_from_case(
        case,
        predicted_outcome,
        actual_source=decision.source,
        confidence=decision.confidence,
        latency_ms=latency_ms,
        tokens=tokens,
        llm_invoked=llm_invoked,
    )


__all__ = [
    "RecordingLLM",
    "run_case",
]

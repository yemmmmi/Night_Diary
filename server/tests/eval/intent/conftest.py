"""Fixtures for the chat-intent classification eval (事项3 PR-B).

Two LLM-layer strategies are exercised against the same annotated
dataset, both on top of the *identical* rule layer
(:class:`~app.domain.agents.chat_intent_classifier.ChatIntentClassifier`):

* **Baseline A** — rule layer + general-purpose LLM (current production config).
  Real mode: :class:`HttpLLM` (needs ``LLM_API_KEY``). Stub mode:
  :class:`_RuleEchoStubLLM`, a placeholder that re-runs the rule layer and
  rubber-stamps its verdict — i.e. the LLM adds no corrective signal. This
  keeps the framework green in CI and represents the *lower bound* a real
  general LLM is expected to beat; real numbers come from REAL_MODE.
* **Treatment B** — rule layer + fine-tuned small model. Until the fine-tune
  ships, :class:`StubFineTunedLLM` stands in as an **oracle placeholder**: it
  returns the gold intent for every prompt. This proves the wiring is correct
  (Treatment B's ``llm_layer_accuracy`` must be 1.0 in stub mode) and shows the
  achievable upper bound; swap in the real fine-tuned model by replacing the
  ``treatment_b_llm`` fixture.

Per-case measurement:

- ``rule_short_circuited`` is computed from the rule layer directly (independent
  of which LLM is attached), so A and B share the same short-circuit partition.
- :class:`RecordingLLM` wraps the inner LLM to capture per-call token usage and
  whether the LLM layer was actually consulted (``llm_invoked``).
- End-to-end ``classify_sync`` wall time is recorded as ``latency_ms`` (rule
  layer is near-zero, so this effectively measures the LLM call when invoked).

Set ``EVAL_UPDATE_BASELINE=1`` to (re)write ``baseline.json``.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

from app.domain.agents.chat_intent_classifier import ChatIntentClassifier
from app.domain.agents.types import ChatIntent
from tests.eval._http_llm import MODEL, REAL_MODE, HttpLLM, Message, is_auth_error, usage_block
from tests.eval.intent.metrics import CaseOutcome

DATA_DIR = Path(__file__).parent
DATASET_PATH = DATA_DIR / "dataset" / "test_cases.json"

#: User-message extraction from the classifier's prompt template. The template
#: renders ``用户消息：{content}`` followed by a blank line and ``意图类别``.
_PROMPT_CONTENT_RE = re.compile(r"用户消息：(.*?)\n\n意图类别", re.DOTALL)


def _extract_content(prompt: str) -> str:
    """Pull the original user message back out of a rendered intent prompt."""
    m = _PROMPT_CONTENT_RE.search(prompt)
    return m.group(1).strip() if m else prompt


def _intent_json(category: str, confidence: float = 0.85) -> str:
    """Render the minimal JSON the classifier's ``_parse_llm_output`` expects."""
    return json.dumps(
        {
            "intent_category": category,
            "confidence": confidence,
            "need_retrieval": False,
            "need_tools": [],
            "need_entity_query": False,
        },
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------- #
# Stub LLMs (placeholders; real fine-tuned model replaces Treatment B later)
# --------------------------------------------------------------------------- #
class _RuleEchoStubLLM:
    """Baseline A stub placeholder: re-run the rule layer and echo its verdict.

    Simulates a general-purpose LLM that adds *no* corrective signal on
    ambiguous inputs — it agrees with whatever the rule layer decided. This
    keeps the framework deterministic in CI (no API key, no GPU) and pins the
    lower bound: Baseline A's stub accuracy equals the rule layer's accuracy.

    Real mode replaces this with :class:`HttpLLM` for the true general-LLM
    number.
    """

    def __init__(self) -> None:
        self._rule = ChatIntentClassifier(llm=None)

    def _classify(self, prompt: str) -> Message:
        content = _extract_content(prompt)
        rule_result = self._rule._rule_classify(content)
        return Message(
            content=_intent_json(rule_result.intent_category, 0.8),
            response_metadata=usage_block(140, 35),
        )

    def invoke(self, prompt: str) -> Message:
        return self._classify(prompt)

    async def ainvoke(self, prompt: str) -> Message:
        return self._classify(prompt)


class StubFineTunedLLM:
    """Treatment B placeholder: oracle that returns the gold intent.

    Looks up the gold intent by the user message extracted from the prompt and
    returns it as valid intent JSON. This is a **placeholder** standing in for
    the fine-tuned small model until training completes; it proves the eval
    wiring (Treatment B ``llm_layer_accuracy`` == 1.0 in stub mode) and shows the
    achievable ceiling. Replace via the ``treatment_b_llm`` fixture once the
    real model is available.
    """

    def __init__(self, content_to_gold: dict[str, str]) -> None:
        self._map = content_to_gold

    def _classify(self, prompt: str) -> Message:
        content = _extract_content(prompt)
        gold = self._map.get(content, ChatIntent.CASUAL_CHAT.value)
        return Message(
            content=_intent_json(gold, 0.9),
            response_metadata=usage_block(90, 22),
        )

    def invoke(self, prompt: str) -> Message:
        return self._classify(prompt)

    async def ainvoke(self, prompt: str) -> Message:
        return self._classify(prompt)


# --------------------------------------------------------------------------- #
# RecordingLLM — wraps an inner LLM to capture token usage + invocation flag
# --------------------------------------------------------------------------- #
class RecordingLLM:
    """Transparent wrapper that records per-call token usage and call count.

    The classifier calls ``llm.invoke(prompt)`` exactly once per non-short-circuit
    case; ``reset()`` before each case so ``call_count`` reflects whether the LLM
    layer was consulted for *this* case.
    """

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

    def invoke(self, prompt: str) -> Message:
        started = time.perf_counter()
        msg = self._inner.invoke(prompt)
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        self.last_tokens = self._tokens_of(msg)
        self.call_count += 1
        return msg

    async def ainvoke(self, prompt: str) -> Message:
        started = time.perf_counter()
        msg = await self._inner.ainvoke(prompt)
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        self.last_tokens = self._tokens_of(msg)
        self.call_count += 1
        return msg

    def bind_tools(self, tool_specs: list[Any]) -> Any:
        """Delegate ``bind_tools`` so the wrapper is a drop-in for HttpLLM."""
        inner = self._inner
        if hasattr(inner, "bind_tools"):
            return inner.bind_tools(tool_specs)
        raise AttributeError("inner LLM does not support bind_tools")


# --------------------------------------------------------------------------- #
# Auth preflight (real mode only): skip the suite on a dead key
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _intent_auth_preflight() -> None:
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


@pytest.fixture(scope="session")
def content_to_gold(eval_cases: list[dict[str, Any]]) -> dict[str, str]:
    """Map each case's raw ``text`` -> ``gold_intent`` (oracle lookup for stub B)."""
    return {c["text"]: c["gold_intent"] for c in eval_cases}


@pytest.fixture(scope="session")
def rule_classifier() -> ChatIntentClassifier:
    """Rule-only classifier (no LLM) — the canonical rule-layer oracle for A and B."""
    return ChatIntentClassifier(llm=None)


# --------------------------------------------------------------------------- #
# LLM + classifier fixtures: Baseline A and Treatment B
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def baseline_a_llm(real_mode: bool) -> RecordingLLM:
    """Baseline A LLM: HttpLLM (real) or rule-echo stub (CI placeholder)."""
    inner: Any = (
        HttpLLM(temperature=0.0, max_tokens=300, json_mode=True)
        if real_mode
        else _RuleEchoStubLLM()
    )
    return RecordingLLM(inner)


@pytest.fixture(scope="session")
def treatment_b_llm(content_to_gold: dict[str, str]) -> RecordingLLM:
    """Treatment B LLM: fine-tuned stub placeholder (oracle) until training lands.

    Swap the inner for the real fine-tuned client here once available.
    """
    return RecordingLLM(StubFineTunedLLM(content_to_gold))


@pytest.fixture(scope="session")
def baseline_a_classifier(baseline_a_llm: RecordingLLM, model_name: str) -> ChatIntentClassifier:
    return ChatIntentClassifier(llm=baseline_a_llm, model=model_name)


@pytest.fixture(scope="session")
def treatment_b_classifier(treatment_b_llm: RecordingLLM) -> ChatIntentClassifier:
    return ChatIntentClassifier(llm=treatment_b_llm, model="stub-finetuned-placeholder")


# --------------------------------------------------------------------------- #
# Per-case runner — shared by the report fixture and any ad-hoc test
# --------------------------------------------------------------------------- #
def run_case(
    case: dict[str, Any],
    classifier: ChatIntentClassifier,
    recording_llm: RecordingLLM,
    rule_classifier: ChatIntentClassifier,
) -> CaseOutcome:
    """Classify one case and align the prediction against its gold intent.

    ``rule_short_circuited`` is derived from the rule layer directly (so A and B
    share the same partition); ``llm_invoked`` is the empirical signal from the
    recording wrapper (True iff the LLM layer was actually consulted).
    """
    text = case["text"]
    rule_result = rule_classifier._rule_classify(text)
    rule_short_circuited = rule_result.confidence > ChatIntentClassifier.CONFIDENCE_THRESHOLD

    recording_llm.reset()
    started = time.perf_counter()
    result = classifier.classify_sync(text)
    latency_ms = (time.perf_counter() - started) * 1000

    llm_invoked = recording_llm.call_count > 0
    tokens = recording_llm.last_tokens if llm_invoked else 0

    return CaseOutcome(
        case_id=case["case_id"],
        category=case["category"],
        gold_intent=case["gold_intent"],
        predicted_intent=result.intent_category,
        rule_short_circuited=rule_short_circuited,
        llm_invoked=llm_invoked,
        latency_ms=latency_ms,
        tokens=tokens,
        rule_confidence=rule_result.confidence,
        notes=case.get("notes", ""),
    )


__all__ = [
    "RecordingLLM",
    "StubFineTunedLLM",
    "run_case",
]

"""Fixtures for the offline generation-quality eval.

This eval runs the *real* Worker Agents and grades their replies with the B-7
:class:`~tests.eval.judge.LLMJudge`. It is excluded from CI (``-m eval``) and
graded by an LLM, so it operates in two modes:

* **Real mode** — when ``LLM_API_KEY`` is set, both the agent LLM and the judge
  LLM are a thin ``httpx`` adapter over any OpenAI-compatible endpoint
  (DeepSeek by default). ``httpx`` is already a dev dependency, so no
  ``langchain-openai`` / ``openai`` runtime dep is pulled in. yemi runs the real
  baseline this way.
* **Stub mode** — when ``LLM_API_KEY`` is absent (CI, local dev), a deterministic
  stub agent LLM + stub judge keep ``make eval`` green and prove the framework
  wiring without any network call.

Set ``EVAL_UPDATE_BASELINE=1`` to (re)write ``BASELINE.md`` from a real run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._http_llm import (
    MODEL,
    REAL_MODE,
    HttpLLM,
    Message,
    is_auth_error,
    usage_block,
)

DATA_DIR = Path(__file__).parent


class _StubAgentLLM:
    """Deterministic empathetic-ish reply so stub-mode eval can be scored."""

    _REPLY = (
        "听起来你今天经历了不少起伏，这些情绪都是真实而值得被理解的。"
        "谢谢你愿意把它们写下来，我会一直在这里陪着你，慢慢来，不着急。"
    )

    def invoke(self, prompt: str) -> Message:
        return Message(content=self._REPLY, response_metadata=usage_block(150, 60))

    async def ainvoke(self, prompt: str) -> Message:
        return Message(content=self._REPLY, response_metadata=usage_block(150, 60))


class _StubJudgeLLM:
    """Deterministic judge returning a fixed mid-high score for every dimension."""

    def invoke(self, prompt: str) -> Message:
        keys = ["empathy", "context_faithfulness", "relevance", "safety", "no_pressure"]
        body = ", ".join(f'"{k}": 4' for k in keys)
        return Message(
            content=f'{{{body}, "rationale": "stub judge"}}',
            response_metadata=usage_block(300, 48),
        )


class StubKnowledgeStore:
    """No-op domain knowledge store for the eval (no Chroma needed)."""

    def query(
        self, query_text: str, max_results: int = 2, category_filter: str | None = None
    ) -> list[Any]:
        return []


@pytest.fixture(scope="session", autouse=True)
def _llm_auth_preflight() -> None:
    """Skip the whole generation eval (with a clear message) on a dead key.

    A single cheap call in real mode: if the LLM rejects the key (401/403),
    every downstream judge call would otherwise raise mid-suite and abort the
    remaining cases. We turn that into a clean ``skip`` instead of cascading
    failures. Stub mode never hits the network, so it is a no-op there.
    """
    if not REAL_MODE:
        return
    try:
        HttpLLM(max_tokens=1, max_retries=1).invoke("ping")
    except Exception as exc:
        if is_auth_error(exc):
            pytest.skip(f"LLM auth failed (check LLM_API_KEY in server/.env): {exc}")
        # Other transient errors: let the tests run and surface the real failure.


@pytest.fixture(scope="session")
def real_mode() -> bool:
    return REAL_MODE


@pytest.fixture(scope="session")
def model_name() -> str:
    return MODEL if REAL_MODE else "stub"


@pytest.fixture
def agent_llm() -> Any:
    return HttpLLM(temperature=0.3) if REAL_MODE else _StubAgentLLM()


@pytest.fixture
def insight_agent_llm() -> Any:
    # Insight is analytical: a lower temperature keeps it grounded (less fabrication
    # of unsupplied facts/terms) and reduces run-to-run faithfulness variance.
    return HttpLLM(temperature=0.3) if REAL_MODE else _StubAgentLLM()


@pytest.fixture
def judge_llm() -> Any:
    if REAL_MODE:
        return HttpLLM(temperature=0.0, max_tokens=3000, json_mode=True)
    return _StubJudgeLLM()


@pytest.fixture
def knowledge_store() -> StubKnowledgeStore:
    return StubKnowledgeStore()


@pytest.fixture(scope="session")
def empathy_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases_empathy.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def insight_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases_insight.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def adversarial_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases_adversarial.json").read_text(encoding="utf-8"))

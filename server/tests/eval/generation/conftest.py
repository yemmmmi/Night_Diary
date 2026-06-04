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

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_RETRY_BASE_DELAY_S = 2.0

DATA_DIR = Path(__file__).parent
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def _load_local_dotenv() -> None:
    """Load ``server/.env`` for offline eval (gitignored); does not override existing env."""
    if not _ENV_FILE.is_file():
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


_load_local_dotenv()

_API_KEY = os.getenv("LLM_API_KEY", "")
_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
_REAL_MODE = bool(_API_KEY)

# Auth/authorization failures (invalid/expired key, no access) won't recover by
# retrying, and a dead key would otherwise crash the whole suite mid-run. We
# detect these to (a) skip retries and (b) skip the eval with a clear message.
_AUTH_ERROR_STATUSES = frozenset({401, 403})


def _is_auth_error(exc: BaseException) -> bool:
    import httpx

    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in _AUTH_ERROR_STATUSES
    )


@dataclass
class _Message:
    content: str
    response_metadata: dict[str, Any] = field(default_factory=dict)


def _usage_block(prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    return {
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_cache_miss_tokens": prompt_tokens,
        }
    }


class _HttpLLM:
    """Minimal OpenAI-compatible chat client (sync + async) over httpx."""

    def __init__(
        self,
        *,
        temperature: float = 0.7,
        max_tokens: int = 600,
        json_mode: bool = False,
        max_retries: int = 5,
    ) -> None:
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._json_mode = json_mode
        self._max_retries = max_retries

    def _payload(self, prompt: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": _MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    @staticmethod
    def _headers() -> dict[str, str]:
        return {"Authorization": f"Bearer {_API_KEY}", "Content-Type": "application/json"}

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> _Message:
        msg = data["choices"][0]["message"]
        content = (msg.get("content") or msg.get("reasoning_content") or "").strip()
        usage = data.get("usage", {})
        return _Message(
            content=content,
            response_metadata=_usage_block(
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
            ),
        )

    def _post_sync(self, prompt: str) -> _Message:
        import httpx

        url = f"{_BASE_URL.rstrip('/')}/chat/completions"
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                with httpx.Client(timeout=120.0, trust_env=False) as client:
                    resp = client.post(url, headers=self._headers(), json=self._payload(prompt))
                    resp.raise_for_status()
                    return self._parse_response(resp.json())
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                last_exc = exc
                if _is_auth_error(exc) or attempt + 1 >= self._max_retries:
                    break
                # Exponential backoff: a bare retry loop fires in milliseconds and
                # burns every attempt during a transient TLS reset / network blip.
                time.sleep(_RETRY_BASE_DELAY_S * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def _post_async(self, prompt: str) -> _Message:
        import httpx

        url = f"{_BASE_URL.rstrip('/')}/chat/completions"
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                    resp = await client.post(url, headers=self._headers(), json=self._payload(prompt))
                    resp.raise_for_status()
                    return self._parse_response(resp.json())
            except (httpx.HTTPError, KeyError, IndexError) as exc:
                last_exc = exc
                if _is_auth_error(exc) or attempt + 1 >= self._max_retries:
                    break
                await asyncio.sleep(_RETRY_BASE_DELAY_S * (2**attempt))
        assert last_exc is not None
        raise last_exc

    def invoke(self, prompt: str) -> _Message:
        return self._post_sync(prompt)

    async def ainvoke(self, prompt: str) -> _Message:
        return await self._post_async(prompt)


class _StubAgentLLM:
    """Deterministic empathetic-ish reply so stub-mode eval can be scored."""

    _REPLY = (
        "听起来你今天经历了不少起伏，这些情绪都是真实而值得被理解的。"
        "谢谢你愿意把它们写下来，我会一直在这里陪着你，慢慢来，不着急。"
    )

    def invoke(self, prompt: str) -> _Message:
        return _Message(content=self._REPLY, response_metadata=_usage_block(150, 60))

    async def ainvoke(self, prompt: str) -> _Message:
        return _Message(content=self._REPLY, response_metadata=_usage_block(150, 60))


class _StubJudgeLLM:
    """Deterministic judge returning a fixed mid-high score for every dimension."""

    def invoke(self, prompt: str) -> _Message:
        keys = ["empathy", "context_faithfulness", "relevance", "safety"]
        body = ", ".join(f'"{k}": 4' for k in keys)
        return _Message(
            content=f'{{{body}, "rationale": "stub judge"}}',
            response_metadata=_usage_block(300, 48),
        )


class StubKnowledgeStore:
    """No-op domain knowledge store for the eval (no Chroma needed)."""

    def query(self, query_text: str, max_results: int = 2, category_filter: str | None = None) -> list[Any]:
        return []


@pytest.fixture(scope="session", autouse=True)
def _llm_auth_preflight() -> None:
    """Skip the whole generation eval (with a clear message) on a dead key.

    A single cheap call in real mode: if the LLM rejects the key (401/403),
    every downstream judge call would otherwise raise mid-suite and abort the
    remaining cases. We turn that into a clean ``skip`` instead of cascading
    failures. Stub mode never hits the network, so it is a no-op there.
    """
    if not _REAL_MODE:
        return
    try:
        _HttpLLM(max_tokens=1, max_retries=1).invoke("ping")
    except Exception as exc:
        if _is_auth_error(exc):
            pytest.skip(f"LLM auth failed (check LLM_API_KEY in server/.env): {exc}")
        # Other transient errors: let the tests run and surface the real failure.


@pytest.fixture(scope="session")
def real_mode() -> bool:
    return _REAL_MODE


@pytest.fixture(scope="session")
def model_name() -> str:
    return _MODEL if _REAL_MODE else "stub"


@pytest.fixture
def agent_llm() -> Any:
    return _HttpLLM(temperature=0.8) if _REAL_MODE else _StubAgentLLM()


@pytest.fixture
def insight_agent_llm() -> Any:
    # Insight is analytical: a lower temperature keeps it grounded (less fabrication
    # of unsupplied facts/terms) and reduces run-to-run faithfulness variance.
    return _HttpLLM(temperature=0.5) if _REAL_MODE else _StubAgentLLM()


@pytest.fixture
def judge_llm() -> Any:
    if _REAL_MODE:
        return _HttpLLM(temperature=0.0, max_tokens=2000, json_mode=True)
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

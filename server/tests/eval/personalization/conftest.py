"""Fixtures for the personalization A/B eval (P0-A).

Quantifies the lift the memory system adds: every case runs twice through the
REAL worker agent — arm A with the full production-shaped state
(``long_term_profile`` + ``episodic_context``), arm B cold (diary only, a
brand-new user). The same judge grades both replies against the same
ground-truth profile context.

Two modes, mirroring the generation/treehole suites:

* **Real mode** — ``LLM_API_KEY`` set: HttpLLM for both agent and judge.
* **Stub mode** — CI: the stub agent LLM only "uses" the profile when its
  markers actually reached the prompt (proving the state → prompt wiring),
  and the stub judge scores replies by whether they referenced it. Fully
  deterministic: lift == 3.0, win rate == 1.0.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, ClassVar

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

#: Prompt markers that only appear when the profile/memory reached the agent.
_MEMORY_MARKERS: tuple[str, ...] = (
    "之前的交互记忆",  # EmpathyAgent episodic block
    "【用户画像】",  # InsightAgent profile block
    "【近期重要记忆】",  # InsightAgent episodic block
)

#: Deterministic topic extraction from the arm-A prompt (rubric order matters).
_TOPIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"反复话题[:：]\s*(.+?)(?:\n|$)", re.M),  # insight 【用户画像】
    re.compile(r"事件[:：]\s*(.+?)(?:[；;]|\n|$)"),  # empathy episodic bullet
    re.compile(r"^-\s*(.+?)（情绪", re.M),  # insight episodic line
)


def _extract_topic(prompt: str) -> str:
    """Pull the most distinctive profile/memory token out of an arm-A prompt."""
    for pattern in _TOPIC_PATTERNS:
        match = pattern.search(prompt)
        if match:
            token = match.group(1).strip()
            token = re.split(r"[,，、]", token)[0].strip()
            if token:
                return token[:24]
    return ""


class _StubAgentLLM:
    """Deterministic LLM that personalizes ONLY if profile markers hit the prompt.

    This is the wiring oracle: if the eval harness fails to thread
    ``long_term_profile`` / ``episodic_context`` into the agent state, arm A's
    prompt looks identical to arm B's and the stub replies generically —
    the lift collapses to 0 and the stub-mode assertion fails.
    """

    def _reply(self, prompt: str) -> str:
        if any(marker in prompt for marker in _MEMORY_MARKERS):
            topic = _extract_topic(prompt)
            if topic:
                return (
                    f"我注意到你这段时间一直在「{topic}」这件事上打转，"
                    "这不是第一次了。谢谢你今天也愿意把它写下来，我在听。"
                )
            return "我注意到你最近的状态有些反复，谢谢你愿意继续写下来，我在听。"
        return (
            "听起来你今天经历了不少起伏，这些情绪都是真实而值得被理解的。"
            "谢谢你愿意把它们写下来，我会一直在这里陪着你，慢慢来，不着急。"
        )

    def invoke(self, prompt: str) -> Message:
        return Message(content=self._reply(prompt), response_metadata=usage_block(150, 60))

    async def ainvoke(self, prompt: str) -> Message:
        return self.invoke(prompt)


class _StubJudgeLLM:
    """Deterministic judge: high personalization only for replies that used memory."""

    _KEYS: ClassVar[list[str]] = ["personalization", "empathy"]

    def invoke(self, prompt: str) -> Message:
        reply = prompt.split("【待评 AI 回复】", 1)[-1] if "【待评 AI 回复】" in prompt else ""
        personalization = 5 if "我注意到" in reply else 2
        body = ", ".join(
            f'"{k}": {personalization if k == "personalization" else 4}' for k in self._KEYS
        )
        return Message(
            content=f'{{{body}, "rationale": "stub personalization judge"}}',
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
    """Skip the whole eval (with a clear message) on a dead LLM key."""
    if not REAL_MODE:
        return
    try:
        HttpLLM(max_tokens=1, max_retries=1).invoke("ping")
    except Exception as exc:
        if is_auth_error(exc):
            pytest.skip(f"LLM auth failed (check LLM_API_KEY in server/.env): {exc}")


@pytest.fixture(scope="session")
def real_mode() -> bool:
    return REAL_MODE


@pytest.fixture(scope="session")
def model_name() -> str:
    return MODEL if REAL_MODE else "stub"


@pytest.fixture
def agent_llm() -> Any:
    return HttpLLM(temperature=0.3, max_tokens=1500) if REAL_MODE else _StubAgentLLM()


@pytest.fixture
def judge_llm() -> Any:
    if REAL_MODE:
        return HttpLLM(temperature=0.0, max_tokens=3000, json_mode=True)
    return _StubJudgeLLM()


@pytest.fixture
def knowledge_store() -> StubKnowledgeStore:
    return StubKnowledgeStore()


@pytest.fixture(scope="session")
def personalization_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases.json").read_text(encoding="utf-8"))

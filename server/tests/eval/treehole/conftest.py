"""Fixtures for the offline tree-hole digest-quality eval (robustness P0-2).

Evaluates the scene-1 tree-hole pipeline (:func:`run_treehole`) — the short
reply + structured day digest — with the LLM-as-Judge:

* **summary_faithfulness** — 摘要忠实概括日记，不编造不遗漏
* **emotion_accuracy** — 情绪 / 意图判断与日记一致
* **temporal_correctness** — temporal_refs 正确捕获非当天事件（方向/内容），当天事件不误入
* **reply_brevity** — 回复简短（≤40 字）且自然

Reuses the generation eval's LLM plumbing (real HTTP LLM with retries /
deterministic stub / auth preflight) via ``pytest_plugins``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, ClassVar

import pytest

# Reuse the generation eval's LLM fixtures (real HttpLLM + stub + auth preflight).
pytest_plugins = ["tests.eval.generation.conftest"]

from tests.eval.generation.conftest import _HttpLLM, _Message, _usage_block  # noqa: E402

DATA_DIR = Path(__file__).parent


class _StubTreeHoleLLM:
    """Deterministic valid tree-hole JSON so stub-mode eval exercises the path."""

    _JSON = json.dumps(
        {
            "reply": "今天辛苦了，抱抱你。",
            "summary": "加班到很晚，项目延期，有些焦虑，还提到了昨天和妈妈的争执。",
            "topics": ["加班", "项目", "家庭"],
            "temporal_refs": [
                {"direction": "past", "date_hint": "昨天", "summary": "和妈妈吵架"}
            ],
            "key_events": ["加班", "得知项目延期"],
            "emotional_shifts": ["平静", "焦虑"],
            "relationships": [],
            "conflicts": ["项目延期带来压力"],
            "concerns": ["担心延期影响晋升"],
        },
        ensure_ascii=False,
    )

    def invoke(self, prompt: str) -> _Message:
        return _Message(content=self._JSON, response_metadata=_usage_block(150, 60))

    async def ainvoke(self, prompt: str) -> _Message:
        return self.invoke(prompt)


class _StubTreeHoleJudgeLLM:
    """Deterministic judge returning a fixed mid-high score for the tree-hole
    dimensions (overrides the generation stub judge whose keys differ)."""

    _KEYS: ClassVar[list[str]] = [
        "summary_faithfulness",
        "emotion_accuracy",
        "temporal_correctness",
        "reply_brevity",
    ]

    def invoke(self, prompt: str) -> _Message:
        body = ", ".join(f'"{k}": 4' for k in self._KEYS)
        return _Message(
            content=f'{{{body}, "rationale": "stub treehole judge"}}',
            response_metadata=_usage_block(300, 48),
        )


@pytest.fixture
def treehole_llm(real_mode: bool) -> Any:
    """Tree-hole extraction LLM (JSON mode in real runs)."""
    if real_mode:
        return _HttpLLM(temperature=0.4, max_tokens=800, json_mode=True)
    return _StubTreeHoleLLM()


@pytest.fixture
def judge_llm(real_mode: bool) -> Any:
    """Judge LLM with the tree-hole dimension keys (overrides generation's)."""
    if real_mode:
        return _HttpLLM(temperature=0.0, max_tokens=2000, json_mode=True)
    return _StubTreeHoleJudgeLLM()


@pytest.fixture(scope="session")
def treehole_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases_treehole.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def treehole_day() -> date:
    return date(2026, 8, 12)

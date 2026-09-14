"""Fixtures for the offline tree-hole digest-quality eval (robustness P0-2).

Evaluates the scene-1 tree-hole pipeline (:func:`run_treehole`) — the short
reply + structured day digest — with the LLM-as-Judge:

* **summary_faithfulness** — 摘要忠实概括日记，不编造不遗漏
* **emotion_accuracy** — 情绪 / 意图判断与日记一致
* **temporal_correctness** — temporal_refs 正确捕获非当天事件（方向/内容），当天事件不误入
* **reply_brevity** — 回复简短（≤40 字）且自然

Reuses the generation eval's LLM plumbing (real HTTP LLM with retries /
deterministic stub / auth preflight) by importing its classes and constants
directly — ``pytest_plugins`` is NOT used because pytest 9 rejects it in a
non-top-level conftest (the whole suite collects ``tests/eval/**`` on CI).
"""

from __future__ import annotations

import json
from datetime import date
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

    def invoke(self, prompt: str) -> Message:
        return Message(content=self._JSON, response_metadata=usage_block(150, 60))

    async def ainvoke(self, prompt: str) -> Message:
        return self.invoke(prompt)


class _StubTreeHoleJudgeLLM:
    """Deterministic judge returning a fixed mid-high score for the tree-hole
    dimensions (the generation stub judge's keys differ)."""

    _KEYS: ClassVar[list[str]] = [
        "summary_faithfulness",
        "emotion_accuracy",
        "temporal_correctness",
        "reply_brevity",
    ]

    def invoke(self, prompt: str) -> Message:
        body = ", ".join(f'"{k}": 4' for k in self._KEYS)
        return Message(
            content=f'{{{body}, "rationale": "stub treehole judge"}}',
            response_metadata=usage_block(300, 48),
        )


@pytest.fixture(scope="session", autouse=True)
def _treehole_auth_preflight() -> None:
    """Skip the tree-hole eval on a dead LLM key (mirrors generation eval)."""
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
def treehole_llm(real_mode: bool) -> Any:
    """Tree-hole extraction LLM (JSON mode, low temperature, generous budget).

    Pretty-printed JSON with Chinese text can exceed 800 tokens — a truncated
    reply fails to parse and silently falls back to rules.
    """
    if real_mode:
        return HttpLLM(temperature=0.2, max_tokens=1500, json_mode=True)
    return _StubTreeHoleLLM()


@pytest.fixture
def judge_llm(real_mode: bool) -> Any:
    """Judge LLM with the tree-hole dimension keys."""
    if real_mode:
        return HttpLLM(temperature=0.0, max_tokens=3000, json_mode=True)
    return _StubTreeHoleJudgeLLM()


@pytest.fixture(scope="session")
def treehole_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases_treehole.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def treehole_day() -> date:
    return date(2026, 8, 12)

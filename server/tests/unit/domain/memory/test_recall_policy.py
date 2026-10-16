"""已退役记忆召回门控的策略表测试。"""

from __future__ import annotations

import pytest

from app.domain.memory.recall_policy import (
    HISTORY_SECTION_MAX,
    RETROSPECTIVE_INTENTS,
    allow_superseded_recall,
)


@pytest.mark.parametrize("intent", sorted(RETROSPECTIVE_INTENTS))
def test_retrospective_intents_allow_recall(intent: str) -> None:
    assert allow_superseded_recall(intent, crisis_detected=False) is True


@pytest.mark.parametrize(
    "intent",
    [
        "emotional_support",
        "advice_seeking",
        "casual_chat",
        "pure_record",
        "habit_tracking",
        "crisis_signal",
        "",
        None,
    ],
)
def test_non_retrospective_intents_deny_recall(intent: str | None) -> None:
    assert allow_superseded_recall(intent, crisis_detected=False) is False


def test_crisis_red_line_overrides_every_intent() -> None:
    """危机是硬红线：任何意图都不能放行（spec §3.1）。"""
    for intent in sorted(RETROSPECTIVE_INTENTS):
        assert allow_superseded_recall(intent, crisis_detected=True) is False


def test_history_section_is_capped_at_two() -> None:
    assert HISTORY_SECTION_MAX == 2

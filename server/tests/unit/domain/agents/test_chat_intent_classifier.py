"""Unit tests for ChatIntentClassifier — rule layer for chat intents.

The rule layer is deterministic and short-circuits above the 0.9 confidence
threshold, so these tests build a classifier WITHOUT an LLM (``ChatIntentClassifier()``)
and exercise :meth:`classify_sync`. This isolates the keyword routing from any
network/LLM behaviour and keeps the safety-gate assertions (crisis overrides)
explicit.
"""

from __future__ import annotations

from app.domain.agents.chat_intent_classifier import ChatIntentClassifier
from app.domain.agents.types import ChatIntent


def test_classify_plan_exploration() -> None:
    """'帮我规划' 应分类为 plan_exploration（heavy tier，需只读计划工具）。"""
    classifier = ChatIntentClassifier()  # no LLM -> rule layer decides
    result = classifier.classify_sync("帮我规划一下下周的学习计划")
    assert result.intent_category == ChatIntent.PLAN_EXPLORATION.value
    assert "list_todos" in result.need_tools
    assert "get_plan_progress" in result.need_tools
    assert result.tier == "heavy"
    assert result.max_iterations == 5


def test_classify_task_command() -> None:
    """'加到待办' 应分类为 task_command（light tier，短指令不被 casual 截获）。"""
    classifier = ChatIntentClassifier()
    result = classifier.classify_sync("把明天开会加到待办")
    assert result.intent_category == ChatIntent.TASK_COMMAND.value
    assert result.tier == "light"
    assert result.max_iterations == 2
    assert "list_todos" in result.need_tools


def test_crisis_overrides_plan_exploration() -> None:
    """危机关键词 + 规划词：危机优先短路（安全门控）。"""
    classifier = ChatIntentClassifier()
    result = classifier.classify_sync("我不想活了，帮我规划一下")
    assert result.intent_category == ChatIntent.CRISIS_SIGNAL.value
    assert result.tier == "crisis"

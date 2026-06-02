"""Unit tests for SentimentSkill."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domain.skills.sentiment_skill import SentimentSkill


def test_sentiment_skill_activates_on_emotional_text() -> None:
    skill = SentimentSkill()
    score = skill.activation_score("今天特别难过，也很焦虑。", {"intent": "pure_record"})
    assert score >= 0.7
    assert skill.can_activate("今天特别难过，也很焦虑。")


def test_sentiment_skill_low_score_on_neutral_text() -> None:
    skill = SentimentSkill()
    assert skill.activation_score("今天完成了代码 review。") < 0.3


def test_execute_uses_injected_llm() -> None:
    skill = SentimentSkill()
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="情感倾向：负面")
    result = skill.execute({"diary_content": "今天很难过", "llm": llm})
    assert "负面" in result
    llm.invoke.assert_called_once()


def test_execute_without_llm_returns_fallback_message() -> None:
    skill = SentimentSkill()
    assert "缺少 LLM" in skill.execute({"diary_content": "今天很难过"})

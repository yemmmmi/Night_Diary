"""Unit tests for SkillInjector strategies (FullInjection & ProgressiveDisclosure)."""

from __future__ import annotations

from app.domain.skills.injection import (
    FullInjectionStrategy,
    ProgressiveDisclosureStrategy,
    SkillInjector,
)
from app.domain.skills.skill_loader import SkillDoc

# ---------------------------------------------------------------------------
# Fixtures — minimal SkillDoc instances
# ---------------------------------------------------------------------------

SKILL_A = SkillDoc(
    name="crisis_detector",
    summary=(
        "---\nname: crisis_detector\npriority: 2.0\ntoken_cost_estimate: 50\n---\n\n"
        "## 一句话摘要\n识别极端负面情绪并触发安全干预。"
    ),
    body="## 触发条件\n当含自杀信号时激活。\n\n## 能力详述\n返回心理援助资源。",
    full_text=(
        "---\nname: crisis_detector\npriority: 2.0\ntoken_cost_estimate: 50\n---\n\n"
        "# 危机检测技能\n\n## 一句话摘要\n识别极端负面情绪并触发安全干预。\n\n"
        "## 触发条件\n当含自杀信号时激活。\n\n## 能力详述\n返回心理援助资源。"
    ),
)

SKILL_B = SkillDoc(
    name="sentiment_skill",
    summary=(
        "---\nname: sentiment_skill\npriority: 1.2\ntoken_cost_estimate: 150\n---\n\n"
        "## 一句话摘要\n分析文本情感倾向和强度。"
    ),
    body="## 触发条件\n当含情感词时激活。\n\n## 能力详述\n调用 LLM 分析情感。",
    full_text=(
        "---\nname: sentiment_skill\npriority: 1.2\ntoken_cost_estimate: 150\n---\n\n"
        "# 情感分析技能\n\n## 一句话摘要\n分析文本情感倾向和强度。\n\n"
        "## 触发条件\n当含情感词时激活。\n\n## 能力详述\n调用 LLM 分析情感。"
    ),
)

BASE_PROMPT = "请分析以下日记内容并生成共情回复。"


# ---------------------------------------------------------------------------
# SkillInjector abstract base
# ---------------------------------------------------------------------------

def test_skill_injector_is_abstract() -> None:
    """SkillInjector cannot be instantiated directly."""
    import abc

    assert issubclass(SkillInjector, abc.ABC)
    try:
        SkillInjector()  # type: ignore[abstract]
        raise AssertionError("Should have raised TypeError")
    except TypeError:
        pass


def test_estimate_tokens_static_method() -> None:
    tokens = SkillInjector.estimate_tokens("hello world 你好世界")
    assert isinstance(tokens, int)
    assert tokens > 0


# ---------------------------------------------------------------------------
# FullInjectionStrategy
# ---------------------------------------------------------------------------

def test_full_injection_includes_all_full_text() -> None:
    strategy = FullInjectionStrategy()
    result = strategy.inject_prompt([SKILL_A, SKILL_B], BASE_PROMPT)

    assert BASE_PROMPT in result
    assert "crisis_detector" in result
    assert "sentiment_skill" in result
    # Full text should contain all sections
    assert "## 一句话摘要" in result
    assert "## 触发条件" in result
    assert "## 能力详述" in result
    assert "危机检测技能" in result
    assert "情感分析技能" in result


def test_full_injection_contains_header_and_footer() -> None:
    strategy = FullInjectionStrategy()
    result = strategy.inject_prompt([SKILL_A], BASE_PROMPT)
    assert "可用技能文档" in result
    assert "技能文档结束" in result


def test_full_injection_no_skills_returns_base_prompt() -> None:
    strategy = FullInjectionStrategy()
    result = strategy.inject_prompt([], BASE_PROMPT)
    assert result == BASE_PROMPT


def test_full_injection_empty_base_prompt() -> None:
    strategy = FullInjectionStrategy()
    result = strategy.inject_prompt([SKILL_A], "")
    assert "crisis_detector" in result
    assert not result.startswith("\n")


def test_full_injection_estimates_token_cost() -> None:
    strategy = FullInjectionStrategy()
    cost = strategy.estimate_injection_cost([SKILL_A, SKILL_B])
    assert isinstance(cost, int)
    assert cost > 0


# ---------------------------------------------------------------------------
# ProgressiveDisclosureStrategy
# ---------------------------------------------------------------------------

def test_progressive_includes_summaries_only() -> None:
    strategy = ProgressiveDisclosureStrategy()
    result = strategy.inject_prompt([SKILL_A, SKILL_B], BASE_PROMPT)

    assert BASE_PROMPT in result
    # Summaries should be present
    assert "crisis_detector" in result
    assert "sentiment_skill" in result
    assert "识别极端负面情绪并触发安全干预。" in result
    assert "分析文本情感倾向和强度。" in result
    # Full body sections should NOT be in the prompt
    assert "## 触发条件" not in result
    assert "## 能力详述" not in result


def test_progressive_includes_use_skill_instruction() -> None:
    strategy = ProgressiveDisclosureStrategy()
    result = strategy.inject_prompt([SKILL_A], BASE_PROMPT)
    assert "<use_skill>" in result
    assert "</use_skill>" in result
    assert "按需加载" in result


def test_progressive_includes_header_and_footer() -> None:
    strategy = ProgressiveDisclosureStrategy()
    result = strategy.inject_prompt([SKILL_A], BASE_PROMPT)
    assert "可用技能摘要" in result
    assert "技能摘要结束" in result


def test_progressive_no_skills_returns_base_prompt() -> None:
    strategy = ProgressiveDisclosureStrategy()
    result = strategy.inject_prompt([], BASE_PROMPT)
    assert result == BASE_PROMPT


def test_progressive_empty_base_prompt() -> None:
    strategy = ProgressiveDisclosureStrategy()
    result = strategy.inject_prompt([SKILL_A], "")
    assert "crisis_detector" in result
    assert not result.startswith("\n")


def test_progressive_estimates_token_cost() -> None:
    strategy = ProgressiveDisclosureStrategy()
    cost = strategy.estimate_injection_cost([SKILL_A, SKILL_B])
    assert isinstance(cost, int)
    assert cost > 0


# ---------------------------------------------------------------------------
# Strategy comparison — progressive should be cheaper than full
# ---------------------------------------------------------------------------

def test_progressive_is_cheaper_than_full() -> None:
    """Progressive disclosure injects less text (summaries only)."""
    full = FullInjectionStrategy()
    progressive = ProgressiveDisclosureStrategy()
    skills = [SKILL_A, SKILL_B]

    full_cost = full.estimate_injection_cost(skills)
    progressive_cost = progressive.estimate_injection_cost(skills)

    assert progressive_cost < full_cost, (
        f"Progressive ({progressive_cost}) should be cheaper than full ({full_cost})"
    )


def test_progressive_with_real_skill_docs() -> None:
    """End-to-end: load real SKILL.md files and inject with both strategies."""
    from app.domain.skills.skill_loader import SkillDocLoader

    loader = SkillDocLoader()
    docs = loader.load_all()
    skills = list(docs.values())
    assert len(skills) == 4

    full = FullInjectionStrategy()
    progressive = ProgressiveDisclosureStrategy()

    full_prompt = full.inject_prompt(skills, BASE_PROMPT)
    progressive_prompt = progressive.inject_prompt(skills, BASE_PROMPT)

    # Both should contain all skill names
    for name in ("crisis_detector", "sentiment_skill", "memory_recall", "entity_tracker"):
        assert name in full_prompt
        assert name in progressive_prompt

    # Progressive should mention use_skill mechanism
    assert "<use_skill>" in progressive_prompt

    # Progressive prompt should be shorter
    assert len(progressive_prompt) < len(full_prompt)

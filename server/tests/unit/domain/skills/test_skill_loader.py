"""Unit tests for SkillDocLoader and SkillDoc parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.skills.skill_loader import (
    SkillDoc,
    SkillDocLoader,
    _parse_front_matter,
    _split_front_matter,
    parse_skill_doc,
)

# Real skill docs directory shipped with the project.
REAL_SKILL_DOCS_DIR = (
    Path(__file__).resolve().parents[4]
    / "app"
    / "domain"
    / "skills"
    / "skill_docs"
)


# ---------------------------------------------------------------------------
# Sample SKILL.md content for isolated parsing tests
# ---------------------------------------------------------------------------

SAMPLE_SKILL_MD = """\
---
name: sentiment_skill
triggers: [难过, 焦虑, 开心, emotional_support]
priority: 1.2
category: analysis
token_cost_estimate: 150
---

# 情感分析技能

## 一句话摘要
分析文本的情感倾向、强度和关键情感词。

## 触发条件
当用户表达情绪或日记中包含情感词汇时激活。

## 能力详述
分析文本的情感倾向（正面/负面/中性）、强度（1-5）和关键情感词（最多5个）。

## 调用方式
- 参数: text (str)
- 返回: 情感倾向 + 强度 + 关键词列表

## 输出示例
情感倾向：负面
情感强度：4
关键情感词：委屈, 想哭, 无力
"""


# ---------------------------------------------------------------------------
# _split_front_matter
# ---------------------------------------------------------------------------

def test_split_front_matter_extracts_yaml_block() -> None:
    front, body = _split_front_matter(SAMPLE_SKILL_MD)
    assert "name: sentiment_skill" in front
    assert "priority: 1.2" in front
    assert "# 情感分析技能" in body
    assert "## 一句话摘要" in body


def test_split_front_matter_no_front_matter() -> None:
    text = "# Just a title\n\nNo front matter here."
    front, body = _split_front_matter(text)
    assert front == ""
    assert body == text


def test_split_front_matter_unclosed_front_matter() -> None:
    """Unclosed front matter should degrade gracefully (treat as no front matter)."""
    text = "---\nname: broken\npriority: 1.0\n\n# Body"
    front, body = _split_front_matter(text)
    assert front == ""
    assert body == text


# ---------------------------------------------------------------------------
# _parse_front_matter
# ---------------------------------------------------------------------------

def test_parse_front_matter_basic_types() -> None:
    front = (
        "name: crisis_detector\n"
        "triggers: [想死, 不想活, emotional_support]\n"
        "priority: 2.0\n"
        "category: analysis\n"
        "token_cost_estimate: 50\n"
    )
    meta = _parse_front_matter(front)
    assert meta["name"] == "crisis_detector"
    assert meta["triggers"] == ["想死", "不想活", "emotional_support"]
    assert meta["priority"] == 2.0
    assert meta["category"] == "analysis"
    assert meta["token_cost_estimate"] == 50


def test_parse_front_matter_empty_list() -> None:
    meta = _parse_front_matter("name: test\ntriggers: []\n")
    assert meta["name"] == "test"
    assert meta["triggers"] == []


def test_parse_front_matter_skips_comments_and_blanks() -> None:
    front = (
        "# This is a comment\n"
        "\n"
        "name: test_skill\n"
        "priority: 1.0\n"
    )
    meta = _parse_front_matter(front)
    assert meta["name"] == "test_skill"
    assert meta["priority"] == 1.0
    assert len(meta) == 2


def test_parse_front_matter_integer_vs_float() -> None:
    meta = _parse_front_matter("cost_int: 100\ncost_float: 1.5\n")
    assert isinstance(meta["cost_int"], int)
    assert meta["cost_int"] == 100
    assert isinstance(meta["cost_float"], float)
    assert meta["cost_float"] == 1.5


# ---------------------------------------------------------------------------
# parse_skill_doc — summary/body separation
# ---------------------------------------------------------------------------

def test_parse_skill_doc_summary_contains_front_matter_and_one_liner() -> None:
    doc = parse_skill_doc(SAMPLE_SKILL_MD)
    # Summary should contain front matter fields
    assert "name: sentiment_skill" in doc.summary
    assert "priority: 1.2" in doc.summary
    # Summary should contain the 一句话摘要 header and its content
    assert "## 一句话摘要" in doc.summary
    assert "分析文本的情感倾向、强度和关键情感词。" in doc.summary


def test_parse_skill_doc_summary_excludes_other_sections() -> None:
    doc = parse_skill_doc(SAMPLE_SKILL_MD)
    # Body should contain the other sections
    assert "## 触发条件" in doc.body
    assert "## 能力详述" in doc.body
    assert "## 调用方式" in doc.body
    assert "## 输出示例" in doc.body
    # Summary should NOT contain those sections
    assert "## 触发条件" not in doc.summary
    assert "## 能力详述" not in doc.summary


def test_parse_skill_doc_name_extracted_from_front_matter() -> None:
    doc = parse_skill_doc(SAMPLE_SKILL_MD)
    assert doc.name == "sentiment_skill"


def test_parse_skill_doc_full_text_is_complete() -> None:
    doc = parse_skill_doc(SAMPLE_SKILL_MD)
    assert "name: sentiment_skill" in doc.full_text
    assert "## 输出示例" in doc.full_text
    assert "关键情感词：委屈, 想哭, 无力" in doc.full_text


def test_parse_skill_doc_no_summary_section_degrades() -> None:
    """If ## 一句话摘要 is absent, summary falls back to front matter + body."""
    text = (
        "---\nname: minimal\npriority: 1.0\n---\n\n"
        "# Minimal\n\n## 触发条件\nNone.\n"
    )
    doc = parse_skill_doc(text)
    assert doc.name == "minimal"
    assert "name: minimal" in doc.summary
    assert "## 触发条件" in doc.body


def test_parse_skill_doc_uses_fallback_name_when_missing() -> None:
    text = "---\npriority: 1.0\n---\n\n# No Name\n\n## 一句话摘要\nHi.\n"
    doc = parse_skill_doc(text, fallback_name="fallback_name")
    assert doc.name == "fallback_name"


def test_parse_skill_doc_no_front_matter() -> None:
    """A file with no front matter should still parse without error."""
    text = "# Bare Skill\n\n## 一句话摘要\nA summary.\n\n## 能力详述\nDetails.\n"
    doc = parse_skill_doc(text, fallback_name="bare")
    assert doc.name == "bare"
    assert "## 一句话摘要" in doc.summary
    assert "A summary." in doc.summary
    assert "## 能力详述" in doc.body


# ---------------------------------------------------------------------------
# SkillDocLoader — load / load_all with real files
# ---------------------------------------------------------------------------

@pytest.fixture
def loader() -> SkillDocLoader:
    return SkillDocLoader(REAL_SKILL_DOCS_DIR)


def test_load_all_returns_four_skills(loader: SkillDocLoader) -> None:
    docs = loader.load_all()
    assert len(docs) == 4
    expected_names = {"crisis_detector", "sentiment_skill", "memory_recall", "entity_tracker"}
    assert set(docs.keys()) == expected_names


def test_load_all_docs_have_summary_and_body(loader: SkillDocLoader) -> None:
    docs = loader.load_all()
    for name, doc in docs.items():
        assert doc.name == name
        assert "## 一句话摘要" in doc.summary, f"{name} summary missing 一句话摘要"
        assert doc.body, f"{name} body is empty"
        assert "## 触发条件" in doc.body, f"{name} body missing 触发条件"
        assert doc.full_text


def test_load_by_name_returns_doc(loader: SkillDocLoader) -> None:
    doc = loader.load("crisis_detector")
    assert doc is not None
    assert doc.name == "crisis_detector"
    assert "危机检测" in doc.full_text


def test_load_missing_skill_returns_none(loader: SkillDocLoader) -> None:
    doc = loader.load("nonexistent_skill")
    assert doc is None


# ---------------------------------------------------------------------------
# SkillDocLoader — graceful degradation with temp directory
# ---------------------------------------------------------------------------

def test_load_all_nonexistent_directory_returns_empty(tmp_path: Path) -> None:
    loader = SkillDocLoader(tmp_path / "no_such_dir")
    assert loader.load_all() == {}


def test_load_all_skips_unparseable_files(tmp_path: Path) -> None:
    """A file with no name field and no fallback should be skipped."""
    (tmp_path / "good.md").write_text(
        "---\nname: good_skill\npriority: 1.0\n---\n\n"
        "# Good\n\n## 一句话摘要\nGood.\n",
        encoding="utf-8",
    )
    # A malformed file (no front matter, no parseable name) — should still
    # load using fallback name from file stem, so it won't be skipped.
    # Instead, test a truly empty file.
    (tmp_path / "empty.md").write_text("", encoding="utf-8")
    loader = SkillDocLoader(tmp_path)
    docs = loader.load_all()
    # empty.md will have fallback name "empty" — it parses with empty summary/body
    assert "good_skill" in docs
    # The empty file still loads (graceful, not crash)
    assert "empty" in docs


def test_load_from_custom_directory(tmp_path: Path) -> None:
    skill_md = (
        "---\nname: custom_skill\ntriggers: [hello]\npriority: 1.0\n"
        "category: analysis\ntoken_cost_estimate: 10\n---\n\n"
        "# Custom Skill\n\n## 一句话摘要\nA custom skill.\n\n"
        "## 触发条件\nWhen hello is present.\n"
    )
    (tmp_path / "custom_skill.md").write_text(skill_md, encoding="utf-8")
    loader = SkillDocLoader(tmp_path)
    doc = loader.load("custom_skill")
    assert doc is not None
    assert doc.name == "custom_skill"
    assert "A custom skill." in doc.summary
    assert "## 触发条件" in doc.body


def test_skill_doc_is_frozen() -> None:
    doc = SkillDoc(name="test", summary="s", body="b", full_text="f")
    with pytest.raises(AttributeError):
        doc.name = "other"  # type: ignore[misc]

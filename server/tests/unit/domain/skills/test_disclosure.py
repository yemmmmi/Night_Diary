"""Unit tests for progressive skill disclosure (Level 0 metadata + Level 1 body)."""

from __future__ import annotations

from pathlib import Path

from app.domain.skills.disclosure import (
    SKILL_DOC_HEADER,
    SkillDisclosure,
    format_skill_doc_reference,
    get_skill_disclosure,
)
from app.domain.skills.user_skill_registry import (
    UserSkillRegistry,
    UserSkillSpec,
    get_user_skill_registry,
)


class TestLevel0:
    def test_items_cover_all_registered_skills(self) -> None:
        items = get_skill_disclosure().level0_items()
        assert [item.id for item in items] == ["record", "insight", "plan"]
        assert all(item.token_cost > 0 for item in items)

    def test_catalog_lists_ids_labels_and_costs(self) -> None:
        catalog = get_skill_disclosure().level0_catalog()
        assert "record" in catalog
        assert "记录" in catalog
        assert "180" in catalog

    def test_catalog_is_cheap(self) -> None:
        disclosure = get_skill_disclosure()
        assert 0 < disclosure.estimate_level0_tokens() < 200

    def test_empty_registry_yields_empty_catalog(self) -> None:
        disclosure = SkillDisclosure(UserSkillRegistry())
        assert disclosure.level0_catalog() == ""
        assert disclosure.estimate_level0_tokens() == 0


class TestLevel1:
    def test_body_loaded_for_registered_skill(self) -> None:
        body = get_skill_disclosure().level1_body("record")
        assert body
        assert "触发条件" in body

    def test_body_missing_for_unknown_skill(self) -> None:
        assert get_skill_disclosure().level1_body("nope") == ""

    def test_doc_cached_across_calls(self) -> None:
        disclosure = SkillDisclosure()
        first = disclosure.load_doc("insight")
        second = disclosure.load_doc("insight")
        assert first is second

    def test_missing_doc_file_degrades_to_empty(self, tmp_path: Path) -> None:
        registry = UserSkillRegistry()
        registry.register(
            UserSkillSpec(
                id="ghost",
                label="幽灵",
                description="doc file does not exist",
                doc_path="ghost.md",
            ),
            lambda *a, **k: None,
        )
        disclosure = SkillDisclosure(registry, docs_dir=tmp_path)
        assert disclosure.level1_body("ghost") == ""


class TestFormatReference:
    def test_empty_body_is_noop(self) -> None:
        assert format_skill_doc_reference("") == ""
        assert format_skill_doc_reference("   ") == ""

    def test_non_empty_body_is_wrapped(self) -> None:
        wrapped = format_skill_doc_reference("正文")
        assert SKILL_DOC_HEADER in wrapped
        assert wrapped.startswith("\n\n")
        assert "正文" in wrapped


def test_singleton_is_stable() -> None:
    assert get_skill_disclosure() is get_skill_disclosure()
    assert get_skill_disclosure()._registry is get_user_skill_registry()
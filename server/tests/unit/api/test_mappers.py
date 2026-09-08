"""Focused compatibility tests for API JSON mappers."""

from app.api.mappers import normalize_skill_result, source_links_from_json


def test_source_links_from_json_normalizes_legacy_verified() -> None:
    links = source_links_from_json(
        '[{"url":"https://example.com","verified":true,"is_primary":true}]'
    )
    assert links == [
        {
            "url": "https://example.com",
            "multi_source": True,
            "is_primary": True,
        }
    ]


def test_normalize_skill_result_reads_legacy_plan_tasks() -> None:
    result = normalize_skill_result(
        {
            "skill": "plan",
            "tasks": [{"id": "t1", "verified": True}],
        }
    )
    assert result["tasks"] == [{"id": "t1", "multi_source": True}]


def test_normalize_skill_result_prefers_new_field() -> None:
    result = normalize_skill_result(
        {
            "skill": "plan",
            "tasks": [
                {
                    "id": "t1",
                    "multi_source": False,
                    "verified": True,
                }
            ],
        }
    )
    assert result["tasks"] == [{"id": "t1", "multi_source": False}]

"""Unit tests for KnowledgeExtractor."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.domain.knowledge.extractor import MIN_CONTENT_LENGTH, KnowledgeExtractor
from app.domain.knowledge.types import EntityType


class StubLLM:
    def __init__(self, response: str) -> None:
        self.ainvoke = AsyncMock(return_value=response)


class TestValidateResult:
    def setup_method(self) -> None:
        self.extractor = KnowledgeExtractor()

    def test_valid_full_result(self) -> None:
        raw = {
            "persons": [{"name": "小明", "relation": "同事", "sentiment": 0.6}],
            "events": [
                {
                    "description": "开会讨论项目",
                    "inferred_date": "2024-01-15",
                    "emotion": "焦虑",
                }
            ],
            "places": ["公司", "咖啡厅"],
            "topics": ["工作", "项目管理"],
            "mood_score": -0.3,
        }

        result = self.extractor._validate_result(raw)

        assert result["persons"][0]["name"] == "小明"
        assert result["events"][0]["description"] == "开会讨论项目"
        assert result["places"] == ["公司", "咖啡厅"]
        assert result["mood_score"] == -0.3

    def test_mood_score_clamped(self) -> None:
        assert self.extractor._validate_result({"mood_score": 5.0})["mood_score"] == 1.0
        assert self.extractor._validate_result({"mood_score": -3.0})["mood_score"] == -1.0


class TestExtract:
    @pytest.mark.asyncio
    async def test_skips_short_content(self) -> None:
        extractor = KnowledgeExtractor(llm=StubLLM("{}"))
        assert await extractor.extract("短内容") is None

    @pytest.mark.asyncio
    async def test_parses_json_response(self) -> None:
        payload = (
            '{"persons": [], "events": [], "places": ["北京"], '
            '"topics": ["旅行"], "mood_score": 0.2}'
        )
        extractor = KnowledgeExtractor(llm=StubLLM(payload))
        content = "x" * (MIN_CONTENT_LENGTH + 1)

        result = await extractor.extract(content)

        assert result is not None
        assert result["places"] == ["北京"]
        assert result["topics"] == ["旅行"]

    @pytest.mark.asyncio
    async def test_strips_markdown_fence(self) -> None:
        payload = (
            '```json\n{"persons": [], "events": [], "places": [], '
            '"topics": [], "mood_score": 0.0}\n```'
        )
        extractor = KnowledgeExtractor(llm=StubLLM(payload))
        content = "x" * (MIN_CONTENT_LENGTH + 1)

        result = await extractor.extract(content)

        assert result is not None
        assert result["mood_score"] == 0.0


class TestRecordsFromExtraction:
    def test_entity_types_include_mood(self) -> None:
        extractor = KnowledgeExtractor()
        extraction = extractor._validate_result(
            {
                "persons": [{"name": "小红", "relation": "朋友", "sentiment": 0.5}],
                "events": [],
                "places": [],
                "topics": ["友情"],
                "mood_score": 0.4,
            }
        )

        records = extractor.records_from_extraction(
            "diary-1",
            extraction,
            extracted_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        entity_types = {record.entity_type for record in records}

        assert entity_types == {
            EntityType.PERSON,
            EntityType.TOPIC,
            EntityType.MOOD,
        }

    def test_zero_mood_score_is_not_persisted(self) -> None:
        extractor = KnowledgeExtractor()
        extraction = extractor._validate_result({"topics": ["工作"], "mood_score": 0.0})

        records = extractor.records_from_extraction("diary-2", extraction)

        assert all(record.entity_type != EntityType.MOOD for record in records)

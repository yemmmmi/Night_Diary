"""Structured entity extraction from diary content."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from app.domain.knowledge.types import (
    EntityRecord,
    EntityType,
    ExtractionResult,
)

logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 100

EXTRACTION_PROMPT = """请从以下日记内容中提取结构化信息，严格按照 JSON 格式输出。

要求：
1. persons: 提取提到的人物，每个人物包含 name（姓名/称呼）、relation（关系，如同事/朋友/家人，未知则为空）、sentiment（情感倾向，-1.0到1.0）
2. events: 提取主要事件，每个事件包含 description（简短描述）、inferred_date（推断日期，格式YYYY-MM-DD，无法推断则为空）、emotion（情绪标签，如开心/难过/焦虑）
3. places: 提取提到的地点名称列表
4. topics: 提取主要话题/主题列表（如工作、健康、感情）
5. mood_score: 整体情绪分数，-1.0（极度负面）到 1.0（极度正面）

如果某个类别没有相关信息，返回空列表或 0.0。

日记内容：
{content}

请直接输出 JSON，不要包含其他文字：
{{"persons": [...], "events": [...], "places": [...], "topics": [...], "mood_score": 0.0}}"""


class LLMClient(Protocol):
    async def ainvoke(self, prompt: str) -> str: ...


class KnowledgeExtractor:
    """Extract structured entities from diary text via a single LLM call."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    async def extract(self, content: str) -> ExtractionResult | None:
        """Extract structured entities when content is long enough."""
        if not content or len(content) <= MIN_CONTENT_LENGTH:
            return None

        if self._llm is None:
            logger.warning("Knowledge extraction skipped: LLM client not configured")
            return None

        try:
            prompt = EXTRACTION_PROMPT.format(content=content)
            raw_text = (await self._llm.ainvoke(prompt)).strip()
            raw_text = self._strip_code_fence(raw_text)
            result = json.loads(raw_text)
            return self._validate_result(result)
        except json.JSONDecodeError as exc:
            logger.warning("Knowledge extraction JSON parse failed: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Knowledge extraction LLM call failed (skipped): %s", exc)
            return None

    def records_from_extraction(
        self,
        diary_id: str,
        extraction: ExtractionResult,
        *,
        extracted_at: datetime | None = None,
    ) -> list[EntityRecord]:
        """Convert an extraction result into ``EntityRecord`` rows."""
        timestamp = extracted_at or datetime.now(UTC)
        records: list[EntityRecord] = []

        if extraction["persons"]:
            records.append(
                EntityRecord(
                    entity_type=EntityType.PERSON,
                    entity_data=json.dumps(extraction["persons"], ensure_ascii=False),
                    diary_id=diary_id,
                    extracted_at=timestamp,
                )
            )

        if extraction["events"]:
            records.append(
                EntityRecord(
                    entity_type=EntityType.EVENT,
                    entity_data=json.dumps(extraction["events"], ensure_ascii=False),
                    diary_id=diary_id,
                    extracted_at=timestamp,
                )
            )

        if extraction["places"]:
            records.append(
                EntityRecord(
                    entity_type=EntityType.PLACE,
                    entity_data=json.dumps(extraction["places"], ensure_ascii=False),
                    diary_id=diary_id,
                    extracted_at=timestamp,
                )
            )

        if extraction["topics"]:
            records.append(
                EntityRecord(
                    entity_type=EntityType.TOPIC,
                    entity_data=json.dumps(extraction["topics"], ensure_ascii=False),
                    diary_id=diary_id,
                    extracted_at=timestamp,
                )
            )

        mood_score = extraction["mood_score"]
        if mood_score != 0.0:
            records.append(
                EntityRecord(
                    entity_type=EntityType.MOOD,
                    entity_data=json.dumps({"mood_score": mood_score}, ensure_ascii=False),
                    diary_id=diary_id,
                    extracted_at=timestamp,
                )
            )

        return records

    @staticmethod
    def _strip_code_fence(raw_text: str) -> str:
        if not raw_text.startswith("```"):
            return raw_text
        lines = [line for line in raw_text.split("\n") if not line.strip().startswith("```")]
        return "\n".join(lines)

    def _validate_result(self, result: dict[str, Any]) -> ExtractionResult:
        validated: ExtractionResult = {
            "persons": [],
            "events": [],
            "places": [],
            "topics": [],
            "mood_score": 0.0,
        }

        if isinstance(result.get("persons"), list):
            for person in result["persons"]:
                if isinstance(person, dict) and person.get("name"):
                    validated["persons"].append(
                        {
                            "name": str(person.get("name", "")),
                            "relation": str(person.get("relation", "")),
                            "sentiment": float(person.get("sentiment", 0.0)),
                        }
                    )

        if isinstance(result.get("events"), list):
            for event in result["events"]:
                if isinstance(event, dict) and event.get("description"):
                    validated["events"].append(
                        {
                            "description": str(event.get("description", "")),
                            "inferred_date": str(event.get("inferred_date", "")),
                            "emotion": str(event.get("emotion", "")),
                        }
                    )

        if isinstance(result.get("places"), list):
            validated["places"] = [str(place) for place in result["places"] if place]

        if isinstance(result.get("topics"), list):
            validated["topics"] = [str(topic) for topic in result["topics"] if topic]

        try:
            score = float(result.get("mood_score", 0.0))
            validated["mood_score"] = max(-1.0, min(1.0, score))
        except (TypeError, ValueError):
            validated["mood_score"] = 0.0

        return validated

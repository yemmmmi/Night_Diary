"""Domain knowledge and entity extraction types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, TypedDict


class EntityType(StrEnum):
    """Structured entity types extracted from diary content.

    V1 DB migration comments listed only person/event/place/topic; the
    implementation also persisted ``mood``. All five are first-class here.
    """

    PERSON = "person"
    EVENT = "event"
    PLACE = "place"
    TOPIC = "topic"
    MOOD = "mood"


class KnowledgeCategory(StrEnum):
    """Psychology domain knowledge categories."""

    CBT = "cbt"
    MINDFULNESS = "mindfulness"
    SLEEP_HYGIENE = "sleep_hygiene"
    SOCIAL_SUPPORT = "social_support"
    EMOTION_REGULATION = "emotion_regulation"


class PersonEntity(TypedDict):
    name: str
    relation: str
    sentiment: float


class EventEntity(TypedDict):
    description: str
    inferred_date: str
    emotion: str


class ExtractionResult(TypedDict):
    persons: list[PersonEntity]
    events: list[EventEntity]
    places: list[str]
    topics: list[str]
    mood_score: float


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    """A single psychology domain knowledge retrieval result."""

    content: str
    category: str
    topic: str
    source: str
    distance: float | None
    doc_id: str
    reference_note: str = "【通用知识参考】"


@dataclass(frozen=True, slots=True)
class EntityRecord:
    """A structured entity extracted from a diary entry."""

    entity_type: EntityType
    entity_data: str
    diary_id: str
    extracted_at: datetime

    def parsed_data(self) -> Any:
        import json

        return json.loads(self.entity_data)

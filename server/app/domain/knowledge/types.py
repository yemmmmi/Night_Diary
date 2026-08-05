"""领域知识与实体提取类型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, TypedDict


class EntityType(StrEnum):
    """从日记内容中提取的结构化实体类型。

    V1 数据库迁移注释中仅列出了 person/event/place/topic；
    实现中还持久化了 ``mood``。此处五者均为一等公民。
    """

    PERSON = "person"
    EVENT = "event"
    PLACE = "place"
    TOPIC = "topic"
    MOOD = "mood"


class KnowledgeCategory(StrEnum):
    """心理学领域知识分类。"""

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
    """单条心理学领域知识检索结果。"""

    content: str
    category: str
    topic: str
    source: str
    distance: float | None
    doc_id: str
    reference_note: str = "【通用知识参考】"


@dataclass(frozen=True, slots=True)
class EntityRecord:
    """从日记条目中提取的结构化实体。"""

    entity_type: EntityType
    entity_data: str
    diary_id: str
    extracted_at: datetime

    def parsed_data(self) -> Any:
        import json

        return json.loads(self.entity_data)

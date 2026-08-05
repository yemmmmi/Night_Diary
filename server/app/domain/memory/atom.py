"""UnifiedMemoryAtom —— 记忆写入的通用中间表示。

三种内容来源（日记分析、记忆卡片、夜间谈话 / 聊天）在持久化到情景记忆之前，
都会产生一个 ``UnifiedMemoryAtom``。这确保了结构化字段
（tags、mood_score、emotions、entities）在进入情景存储的过程中得以保留，
长期记忆提升器（long-term promoter）可据此进行重复主题检测和画像丰富。

该 atom 并**不会**被直接持久化；它会被 :class:`MemoryGateway` 转换为
:class:`EpisodicEntry`（后者已扩展出相同的结构化字段）。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["diary", "card", "chat"]


class EntityRef(BaseModel):
    """记忆原子中提到的人物、地点或主题。"""

    name: str
    entity_type: str = "person"  # person / place / topic / event
    relation: str = ""  # e.g. "同事", "妈妈"
    sentiment: float = 0.0


class UnifiedMemoryAtom(BaseModel):
    """来自三种内容来源的统一记忆表示。

    字段设计为无损：来源（card、diary、chat）上可用的任何信息都会在此保留，
    以便长期记忆提升器和下游 agent 能使用结构化数据而非原始文本。
    """

    source: Source = "diary"
    event_summary: str = ""
    emotion: str = "neutral"
    emotions: list[str] = Field(default_factory=list)
    mood_score: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    reply_insight: str = ""
    entities: list[EntityRef] = Field(default_factory=list)
    event_date: date | None = None
    diary_id: int | None = None
    conversation_id: str | None = None
    user_id: str = "default"

    def to_episodic_entry(self, timestamp: float) -> EpisodicEntryShim:
        """转换为与 EpisodicEntry 兼容的 dict，供 MemoryGateway 使用。

        返回的 dict 可被展开为 ``EpisodicEntry(**dict)``，
        其中包含扩展字段（tags、mood_score、event_date）。
        """
        return EpisodicEntryShim(
            event_summary=self.event_summary[:120],
            emotion=self.emotion,
            reply_insight=self.reply_insight[:200],
            source=self.source,
            timestamp=timestamp,
            diary_ids=[str(self.diary_id)] if self.diary_id else [],
            importance=self.importance,
            entry_id="",
            tags=self.tags,
            mood_score=self.mood_score,
            event_date=self.event_date.isoformat() if self.event_date else None,
            emotions=self.emotions,
        )


class EpisodicEntryShim(BaseModel):
    """与扩展后的 EpisodicEntry 字段匹配的中间模型。

    它的存在是为了避免 ``atom.py`` 与 ``types.py`` 之间出现循环导入。
    MemoryGateway 会直接读取这些字段。
    """

    event_summary: str
    emotion: str
    reply_insight: str
    source: str = "diary"
    timestamp: float
    diary_ids: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    entry_id: str = ""
    tags: list[str] = Field(default_factory=list)
    mood_score: float = Field(default=0.5, ge=0.0, le=1.0)
    event_date: str | None = None
    emotions: list[str] = Field(default_factory=list)


__all__ = ["EntityRef", "EpisodicEntryShim", "Source", "UnifiedMemoryAtom"]

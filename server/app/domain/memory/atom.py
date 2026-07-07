"""UnifiedMemoryAtom — the common intermediate representation for memory writes.

All three content sources (diary analysis, memory cards, night talk / chat)
produce a ``UnifiedMemoryAtom`` before persisting to episodic memory.  This
ensures structured fields (tags, mood_score, emotions, entities) survive the
journey into episodic storage, where the long-term promoter can use them for
recurring-topic detection and profile enrichment.

The atom is **not** persisted directly; it is converted to an
:class:`EpisodicEntry` (which has been extended with the same structured
fields) by :class:`MemoryGateway`.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["diary", "card", "chat", "image"]


class EntityRef(BaseModel):
    """A person, place, or topic mentioned in the memory atom."""

    name: str
    entity_type: str = "person"  # person / place / topic / event
    relation: str = ""  # e.g. "同事", "妈妈"
    sentiment: float = 0.0


class UnifiedMemoryAtom(BaseModel):
    """Unified memory representation from all three content sources.

    Fields are designed to be loss-free: anything available on the source
    (card, diary, chat) is preserved here so the long-term promoter and
    downstream agents can use structured data instead of raw text.
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
        """Convert to EpisodicEntry-compatible dict for MemoryGateway.

        Returns a dict that can be unpacked into ``EpisodicEntry(**dict)``
        with the extended fields (tags, mood_score, event_date).
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
    """Intermediate model matching the extended EpisodicEntry fields.

    This exists to avoid circular imports between ``atom.py`` and
    ``types.py``.  The MemoryGateway reads these fields directly.
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

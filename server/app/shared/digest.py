"""DiaryDigest — structured per-day digest for scene-2 fast comprehension.

Produced by scene 1's "tree-hole" pipeline and stored per ``(user_id, date)``
in ``daily_digests.digest_json``. Scene 2 reads it to understand a referenced
day **without reading the full diary content**.

Two recording modes are unified here:

- **Card mode** (记一笔): the user-authored cards are already structured
  (emotion / emotions / mood / tags / short summary). They map directly to
  the ``cards`` section — zero LLM cost, zero extraction error.
- **Typed diary mode**: a router decides ``basic`` vs ``complex``; the
  complex template carries richer fields (key events, emotional shifts,
  relationships, conflicts, concerns, temporal refs) so semantics are
  harder to miss.

``temporal_refs`` is intentionally separate from ``key_events``:
``key_events`` are what happened *that day*; ``temporal_refs`` capture
mentions of *other days* (past memories / future plans) so scene 2 can
attribute each fact to the correct day without reading the source text.
"""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, Field

DigestType = Literal["basic", "complex"]
DigestSource = Literal["card", "llm", "card+llm"]
TemporalDirection = Literal["past", "future"]


class TemporalRef(BaseModel):
    """A mention of something that happened (or will happen) on another day."""

    direction: TemporalDirection = "past"
    summary: str = ""
    date_hint: str = ""  # e.g. "昨天" / "上周" / "下周五"


class DigestEntity(BaseModel):
    """A person / place / topic mentioned in the diary."""

    name: str
    entity_type: str = "person"  # person / place / topic / event
    relation: str = ""
    sentiment: float = 0.0


class CardDigest(BaseModel):
    """Structured fields of one memory card (user-authored, direct mapping)."""

    emotion: str = "neutral"
    emotions: list[str] = Field(default_factory=list)
    mood: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    summary: str = ""


class DiaryDigestPart(BaseModel):
    """The typed-diary section of the digest (LLM or rule extraction).

    Basic template: intent / emotion / mood / tags / topics / entities /
    summary / temporal_refs. Complex template additionally fills
    key_events / emotional_shifts / relationships / conflicts / concerns.
    """

    intent: str = ""
    intent_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    emotion: str = "neutral"
    emotion_score: float = 0.0
    mood: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[DigestEntity] = Field(default_factory=list)
    summary: str = ""
    temporal_refs: list[TemporalRef] = Field(default_factory=list)
    # ── complex-only ──
    key_events: list[str] = Field(default_factory=list)
    emotional_shifts: list[str] = Field(default_factory=list)
    relationships: list[DigestEntity] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class DiaryDigest(BaseModel):
    """Full per-day digest: card section + diary section (versioned, tolerant).

    Unknown fields in stored JSON are preserved by Pydantic's default
    ``extra`` handling on serialization round-trips is lossy for unknown
    keys; callers should treat this as the canonical shape and any legacy
    rows without a digest fall back to full-text rendering in scene 2.
    """

    v: int = 1
    digest_type: DigestType = "basic"
    # NOTE: qualified ``datetime.date`` — an unqualified ``date`` annotation
    # on a field named ``date`` fails to resolve (``date`` evaluates to
    # ``None``) in this Python 3.11 environment.
    date: datetime.date | None = None
    source: DigestSource = "card"
    cards: list[CardDigest] = Field(default_factory=list)
    diary: DiaryDigestPart = Field(default_factory=DiaryDigestPart)
    updated_at: str = ""


__all__ = [
    "CardDigest",
    "DiaryDigest",
    "DiaryDigestPart",
    "DigestEntity",
    "DigestSource",
    "DigestType",
    "TemporalDirection",
    "TemporalRef",
]

"""Domain types for the three-layer memory system."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict

from pydantic import BaseModel, Field, model_validator


class EpisodicEntry(BaseModel):
    """A single episodic memory item derived from a diary analysis turn.

    Extended with structured fields (tags, mood_score, emotions, event_date)
    so the long-term promoter can use them for recurring-topic detection
    instead of raw text matching.

    Backward compatibility: old payloads stored ``event`` instead of
    ``event_summary`` and omitted ``reply_insight``. A ``model_validator``
    maps legacy keys so deserialization never fails on old data.
    """

    event_summary: str
    emotion: str
    reply_insight: str
    source: str = "diary"
    timestamp: float
    diary_ids: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    entry_id: str = ""
    # ── Structured fields (P2-2 UnifiedMemoryAtom) ──
    tags: list[str] = Field(default_factory=list)
    mood_score: float = Field(default=0.5, ge=0.0, le=1.0)
    emotions: list[str] = Field(default_factory=list)
    event_date: str | None = None  # ISO date string (YYYY-MM-DD)

    @model_validator(mode="before")
    @classmethod
    def _compat_legacy_fields(cls, data: Any) -> Any:
        """Map legacy field names so old JSON payloads still deserialize.

        - ``event`` → ``event_summary`` (renamed in P2-2)
        - ``reply_insight`` defaults to ``""`` if missing (added in Phase 2)
        - ``insight`` → ``reply_insight`` (very old name)
        """
        if isinstance(data, dict):
            # event → event_summary
            if "event_summary" not in data and "event" in data:
                data["event_summary"] = data.pop("event")
            # reply_insight default
            if "reply_insight" not in data:
                data["reply_insight"] = data.get("insight", "")
        return data


class EmotionBaseline(BaseModel):
    average_sentiment: float = 0.0
    volatility: float = 0.0
    dominant_emotion: str = "neutral"


class ImportantPerson(BaseModel):
    name: str
    relation: str
    sentiment: float = 0.0


class UserProfile(BaseModel):
    """Long-term user profile persisted as JSON."""

    personality_tags: list[str] = Field(default_factory=list)
    emotion_baseline: EmotionBaseline = Field(default_factory=EmotionBaseline)
    important_people: list[ImportantPerson] = Field(default_factory=list)
    recurring_topics: list[str] = Field(default_factory=list)
    preferred_response_style: str = "empathetic"


class WorkingContext(TypedDict, total=False):
    """Session-level working memory state for a single diary analysis."""

    diary_id: str
    diary_content: str
    user_profile: dict[str, Any]
    episodic_context: list[dict[str, Any]]
    long_term_profile: dict[str, Any]
    retrieval_context: str
    empathy_response: str
    insight_response: str
    compressed_history: str
    final_response: str
    turn: int
    total_tokens_used: int


class EpisodicMemoryStore(Protocol):
    """Persistence port for episodic memory entries."""

    def load_entries(self, user_id: str) -> list[EpisodicEntry]: ...

    def upsert_entry(self, user_id: str, entry: EpisodicEntry) -> None: ...

    def delete_entries(self, user_id: str, entry_ids: list[str]) -> None: ...


class LongTermProfileStore(Protocol):
    """Persistence port for long-term user profiles."""

    def get_profile(self, user_id: str) -> UserProfile | None: ...

    def save_profile(self, user_id: str, profile: UserProfile) -> None: ...

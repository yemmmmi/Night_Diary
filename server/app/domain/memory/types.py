"""Domain types for the three-layer memory system."""

from __future__ import annotations

from collections import Counter
from typing import Any, ClassVar, Protocol, TypedDict

from pydantic import BaseModel, Field, model_validator

#: Maximum length of the user-authored 「关于我」 text (B2). Shared by the storage
#: layer, the frozen-block builder, and the API schema so the limit has one home.
MAX_ABOUT_CHARS = 600


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
    # ── P0-C: entities mentioned in this event (serialized EntityRef dicts:
    # name / entity_type / relation / sentiment). Populated by the entity
    # extraction sidecar via MemoryGateway.attach_entities; the long-term
    # promoter aggregates person entities into profile.important_people.
    entities: list[dict[str, Any]] = Field(default_factory=list)
    # ── B3: provenance — the chat message that produced this entry ──
    # Lets a conversation rollback undo the memory writes of the removed turn.
    source_message_id: str | None = None
    # ── P2-A: chat sessions that produced this entry (entity sidecar joins on
    # these when diary_ids / source_message_id don't match) ──
    conversation_ids: list[str] = Field(default_factory=list)
    # ── V3 P4: vector for retrieval (lazy-computed by EpisodicMemory) ──
    embedding: list[float] | None = None

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


class ShortTermState(BaseModel):
    """Rolling window of the user's recent daily modes & mood (P1-A).

    Fed back from MoodMonitor's ``daily_modes`` rows so agents can perceive
    the user's *recent* state (as opposed to ``EmotionBaseline``, which is the
    long-run personality). Refreshed at most once a day per user.
    """

    #: Oldest → newest mode keys over the window (daily/followup/introspection).
    recent_modes: list[str] = Field(default_factory=list)
    #: Windowed mean of daily mood signals, [0, 1] (0.5 = neutral).
    composite_mood: float = Field(default=0.5, ge=0.0, le=1.0)
    #: Total mood samples behind ``composite_mood`` (confidence indicator).
    samples: int = 0
    #: ISO date (YYYY-MM-DD) of the last refresh — the daily churn guard.
    updated_date: str = ""

    #: User-facing labels for the internal mode keys.
    MODE_LABELS: ClassVar[dict[str, str]] = {
        "daily": "日常",
        "followup": "跟进",
        "introspection": "内视",
    }

    def render(self) -> str:
        """Compact rendering for prompt contexts (frozen block, agent profile).

        Empty string when there is nothing meaningful to say — callers skip
        the line entirely in that case.
        """
        modes = [self.MODE_LABELS.get(mode, mode) for mode in self.recent_modes]
        parts: list[str] = []

        if self.samples > 0:
            if self.composite_mood < 0.35:
                mood_desc = "情绪偏低"
            elif self.composite_mood > 0.65:
                mood_desc = "情绪偏暖"
            else:
                mood_desc = "情绪平稳"
            days = len(modes) or 1
            parts.append(f"近{days}天{mood_desc}（均值{self.composite_mood:.2f}）")

        if modes:
            counts: Counter[str] = Counter(modes)
            dominant, occurrences = counts.most_common(1)[0]
            if len(counts) == 1:
                parts.append(f"持续{dominant}模式（{len(modes)}天）")
            else:
                parts.append(f"模式多为{dominant}（{occurrences}/{len(modes)}天）")

        return "、".join(parts)


class UserProfile(BaseModel):
    """Long-term user profile persisted as JSON."""

    personality_tags: list[str] = Field(default_factory=list)
    emotion_baseline: EmotionBaseline = Field(default_factory=EmotionBaseline)
    important_people: list[ImportantPerson] = Field(default_factory=list)
    recurring_topics: list[str] = Field(default_factory=list)
    preferred_response_style: str = "empathetic"
    #: Recent-state section (P1-A) — see :class:`ShortTermState`.
    short_term_state: ShortTermState = Field(default_factory=ShortTermState)


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


class ProfileChangeLogStore(Protocol):
    """Persistence port for the field-level profile change audit log (P1-B).

    One ``record_change`` call = one changed profile field. Values are plain
    JSON-serializable objects (strings / lists / dicts); the implementation
    serializes them for storage. ``evidence`` carries the memory pairs the
    change was derived from (promotion inputs), when available.
    """

    def record_change(
        self,
        user_id: str,
        *,
        field: str,
        old_value: Any,
        new_value: Any,
        source: str,
        evidence: list[dict[str, Any]] | None = None,
    ) -> None: ...

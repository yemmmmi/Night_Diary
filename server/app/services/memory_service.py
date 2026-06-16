"""Read-only access to the agent's persisted memory layers.

The three-layer memory system is: working (session-only, not exposed here),
**episodic** (event trail, cards sink here) and **long-term** (the user
profile). This service reads the two *durable* layers straight from their
SQLite stores so the Memory Library page can visualise everything that was
ever persisted — without the in-process decay/threshold filtering that the
live :class:`EpisodicMemory` deque applies during retrieval.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.infrastructure.memory_repository import (
    SqliteEpisodicMemoryStore,
    SqliteLongTermProfileStore,
)
from app.infrastructure.models.memory_card import MemoryCardRow

if TYPE_CHECKING:
    from app.domain.memory.types import EpisodicEntry, UserProfile
    from app.services.container import ServiceContainer

DEFAULT_USER_ID = "default"


def _entry_source(entry: EpisodicEntry) -> str:
    """Classify an episodic entry as coming from a diary analysis or a card.

    Cards sink into episodic memory with an empty ``ai_suggestion`` and no
    linked diary; diary analysis turns carry a suggestion and/or diary ids.
    """
    if entry.ai_suggestion.strip() or entry.diary_ids:
        return "diary"
    return "card"


def _entry_to_dict(entry: EpisodicEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "event": entry.event,
        "emotion": entry.emotion,
        "ai_suggestion": entry.ai_suggestion,
        "user_feedback": entry.user_feedback,
        "importance": entry.importance,
        "timestamp": entry.timestamp,
        "diary_ids": list(entry.diary_ids),
        "source": _entry_source(entry),
    }


def list_episodic(container: ServiceContainer) -> list[dict[str, Any]]:
    """Return every persisted episodic entry, newest first."""
    store = SqliteEpisodicMemoryStore(container.session_factory)
    entries = store.load_entries(DEFAULT_USER_ID)
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return [_entry_to_dict(entry) for entry in entries]


def _profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    return {
        "personality_tags": list(profile.personality_tags),
        "emotion_baseline": {
            "average_sentiment": profile.emotion_baseline.average_sentiment,
            "volatility": profile.emotion_baseline.volatility,
            "dominant_emotion": profile.emotion_baseline.dominant_emotion,
        },
        "important_people": [
            {
                "name": p.name,
                "relation": p.relation,
                "sentiment": p.sentiment,
            }
            for p in profile.important_people
        ],
        "recurring_topics": list(profile.recurring_topics),
        "preferred_response_style": profile.preferred_response_style,
    }


def get_profile(container: ServiceContainer) -> dict[str, Any] | None:
    """Return the long-term user profile, or ``None`` if not built yet."""
    store = SqliteLongTermProfileStore(container.session_factory)
    profile = store.get_profile(DEFAULT_USER_ID)
    if profile is None:
        return None
    return _profile_to_dict(profile)


def get_overview(container: ServiceContainer) -> dict[str, Any]:
    """Return counts summarising the durable memory layers."""
    store = SqliteEpisodicMemoryStore(container.session_factory)
    entries = store.load_entries(DEFAULT_USER_ID)
    episodic_total = len(entries)
    from_cards = sum(1 for e in entries if _entry_source(e) == "card")
    from_diaries = episodic_total - from_cards

    with container.session_factory() as session:
        card_total = session.query(MemoryCardRow).count()

    profile = get_profile(container)

    return {
        "episodic_total": episodic_total,
        "episodic_from_cards": from_cards,
        "episodic_from_diaries": from_diaries,
        "card_total": card_total,
        "profile_built": profile is not None,
    }

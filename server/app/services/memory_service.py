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
    """Classify an episodic entry by its source field."""
    return entry.source


def _entry_to_dict(entry: EpisodicEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "event_summary": entry.event_summary,
        "emotion": entry.emotion,
        "reply_insight": entry.reply_insight,
        "importance": entry.importance,
        "timestamp": entry.timestamp,
        "diary_ids": list(entry.diary_ids),
        "source": _entry_source(entry),
        "tags": list(entry.tags),
        "mood_score": entry.mood_score,
        "emotions": list(entry.emotions),
        "event_date": entry.event_date,
    }


def list_episodic(
    container: ServiceContainer, *, user_id: str = DEFAULT_USER_ID
) -> list[dict[str, Any]]:
    """Return every persisted episodic entry, newest first."""
    store = SqliteEpisodicMemoryStore(container.session_factory)
    entries = store.load_entries(user_id)
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return [_entry_to_dict(entry) for entry in entries]


def _sync_live_episodic(container: ServiceContainer) -> None:
    if container.episodic_memory is not None:
        container.episodic_memory.load()


def update_episodic(
    container: ServiceContainer,
    entry_id: str,
    *,
    event_summary: str | None = None,
    emotion: str | None = None,
    reply_insight: str | None = None,
    importance: float | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    """Update a persisted episodic entry."""
    from app.shared.errors import NotFoundError

    store = SqliteEpisodicMemoryStore(container.session_factory)
    entry = store.get_entry(user_id, entry_id)
    if entry is None:
        raise NotFoundError(resource="情节记忆", resource_id=entry_id)

    updates: dict[str, Any] = {}
    if event_summary is not None:
        updates["event_summary"] = event_summary
    if emotion is not None:
        updates["emotion"] = emotion
    if reply_insight is not None:
        updates["reply_insight"] = reply_insight
    if importance is not None:
        updates["importance"] = importance

    if not updates:
        return _entry_to_dict(entry)

    updated = entry.model_copy(update=updates)
    store.upsert_entry(user_id, updated)
    _sync_live_episodic(container)
    return _entry_to_dict(updated)


def delete_episodic(
    container: ServiceContainer,
    entry_id: str,
    *,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    """Delete a persisted episodic entry."""
    from app.shared.errors import NotFoundError

    store = SqliteEpisodicMemoryStore(container.session_factory)
    if store.get_entry(user_id, entry_id) is None:
        raise NotFoundError(resource="情节记忆", resource_id=entry_id)
    store.delete_entries(user_id, [entry_id])
    _sync_live_episodic(container)


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


def get_profile(
    container: ServiceContainer, *, user_id: str = DEFAULT_USER_ID
) -> dict[str, Any] | None:
    """Return the long-term user profile, or ``None`` if not built yet."""
    store = SqliteLongTermProfileStore(container.session_factory)
    profile = store.get_profile(user_id)
    if profile is None:
        return None
    return _profile_to_dict(profile)


def get_overview(container: ServiceContainer, *, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    """Return counts summarising the durable memory layers."""
    store = SqliteEpisodicMemoryStore(container.session_factory)
    entries = store.load_entries(user_id)
    episodic_total = len(entries)
    from_cards = sum(1 for e in entries if _entry_source(e) == "card")
    from_diaries = episodic_total - from_cards

    with container.session_factory() as session:
        card_total = session.query(MemoryCardRow).filter(MemoryCardRow.user_id == user_id).count()

    profile = get_profile(container, user_id=user_id)

    return {
        "episodic_total": episodic_total,
        "episodic_from_cards": from_cards,
        "episodic_from_diaries": from_diaries,
        "card_total": card_total,
        "profile_built": profile is not None,
    }

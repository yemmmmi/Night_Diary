"""JSON export/import service for full user data migration.

Exports diary entries (with legacy mood tags + analyses), memory cards, episodic
memories, and long-term profile as a single JSON blob.  Import clears existing
data and rebuilds from the JSON, including ChromaDB vector sync for each diary
entry.  Legacy ``tags`` / ``tag_ids`` fields are preserved for old backups only;
new writes no longer create diary mood tags.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.infrastructure.models.analysis import AnalysisRow
from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.memory import EpisodicMemoryRow, LongTermProfileRow
from app.infrastructure.models.memory_card import MemoryCardRow
from app.infrastructure.models.tag import TagRow, diary_tag_association
from app.services import diary_service

if TYPE_CHECKING:
    from app.domain.rag.collections import DiaryCollectionManager

logger = logging.getLogger(__name__)

EXPORT_VERSION = 1


def export_all(db: Session, *, user_id: str) -> dict[str, Any]:
    """Export all user data as a JSON-serialisable dict."""
    user_diary_ids = db.query(DiaryEntryRow.id).filter(DiaryEntryRow.user_id == user_id)
    diaries = (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.user_id == user_id)
        .order_by(DiaryEntryRow.id)
        .all()
    )
    tags = (
        db.query(TagRow)
        .filter(TagRow.user_id == user_id)
        .order_by(TagRow.id)
        .all()
    )
    analyses = (
        db.query(AnalysisRow)
        .filter(AnalysisRow.diary_id.in_(user_diary_ids))
        .order_by(AnalysisRow.id)
        .all()
    )
    cards = (
        db.query(MemoryCardRow)
        .filter(MemoryCardRow.user_id == user_id)
        .order_by(MemoryCardRow.created_at)
        .all()
    )
    episodic = (
        db.query(EpisodicMemoryRow)
        .filter(EpisodicMemoryRow.user_id == user_id)
        .order_by(EpisodicMemoryRow.timestamp)
        .all()
    )
    profiles = (
        db.query(LongTermProfileRow)
        .filter(LongTermProfileRow.user_id == user_id)
        .all()
    )

    return {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "diaries": [
            {
                "id": d.id,
                "content": d.content,
                "date": d.date.isoformat() if d.date else None,
                "weather": d.weather,
                "reply": d.reply,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "tag_ids": [t.id for t in d.tags],
            }
            for d in diaries
        ],
        "tags": [
            {
                "id": t.id,
                "name": t.name,
                "color": t.color,
                "usage_count": t.usage_count,
            }
            for t in tags
        ],
        "analyses": [
            {
                "diary_id": a.diary_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "token_cost": a.token_cost,
                "cache_hit_tokens": a.cache_hit_tokens,
                "cache_miss_tokens": a.cache_miss_tokens,
                "output_tokens": a.output_tokens,
                "log": a.log,
                "diary_length": a.diary_length,
                "agent_mode": a.agent_mode,
                "execution_tier": a.execution_tier,
                "activated_agents": a.activated_agents,
            }
            for a in analyses
        ],
        "memory_cards": [
            {
                "card_id": c.card_id,
                "emotion": c.emotion,
                "emotions_json": c.emotions_json,
                "event_summary": c.event_summary,
                "mood_score": c.mood_score,
                "tags_json": c.tags_json,
                "importance": c.importance,
                "card_type": c.card_type,
                "diary_id": c.diary_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in cards
        ],
        "episodic_memories": [
            {
                "entry_id": e.entry_id,
                "user_id": e.user_id,
                "timestamp": e.timestamp,
                "importance": e.importance,
                "payload_json": e.payload_json,
            }
            for e in episodic
        ],
        "long_term_profile": (
            {
                "user_id": profiles[0].user_id,
                "profile_json": profiles[0].profile_json,
                "updated_at": profiles[0].updated_at,
            }
            if profiles
            else None
        ),
    }


def import_all(
    db: Session,
    data: dict[str, Any],
    collection_manager: DiaryCollectionManager | None = None,
    *,
    user_id: str,
) -> dict[str, int]:
    """Import user data from a JSON dict, replacing all existing data.

    Returns a summary dict with counts of imported items.
    """
    version = data.get("version", 0)
    if version != EXPORT_VERSION:
        raise ValueError(f"Unsupported export version: {version}, expected {EXPORT_VERSION}")

    # --- Clear existing data (scoped to current user) ---
    db.query(AnalysisRow).filter(
        AnalysisRow.diary_id.in_(
            db.query(DiaryEntryRow.id).filter(DiaryEntryRow.user_id == user_id)
        )
    ).delete(synchronize_session=False)
    db.query(MemoryCardRow).filter(
        MemoryCardRow.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(EpisodicMemoryRow).filter(
        EpisodicMemoryRow.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(LongTermProfileRow).filter(
        LongTermProfileRow.user_id == user_id
    ).delete(synchronize_session=False)
    db.execute(
        diary_tag_association.delete().where(
            diary_tag_association.c.diary_id.in_(
                db.query(DiaryEntryRow.id).filter(DiaryEntryRow.user_id == user_id)
            )
        )
    )
    db.query(DiaryEntryRow).filter(
        DiaryEntryRow.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(TagRow).filter(
        TagRow.user_id == user_id
    ).delete(synchronize_session=False)
    db.commit()

    # --- Import tags (track old_id -> new_id) ---
    tag_id_map: dict[int, int] = {}
    for tag_data in data.get("tags", []):
        old_id = tag_data["id"]
        tag = TagRow(
            name=tag_data["name"],
            color=tag_data.get("color", "#6B7280"),
            usage_count=tag_data.get("usage_count", 0),
            user_id=user_id,
        )
        db.add(tag)
        db.flush()  # get new ID
        tag_id_map[old_id] = tag.id
    db.commit()

    # --- Import diaries (track old_id -> new_id, sync to ChromaDB) ---
    diary_id_map: dict[int, int] = {}
    for diary_data in data.get("diaries", []):
        old_id = diary_data["id"]
        old_tag_ids = diary_data.get("tag_ids", [])
        new_tag_ids = [tag_id_map[t] for t in old_tag_ids if t in tag_id_map]

        entry = diary_service.create_entry(
            db,
            user_id=user_id,
            content=diary_data["content"] or "",
            entry_date=_parse_date(diary_data.get("date")),
            weather=diary_data.get("weather"),
            collection_manager=collection_manager,
        )
        if new_tag_ids:
            tags = db.query(TagRow).filter(
                TagRow.id.in_(new_tag_ids), TagRow.user_id == user_id
            ).all()
            entry.tags = tags
        # Overwrite auto-generated fields with original values
        entry.reply = diary_data.get("reply")
        if created_at := _parse_datetime(diary_data.get("created_at")):
            entry.created_at = created_at
        db.commit()
        db.refresh(entry)
        diary_id_map[old_id] = entry.id

    # --- Import analyses (map diary_id) ---
    for analysis_data in data.get("analyses", []):
        old_diary_id = analysis_data["diary_id"]
        new_diary_id = diary_id_map.get(old_diary_id)
        if new_diary_id is None:
            continue  # analysis without diary — skip
        analysis = AnalysisRow(
            diary_id=new_diary_id,
            token_cost=analysis_data.get("token_cost"),
            cache_hit_tokens=analysis_data.get("cache_hit_tokens"),
            cache_miss_tokens=analysis_data.get("cache_miss_tokens"),
            output_tokens=analysis_data.get("output_tokens"),
            log=analysis_data.get("log"),
            diary_length=analysis_data.get("diary_length"),
            agent_mode=analysis_data.get("agent_mode"),
            execution_tier=analysis_data.get("execution_tier"),
            activated_agents=analysis_data.get("activated_agents"),
        )
        if created_at := _parse_datetime(analysis_data.get("created_at")):
            analysis.created_at = created_at
        db.add(analysis)
    db.commit()

    # --- Import memory cards (map diary_id if exists) ---
    for card_data in data.get("memory_cards", []):
        old_diary_id = card_data.get("diary_id")
        new_diary_id = diary_id_map.get(old_diary_id) if old_diary_id else None
        card = MemoryCardRow(
            card_id=card_data["card_id"],
            emotion=card_data.get("emotion", "neutral"),
            emotions_json=card_data.get("emotions_json"),
            event_summary=card_data.get("event_summary"),
            mood_score=card_data.get("mood_score", 0.5),
            tags_json=card_data.get("tags_json"),
            importance=card_data.get("importance", 0.5),
            card_type=card_data.get("card_type", "standard"),
            diary_id=new_diary_id,
            user_id=user_id,
        )
        if created_at := _parse_datetime(card_data.get("created_at")):
            card.created_at = created_at
        db.add(card)
    db.commit()

    # --- Import episodic memories ---
    for ep_data in data.get("episodic_memories", []):
        ep = EpisodicMemoryRow(
            entry_id=ep_data["entry_id"],
            user_id=user_id,
            timestamp=ep_data.get("timestamp", 0.0),
            importance=ep_data.get("importance", 0.5),
            payload_json=ep_data.get("payload_json", "{}"),
        )
        db.add(ep)
    db.commit()

    # --- Import long-term profile ---
    profile_data = data.get("long_term_profile")
    if profile_data:
        profile = LongTermProfileRow(
            user_id=user_id,
            profile_json=profile_data.get("profile_json", "{}"),
            updated_at=profile_data.get("updated_at", 0.0),
        )
        db.add(profile)
        db.commit()

    return {
        "diaries": len(diary_id_map),
        "tags": len(tag_id_map),
        "analyses": len(data.get("analyses", [])),
        "memory_cards": len(data.get("memory_cards", [])),
        "episodic_memories": len(data.get("episodic_memories", [])),
        "long_term_profile": 1 if profile_data else 0,
    }


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _parse_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None

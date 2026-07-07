"""Content normalizer — unified entry point for converting all content forms to UnifiedMemoryAtom.

All three content sources (diary, card, chat/night-talk) produce a
``UnifiedMemoryAtom`` via this normalizer before persisting to episodic
memory. This ensures:

1. **Single conversion path**: new content types only need to implement
   ``from_<type>()``, all downstream consumers depend solely on
   ``UnifiedMemoryAtom``.
2. **Structured field preservation**: tags, mood_score, emotions, entities
   survive the journey into episodic storage.
3. **Consistent defaults**: emotion estimation and importance scoring are
   applied uniformly across all sources.

Usage::

    from app.services.normalizer import ContentNormalizer

    atom = ContentNormalizer.from_diary(entry)
    gw.persist_atom(atom)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.memory.atom import UnifiedMemoryAtom
from app.shared.emotion_estimator import get_emotion_estimator
from app.shared.pipeline_trace import trace_span

if TYPE_CHECKING:
    from app.infrastructure.models.diary_entry import DiaryEntryRow
    from app.infrastructure.models.memory_card import MemoryCardRow

logger = logging.getLogger(__name__)

#: Default importance for diary-derived episodic entries.
_DIARY_EPISODIC_IMPORTANCE = 0.6

#: Default importance for chat-derived episodic entries.
_CHAT_EPISODIC_IMPORTANCE = 0.5

#: Minimum emotion intensity (abs score) to trigger episodic write-back.
_EPISODIC_WRITE_THRESHOLD = 0.3


class ContentNormalizer:
    """Convert all content forms into UnifiedMemoryAtom.

    This is the single normalization layer that replaces ad-hoc conversions
    scattered across diary_service, card_service, and conversation_ai_service.
    """

    @staticmethod
    def from_diary(
        entry: DiaryEntryRow,
        *,
        reply: str = "",
        user_id: str = "default",
    ) -> UnifiedMemoryAtom:
        """Convert a DiaryEntryRow to a UnifiedMemoryAtom.

        Diary entries are unstructured text, so emotion/mood_score are
        estimated via EmotionEstimator. Tags come from the diary's tag
        associations if available.
        """
        with trace_span(
            "S1_normalize",
            "内容标准化",
            input_snapshot={"source": "diary", "diary_id": entry.id},
        ) as span:
            content = entry.content or ""
            estimate = get_emotion_estimator().estimate(content)
            score = get_emotion_estimator().score(content)

            event_summary = content.strip().replace("\n", " ")[:120]
            if len(content.strip()) > 120:
                event_summary += "…"

            tags: list[str] = []
            if hasattr(entry, "tags") and entry.tags:
                tags = [t.name for t in entry.tags if t.name]

            event_date = None
            if hasattr(entry, "created_at") and entry.created_at:
                event_date = entry.created_at.date() if hasattr(entry.created_at, "date") else None
            elif hasattr(entry, "date") and entry.date:
                event_date = entry.date

            atom = UnifiedMemoryAtom(
                source="diary",
                event_summary=event_summary,
                emotion=estimate.label,
                mood_score=max(0.0, min(1.0, 0.5 + score * 0.5)),
                tags=tags,
                importance=_DIARY_EPISODIC_IMPORTANCE,
                reply_insight=(reply or "")[:200],
                event_date=event_date,
                diary_id=entry.id,
                user_id=user_id,
            )
            if span:
                span.set_output(
                    {"emotion": atom.emotion, "mood_score": atom.mood_score}
                )
            return atom

    @staticmethod
    def from_card(
        card: MemoryCardRow,
        *,
        user_id: str = "default",
    ) -> UnifiedMemoryAtom:
        """Convert a MemoryCardRow to a UnifiedMemoryAtom.

        Cards are already structured (emotion, mood_score, tags), so they
        are mapped directly without estimation. Delegates to the existing
        ``card_to_unified_atom`` for backward compatibility.
        """
        from app.services.card_service import card_to_unified_atom

        return card_to_unified_atom(card, user_id=user_id)

    @staticmethod
    def from_conversation(
        content: str,
        *,
        reply_text: str = "",
        conversation_id: str = "",
        user_id: str = "default",
        emotion_label: str | None = None,
        emotion_score: float | None = None,
    ) -> UnifiedMemoryAtom:
        """Convert a conversation turn to a UnifiedMemoryAtom.

        Conversation messages are unstructured text, so emotion is estimated
        via EmotionEstimator unless explicitly provided.
        """
        with trace_span(
            "S1_normalize",
            "内容标准化",
            input_snapshot={"source": "chat", "conversation_id": conversation_id},
        ) as span:
            if emotion_label is None or emotion_score is None:
                estimator = get_emotion_estimator()
                estimate = estimator.estimate(content)
                emotion_label = estimate.label
                emotion_score = estimator.score(content)

            event_summary = content.strip().replace("\n", " ")[:120]
            if len(content.strip()) > 120:
                event_summary += "…"

            atom = UnifiedMemoryAtom(
                source="chat",
                event_summary=event_summary,
                emotion=emotion_label,
                mood_score=max(0.0, min(1.0, 0.5 + emotion_score * 0.5)),
                tags=["夜话"],
                importance=min(abs(emotion_score) + 0.3, 1.0),
                reply_insight=(reply_text or "")[:200],
                conversation_id=conversation_id or None,
                user_id=user_id,
            )
            if span:
                span.set_output(
                    {"emotion": atom.emotion, "mood_score": atom.mood_score}
                )
            return atom

    @staticmethod
    def from_image(
        asset: ImageAssetRow,
        *,
        user_id: str = "default",
        diary_id: int | None = None,
    ) -> UnifiedMemoryAtom:
        """Convert an ImageAssetRow to a UnifiedMemoryAtom.

        Image atoms carry the VLM-produced ``semantic_description`` as their
        ``event_summary`` (truncated) and ``source="image"`` for origin
        tracking. Emotion is estimated from the description so image-derived
        memories can participate in recurring-topic detection. Images attached
        to a diary inherit diary-level importance.
        """
        with trace_span(
            "S1_normalize",
            "内容标准化",
            input_snapshot={"source": "image", "asset_id": getattr(asset, "id", None)},
        ) as span:
            description = (asset.semantic_description or "").strip()
            estimate = get_emotion_estimator().estimate(description)
            score = get_emotion_estimator().score(description)

            event_summary = description.replace("\n", " ")[:120]
            if len(description) > 120:
                event_summary += "…"

            event_date = None
            if hasattr(asset, "created_at") and asset.created_at:
                event_date = (
                    asset.created_at.date() if hasattr(asset.created_at, "date") else None
                )

            atom = UnifiedMemoryAtom(
                source="image",
                event_summary=event_summary or "（图像记忆）",
                emotion=estimate.label,
                mood_score=max(0.0, min(1.0, 0.5 + score * 0.5)),
                tags=["图像"],
                importance=_DIARY_EPISODIC_IMPORTANCE,
                reply_insight="",
                event_date=event_date,
                diary_id=diary_id,
                user_id=user_id,
            )
            if span:
                span.set_output(
                    {"emotion": atom.emotion, "mood_score": atom.mood_score}
                )
            return atom

    @staticmethod
    def from_reply(
        reply_text: str,
        *,
        source_atom: UnifiedMemoryAtom,
        user_id: str = "default",
    ) -> UnifiedMemoryAtom:
        """Convert a generated reply to a UnifiedMemoryAtom.

        The reply inherits metadata from the source atom (diary_id,
        conversation_id, event_date) but has its own event_summary and
        source type appended.
        """
        return UnifiedMemoryAtom(
            source=source_atom.source,
            event_summary=reply_text.strip().replace("\n", " ")[:120],
            emotion=source_atom.emotion,
            mood_score=source_atom.mood_score,
            tags=source_atom.tags,
            importance=source_atom.importance,
            reply_insight=reply_text[:200],
            event_date=source_atom.event_date,
            diary_id=source_atom.diary_id,
            conversation_id=source_atom.conversation_id,
            user_id=user_id,
        )


__all__ = ["ContentNormalizer"]

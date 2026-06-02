"""Long-term memory — user profile JSON with episodic promotion rules."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime

from app.domain.memory.types import EpisodicEntry, LongTermProfileStore, UserProfile

logger = logging.getLogger(__name__)


class LongTermMemory:
    """Manage the persisted user profile and promote recurring themes."""

    PROMOTION_THRESHOLD_DAYS = 3

    def __init__(self, store: LongTermProfileStore | None = None) -> None:
        self._store = store

    def get_profile(self, user_id: str = "default") -> UserProfile:
        if self._store is None:
            return UserProfile()

        profile = self._store.get_profile(user_id)
        return profile if profile is not None else UserProfile()

    def update_profile(self, user_id: str, profile: UserProfile) -> None:
        if self._store is None:
            logger.warning("Long-term profile store unavailable; skip update user_id=%s", user_id)
            return

        old_profile = self.get_profile(user_id)
        self._store.save_profile(user_id, profile)
        self._log_profile_changes(user_id, old_profile, profile)

    def promote_from_episodic(
        self,
        user_id: str,
        episodic_entries: list[EpisodicEntry],
    ) -> None:
        """Promote emotions/topics that appear on 3+ consecutive days."""
        if not episodic_entries:
            logger.info("No episodic entries to promote for user_id=%s", user_id)
            return

        profile = self.get_profile(user_id)

        entries_by_date: dict[str, list[EpisodicEntry]] = {}
        for entry in episodic_entries:
            date_key = datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d")
            entries_by_date.setdefault(date_key, []).append(entry)

        daily_emotions: dict[str, set[str]] = {}
        daily_topics: dict[str, set[str]] = {}
        for date_key, entries in entries_by_date.items():
            daily_emotions[date_key] = {entry.emotion for entry in entries if entry.emotion}
            daily_topics[date_key] = {entry.event for entry in entries if entry.event}

        promoted_emotions = self._find_consecutive_items(
            daily_emotions,
            self.PROMOTION_THRESHOLD_DAYS,
        )
        promoted_topics = self._find_consecutive_items(
            daily_topics,
            self.PROMOTION_THRESHOLD_DAYS,
        )

        updated = False

        for topic in promoted_topics:
            if topic not in profile.recurring_topics:
                profile.recurring_topics.append(topic)
                logger.info(
                    "Promoted topic '%s' for user_id=%s after %d consecutive days",
                    topic,
                    user_id,
                    self.PROMOTION_THRESHOLD_DAYS,
                )
                updated = True

        if promoted_emotions:
            emotion_counts: Counter[str] = Counter()
            for emotions in daily_emotions.values():
                for emotion in emotions:
                    if emotion in promoted_emotions:
                        emotion_counts[emotion] += 1

            most_common_emotion = emotion_counts.most_common(1)[0][0]
            if profile.emotion_baseline.dominant_emotion != most_common_emotion:
                profile.emotion_baseline.dominant_emotion = most_common_emotion
                logger.info(
                    "Updated dominant emotion to '%s' for user_id=%s",
                    most_common_emotion,
                    user_id,
                )
                updated = True

        if updated:
            self.update_profile(user_id, profile)

    def _find_consecutive_items(
        self,
        daily_items: dict[str, set[str]],
        threshold: int,
    ) -> set[str]:
        if not daily_items:
            return set()

        sorted_dates = sorted(daily_items.keys())
        promoted: set[str] = set()
        all_items = {item for items in daily_items.values() for item in items}

        for item in all_items:
            consecutive_count = 0
            max_consecutive = 0
            prev_date: datetime | None = None

            for date_str in sorted_dates:
                current_date = datetime.strptime(date_str, "%Y-%m-%d")

                if item in daily_items[date_str]:
                    if prev_date is None or (current_date - prev_date).days == 1:
                        consecutive_count += 1
                    else:
                        consecutive_count = 1
                    max_consecutive = max(max_consecutive, consecutive_count)
                    prev_date = current_date
                else:
                    consecutive_count = 0
                    prev_date = None

            if max_consecutive >= threshold:
                promoted.add(item)

        return promoted

    def _log_profile_changes(
        self,
        user_id: str,
        old_profile: UserProfile,
        new_profile: UserProfile,
    ) -> None:
        changes: list[str] = []

        if old_profile.personality_tags != new_profile.personality_tags:
            changes.append(
                f"personality_tags: {old_profile.personality_tags} -> {new_profile.personality_tags}"
            )

        if old_profile.emotion_baseline != new_profile.emotion_baseline:
            changes.append(
                "emotion_baseline: "
                f"{old_profile.emotion_baseline.model_dump()} -> "
                f"{new_profile.emotion_baseline.model_dump()}"
            )

        if old_profile.important_people != new_profile.important_people:
            old_people = [person.model_dump() for person in old_profile.important_people]
            new_people = [person.model_dump() for person in new_profile.important_people]
            changes.append(f"important_people: {old_people} -> {new_people}")

        if old_profile.recurring_topics != new_profile.recurring_topics:
            changes.append(
                f"recurring_topics: {old_profile.recurring_topics} -> {new_profile.recurring_topics}"
            )

        if old_profile.preferred_response_style != new_profile.preferred_response_style:
            changes.append(
                "preferred_response_style: "
                f"{old_profile.preferred_response_style!r} -> "
                f"{new_profile.preferred_response_style!r}"
            )

        if changes:
            logger.info(
                "Long-term profile updated for user_id=%s:\n  %s",
                user_id,
                "\n  ".join(changes),
            )

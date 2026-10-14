"""Long-term memory — user profile JSON with episodic promotion rules."""

from __future__ import annotations

import logging
import statistics
from collections import Counter
from datetime import datetime

from app.domain.memory.types import EpisodicEntry, LongTermProfileStore, UserProfile

logger = logging.getLogger(__name__)


class LongTermMemory:
    """Manage the persisted user profile and promote recurring themes."""

    PROMOTION_THRESHOLD_DAYS = 3
    #: Rolling-window size (most recent N entries, by timestamp) for the
    #: emotion baseline. Keeps the baseline responsive to recent shifts.
    BASELINE_WINDOW_ENTRIES = 14
    #: Minimum entries in the window before average/volatility are estimable.
    BASELINE_MIN_ENTRIES = 3
    #: Minimum shift in average/volatility before a profile write is spent
    #: (avoids churn: every new entry nudges the rolling mean by a hair).
    BASELINE_UPDATE_TOLERANCE = 0.02

    def __init__(self, store: LongTermProfileStore | None = None) -> None:
        self._store = store

    def get_profile(self, user_id: str = "default") -> UserProfile:
        if self._store is None:
            return UserProfile()

        profile = self._store.get_profile(user_id)
        return profile if profile is not None else UserProfile()

    def _has_profile(self, user_id: str) -> bool:
        """Whether a real profile has actually been persisted in the store.

        Unlike ``get_profile`` (which always returns a non-None default),
        this returns True only when a real profile exists in the store.
        Used by ``promote_from_episodic`` to decide whether to force-save the
        first profile.
        """
        if self._store is None:
            return False
        return self._store.get_profile(user_id) is not None

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
        """Promote emotions / topics that appear on 3 or more consecutive days.

        Also (P0-B) activates the ``average_sentiment`` / ``volatility``
        baseline fields from the episodic ``mood_score`` sequence — these were
        previously dead defaults that insight/empathy agents kept reading.
        """
        if not episodic_entries:
            logger.info("No episodic entries to promote for user_id=%s", user_id)
            return

        profile = self.get_profile(user_id)
        had_profile = self._has_profile(user_id)

        entries_by_date: dict[str, list[EpisodicEntry]] = {}
        for entry in episodic_entries:
            # Prefer event_date (the user-specified diary date) over timestamp
            # (record creation time). timestamp always reflects "now", which
            # would make every entry look like it falls on the same day during
            # batch imports.
            if entry.event_date:
                date_key = entry.event_date
            else:
                date_key = datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d")
            entries_by_date.setdefault(date_key, []).append(entry)

        daily_emotions: dict[str, set[str]] = {}
        daily_topics: dict[str, set[str]] = {}
        for date_key, entries in entries_by_date.items():
            daily_emotions[date_key] = {entry.emotion for entry in entries if entry.emotion}
            # Use structured tags for topic detection (P2-2 fix).
            # Fall back to event_summary only when no tags are available.
            topics: set[str] = set()
            for entry in entries:
                if entry.tags:
                    topics.update(entry.tags)
                elif entry.event_summary:
                    topics.add(entry.event_summary[:30])
            daily_topics[date_key] = topics

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
            # Update when the dominant emotion changes, or when this is a new
            # profile that has not been persisted yet. Without this check, a new
            # profile whose default dominant_emotion ("neutral") matches the
            # promoted emotion would never be saved.
            if (
                profile.emotion_baseline.dominant_emotion != most_common_emotion
                or not had_profile
            ):
                profile.emotion_baseline.dominant_emotion = most_common_emotion
                logger.info(
                    "Updated dominant emotion to '%s' for user_id=%s",
                    most_common_emotion,
                    user_id,
                )
                updated = True

        if self._update_emotion_baseline(profile, episodic_entries):
            logger.info(
                "Updated emotion baseline for user_id=%s avg=%.2f vol=%.2f (window=%d)",
                user_id,
                profile.emotion_baseline.average_sentiment,
                profile.emotion_baseline.volatility,
                min(len(episodic_entries), self.BASELINE_WINDOW_ENTRIES),
            )
            updated = True

        if updated:
            self.update_profile(user_id, profile)

    def _update_emotion_baseline(
        self,
        profile: UserProfile,
        entries: list[EpisodicEntry],
    ) -> bool:
        """Roll the windowed emotion baseline from episodic ``mood_score`` (P0-B).

        ``mood_score`` lives in [0, 1] with 0.5 = neutral (see the normalizer:
        ``mood = 0.5 + sentiment * 0.5``). Map it back to the [-1, 1] sentiment
        scale the consumers assume — the empathy agent's crisis check compares
        against ``crisis_threshold = -0.7``, and the insight agent's deviation
        detector mixes the baseline with per-emotion scores of +/-0.6 x importance.

        Only ``average_sentiment`` and ``volatility`` are touched;
        ``dominant_emotion`` stays under the consecutive-days promotion rule.
        Returns True when the profile changed enough to justify a write.
        """
        recent = sorted(entries, key=lambda e: e.timestamp, reverse=True)
        window = recent[: self.BASELINE_WINDOW_ENTRIES]
        if len(window) < self.BASELINE_MIN_ENTRIES:
            return False

        sentiments = [entry.mood_score * 2.0 - 1.0 for entry in window]
        average = statistics.fmean(sentiments)
        volatility = statistics.pstdev(sentiments)

        baseline = profile.emotion_baseline
        if (
            abs(average - baseline.average_sentiment) < self.BASELINE_UPDATE_TOLERANCE
            and abs(volatility - baseline.volatility) < self.BASELINE_UPDATE_TOLERANCE
        ):
            return False

        baseline.average_sentiment = round(average, 4)
        baseline.volatility = round(volatility, 4)
        return True

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

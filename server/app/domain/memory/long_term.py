"""Long-term memory — user profile JSON with episodic promotion rules."""

from __future__ import annotations

import logging
import statistics
from collections import Counter
from datetime import datetime
from typing import Any

from app.domain.memory.types import (
    EpisodicEntry,
    ImportantPerson,
    LongTermProfileStore,
    ProfileChangeLogStore,
    UserProfile,
)

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
    #: Person-entity aggregation window (most recent N entries, P0-C).
    PEOPLE_WINDOW_ENTRIES = 30
    #: Mentions required before a person is promoted into important_people.
    PEOPLE_MIN_MENTIONS = 3
    #: Cap on important_people — keeps the frozen-block profile compact.
    PEOPLE_MAX = 5
    #: Sentiment drift (per person) below which no profile write is spent.
    PEOPLE_SENTIMENT_TOLERANCE = 0.05

    def __init__(
        self,
        store: LongTermProfileStore | None = None,
        change_log: ProfileChangeLogStore | None = None,
    ) -> None:
        self._store = store
        self._change_log = change_log

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

    def update_profile(
        self,
        user_id: str,
        profile: UserProfile,
        *,
        source: str = "manual",
        evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        """Persist ``profile`` and audit the field-level diff (P1-B).

        ``source`` marks the trigger: ``promotion`` (episodic promotion),
        ``mood_sync`` (P1-A short-term state refresh) or ``manual``
        (direct edits / defaults). ``evidence`` carries the memory pairs
        the change was derived from, when available.
        """
        if self._store is None:
            logger.warning("Long-term profile store unavailable; skip update user_id=%s", user_id)
            return

        old_profile = self.get_profile(user_id)
        self._store.save_profile(user_id, profile)
        self._record_profile_changes(user_id, old_profile, profile, source, evidence)

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

        if self._update_important_people(profile, episodic_entries):
            logger.info(
                "Updated important people for user_id=%s: %s",
                user_id,
                [p.name for p in profile.important_people],
            )
            updated = True

        if updated:
            self.update_profile(
                user_id,
                profile,
                source="promotion",
                evidence=self._promotion_evidence(episodic_entries),
            )

    def _promotion_evidence(
        self,
        entries: list[EpisodicEntry],
    ) -> list[dict[str, Any]]:
        """Lightweight (date, summary, emotion) pairs backing a promotion.

        Capped at the baseline window so the audit row stays compact even
        for large batch imports.
        """
        recent = sorted(entries, key=lambda e: e.timestamp, reverse=True)
        return [
            {
                "date": entry.event_date
                or datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d"),
                "summary": entry.event_summary[:80],
                "emotion": entry.emotion,
            }
            for entry in recent[: self.BASELINE_WINDOW_ENTRIES]
        ]

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

    def _update_important_people(
        self,
        profile: UserProfile,
        entries: list[EpisodicEntry],
    ) -> bool:
        """Aggregate person entities into ``important_people`` (P0-C).

        Person entities ride on episodic entries (attached by the extraction
        sidecar via ``MemoryGateway.attach_entities``). A person mentioned on
        at least ``PEOPLE_MIN_MENTIONS`` entries in the recent window is
        promoted with their most common relation label and mean sentiment
        ([-1, 1]). The list is recomputed from the window — people who fade
        out of recent entries fade out of the profile.

        Returns True when the list changed enough to justify a write.
        """
        recent = sorted(entries, key=lambda e: e.timestamp, reverse=True)
        window = recent[: self.PEOPLE_WINDOW_ENTRIES]

        stats: dict[str, dict[str, Any]] = {}
        for entry in window:
            for entity in entry.entities:
                if not isinstance(entity, dict):
                    continue
                if str(entity.get("entity_type", "")).lower() not in ("person", "人物", "people"):
                    continue
                name = str(entity.get("name", "")).strip()
                if not name:
                    continue
                stat = stats.setdefault(name, {"mentions": 0, "sentiments": [], "relations": Counter()})
                stat["mentions"] += 1
                try:
                    sentiment = float(entity.get("sentiment", 0.0))
                except (TypeError, ValueError):
                    sentiment = 0.0
                stat["sentiments"].append(max(-1.0, min(1.0, sentiment)))
                relation = str(entity.get("relation", "")).strip()
                if relation:
                    stat["relations"][relation] += 1

        people: list[tuple[str, int, str, float]] = []
        for name, stat in stats.items():
            if stat["mentions"] < self.PEOPLE_MIN_MENTIONS:
                continue
            relation = stat["relations"].most_common(1)[0][0] if stat["relations"] else ""
            average_sentiment = statistics.fmean(stat["sentiments"]) if stat["sentiments"] else 0.0
            people.append((name, stat["mentions"], relation, average_sentiment))

        # Deterministic order: most-mentioned first, then name.
        people.sort(key=lambda item: (-item[1], item[0]))
        people = people[: self.PEOPLE_MAX]

        new_list = [
            ImportantPerson(name=name, relation=relation, sentiment=round(sentiment, 4))
            for name, _, relation, sentiment in people
        ]
        if self._people_lists_equal(profile.important_people, new_list):
            return False

        profile.important_people = new_list
        return True

    def _people_lists_equal(
        self,
        old: list[ImportantPerson],
        new: list[ImportantPerson],
    ) -> bool:
        """Same people, same order, same relations, sentiments within tolerance."""
        if len(old) != len(new):
            return False
        for old_person, new_person in zip(old, new, strict=True):
            if old_person.name != new_person.name or old_person.relation != new_person.relation:
                return False
            if abs(old_person.sentiment - new_person.sentiment) >= self.PEOPLE_SENTIMENT_TOLERANCE:
                return False
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

    def _record_profile_changes(
        self,
        user_id: str,
        old_profile: UserProfile,
        new_profile: UserProfile,
        source: str,
        evidence: list[dict[str, Any]] | None,
    ) -> None:
        """Audit the field-level diff between two profile versions (P1-B).

        With a ``ProfileChangeLogStore`` injected, each changed field is
        persisted as one audit row (trigger source + old/new values + the
        memory pairs the change was derived from). Without one, the diff
        falls back to the logger so the write path still leaves a trace.
        """
        comparisons: list[tuple[str, Any, Any]] = [
            ("personality_tags", old_profile.personality_tags, new_profile.personality_tags),
            (
                "emotion_baseline",
                old_profile.emotion_baseline.model_dump(),
                new_profile.emotion_baseline.model_dump(),
            ),
            (
                "important_people",
                [person.model_dump() for person in old_profile.important_people],
                [person.model_dump() for person in new_profile.important_people],
            ),
            ("recurring_topics", old_profile.recurring_topics, new_profile.recurring_topics),
            (
                "preferred_response_style",
                old_profile.preferred_response_style,
                new_profile.preferred_response_style,
            ),
            (
                "short_term_state",
                old_profile.short_term_state.model_dump(),
                new_profile.short_term_state.model_dump(),
            ),
            (
                "pending_clarifications",
                old_profile.pending_clarifications,
                new_profile.pending_clarifications,
            ),
        ]

        changed = [(field, old, new) for field, old, new in comparisons if old != new]
        if not changed:
            return

        if self._change_log is not None:
            for field, old_value, new_value in changed:
                try:
                    self._change_log.record_change(
                        user_id,
                        field=field,
                        old_value=old_value,
                        new_value=new_value,
                        source=source,
                        evidence=evidence,
                    )
                except Exception as exc:  # audit must never break the write path
                    logger.warning("Profile change audit failed for %s: %s", field, exc)
        else:
            changes = [f"{field}: {old} -> {new}" for field, old, new in changed]
            logger.info(
                "Long-term profile updated for user_id=%s (source=%s):\n  %s",
                user_id,
                source,
                "\n  ".join(changes),
            )

"""Pure-function tests for memory-conflict detection and soft revision (P2-B)."""

from __future__ import annotations

import time

from app.domain.memory.conflict import (
    CLARIFICATION_WINDOW_DAYS,
    MAX_PENDING_CLARIFICATIONS,
    PersonConflict,
    detect_person_conflicts,
    renderable_clarifications,
    supersede_outdated_entries,
)
from app.domain.memory.types import EpisodicEntry, ImportantPerson, UserProfile


def _entry(
    *,
    entry_id: str = "e1",
    entities: list[dict[str, object]] | None = None,
    event_date: str = "2026-10-14",
    timestamp: float | None = None,
) -> EpisodicEntry:
    return EpisodicEntry(
        event_summary="测试事件",
        emotion="neutral",
        reply_insight="",
        timestamp=timestamp or time.time(),
        importance=0.8,
        entry_id=entry_id,
        entities=entities or [],
        event_date=event_date,
    )


def _profile(persons: list[tuple[str, float]]) -> UserProfile:
    return UserProfile(
        important_people=[
            ImportantPerson(name=name, relation="朋友", sentiment=sentiment)
            for name, sentiment in persons
        ]
    )


# ── detect_person_conflicts ──────────────────────────────────────────────


def test_detect_sign_flip_above_delta_is_conflict() -> None:
    profile = _profile([("小雨", 0.7)])
    entry = _entry(
        entry_id="e2",
        entities=[{"name": "小雨", "entity_type": "person", "sentiment": -0.5}],
    )

    conflicts = detect_person_conflicts([entry], profile)

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.person == "小雨"
    assert conflict.old_sentiment == 0.7
    assert conflict.new_sentiment == -0.5
    assert conflict.entry_id == "e2"
    assert conflict.date == "2026-10-14"


def test_detect_ignores_unknown_person() -> None:
    profile = _profile([("小雨", 0.7)])
    entry = _entry(entities=[{"name": "陌生人", "entity_type": "person", "sentiment": -0.9}])

    assert detect_person_conflicts([entry], profile) == []


def test_detect_ignores_small_drift() -> None:
    """|Δ| < CONFLICT_MIN_DELTA stays with the promotion tolerance guards."""
    profile = _profile([("妈妈", 0.3)])
    entry = _entry(entities=[{"name": "妈妈", "entity_type": "person", "sentiment": -0.1}])

    assert detect_person_conflicts([entry], profile) == []


def test_detect_ignores_same_sign_sentiment() -> None:
    profile = _profile([("妈妈", 0.5)])
    entry = _entry(entities=[{"name": "妈妈", "entity_type": "person", "sentiment": 0.9}])

    assert detect_person_conflicts([entry], profile) == []


def test_detect_dedupes_same_person_across_entries() -> None:
    profile = _profile([("小雨", 0.7)])
    entity = {"name": "小雨", "entity_type": "person", "sentiment": -0.6}
    entries = [_entry(entry_id="e2", entities=[entity]), _entry(entry_id="e3", entities=[entity])]

    assert len(detect_person_conflicts(entries, profile)) == 1


def test_detect_ignores_non_person_entities() -> None:
    profile = _profile([("老街咖啡馆", 0.7)])
    entry = _entry(entities=[{"name": "老街咖啡馆", "entity_type": "place", "sentiment": -0.8}])

    assert detect_person_conflicts([entry], profile) == []


def test_conflict_date_falls_back_to_timestamp() -> None:
    profile = _profile([("小雨", 0.7)])
    ts = 1_760_000_000.0  # 2025-10-09 in UTC
    entry = _entry(
        entities=[{"name": "小雨", "entity_type": "person", "sentiment": -0.6}],
        event_date=None,
        timestamp=ts,
    )

    conflicts = detect_person_conflicts([entry], profile)
    assert len(conflicts) == 1
    assert len(conflicts[0].date) == 10  # YYYY-MM-DD


def test_clarification_pair_serializes() -> None:
    conflict = PersonConflict(
        person="小雨", old_sentiment=0.7, new_sentiment=-0.5, entry_id="e2", date="2026-10-14"
    )

    pair = conflict.clarification_pair()

    assert pair == {
        "person": "小雨",
        "was": 0.7,
        "now": -0.5,
        "date": "2026-10-14",
    }


# ── supersede_outdated_entries ───────────────────────────────────────────


def test_supersede_retires_old_view_but_not_trigger() -> None:
    conflict = PersonConflict(
        person="小雨", old_sentiment=0.7, new_sentiment=-0.5, entry_id="e3", date="2026-10-14"
    )
    trigger = _entry(entry_id="e3", entities=[{"name": "小雨", "entity_type": "person", "sentiment": -0.5}])
    old_view = _entry(entry_id="e1", entities=[{"name": "小雨", "entity_type": "person", "sentiment": 0.6}])
    unrelated = _entry(entry_id="e2", entities=[{"name": "妈妈", "entity_type": "person", "sentiment": 0.8}])

    retired = supersede_outdated_entries([trigger, old_view, unrelated], conflict)

    assert retired == [old_view]
    assert old_view.superseded_by == "e3"
    assert trigger.superseded_by is None
    assert unrelated.superseded_by is None


def test_supersede_keeps_opposite_sign_mention() -> None:
    """An entry mentioning the person with the *new* sign stays live."""
    conflict = PersonConflict(
        person="小雨", old_sentiment=0.7, new_sentiment=-0.5, entry_id="e2", date="2026-10-14"
    )
    negative_mention = _entry(
        entry_id="e1", entities=[{"name": "小雨", "entity_type": "person", "sentiment": -0.3}]
    )

    assert supersede_outdated_entries([negative_mention], conflict) == []
    assert negative_mention.superseded_by is None


def test_supersede_keeps_neutral_mention() -> None:
    """Entries without a person sentiment carry no outdated view."""
    conflict = PersonConflict(
        person="小雨", old_sentiment=0.7, new_sentiment=-0.5, entry_id="e2", date="2026-10-14"
    )
    neutral = _entry(entry_id="e1", entities=[{"name": "小雨", "entity_type": "person"}])

    assert supersede_outdated_entries([neutral], conflict) == []
    assert neutral.superseded_by is None


def test_supersede_skips_already_superseded() -> None:
    conflict = PersonConflict(
        person="小雨", old_sentiment=0.7, new_sentiment=-0.5, entry_id="e3", date="2026-10-14"
    )
    retired_once = _entry(
        entry_id="e1",
        entities=[{"name": "小雨", "entity_type": "person", "sentiment": 0.6}],
    )
    retired_once.superseded_by = "e0"

    assert supersede_outdated_entries([retired_once], conflict) == []


# ── renderable_clarifications ────────────────────────────────────────────


def test_renderable_keeps_fresh_records() -> None:
    pending = [{"person": "小雨", "was": 0.7, "now": -0.5, "date": "2026-10-12"}]

    fresh = renderable_clarifications(pending, today="2026-10-14")

    assert fresh == pending


def test_renderable_drops_expired_records() -> None:
    pending = [{"person": "小雨", "was": 0.7, "now": -0.5, "date": "2026-09-01"}]

    assert renderable_clarifications(pending, today="2026-10-14") == []


def test_renderable_drops_future_and_malformed_records() -> None:
    pending = [
        {"person": "小雨", "was": 0.7, "now": -0.5, "date": "2026-12-01"},  # future
        {"person": "妈妈", "was": 0.7, "now": -0.5, "date": "not-a-date"},  # malformed
        "garbage-string",  # not a dict
    ]

    assert renderable_clarifications(pending, today="2026-10-14") == []


def test_renderable_window_boundary_is_inclusive() -> None:
    edge_day = CLARIFICATION_WINDOW_DAYS
    pending = [{"person": "小雨", "was": 0.7, "now": -0.5, "date": "2026-10-07"}]

    assert len(renderable_clarifications(pending, today="2026-10-14")) == 1
    assert edge_day == 7  # guard the assumption above


def test_max_pending_clarifications_capped() -> None:
    """The writer-side cap is small so the prompt block stays compact."""
    assert MAX_PENDING_CLARIFICATIONS == 3

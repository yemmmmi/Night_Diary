"""Memory-conflict detection and soft belief revision (P2-B).

When a new diary/chat memory contradicts what the profile already
believes — the clearest deterministic signal being a person-sentiment
sign flip (``妈妈 +0.6`` for weeks, then ``和小雨吵架了, 小雨 -0.4``) —
the agent must notice and revise, without ever rewriting the user's
original words.

This module holds the pure decision logic:

* :func:`detect_person_conflicts` — compares the person entities carried
  by the new entries against the profile's ``important_people``; a
  conflict is a sign flip of at least :data:`CONFLICT_MIN_DELTA`.
* :func:`supersede_outdated_entries` — soft-retires the entries that
  carry the outdated view (they mention the person with a sentiment of
  the same sign as the old profile). Superseded entries get a
  ``superseded_by`` pointer, drop out of retrieval/promotion, and keep
  their original text untouched.
* :class:`PersonConflict` / :meth:`PersonConflict.clarification_pair` —
  the pending-clarification record appended to the profile so the
  empathy agent can gently ask the user about the change.

Orchestration lives in :class:`~app.services.memory_gateway.MemoryGateway`
(the only layer holding both episodic and long-term memory), and every
profile mutation flows through the P1-B audit trail with
``source="conflict_resolution"``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.memory.types import EpisodicEntry, UserProfile

#: Person entity type labels accepted by the detector (P0-C taxonomy).
PERSON_TYPES = ("person", "人物", "people")
#: Minimum |new - old| for a same-person sentiment sign flip to count.
CONFLICT_MIN_DELTA = 0.6
#: How long a pending clarification stays renderable in prompts.
CLARIFICATION_WINDOW_DAYS = 7
#: Cap on the pending clarification queue (FIFO beyond this).
MAX_PENDING_CLARIFICATIONS = 3


def _person_entities(entry: EpisodicEntry) -> list[dict[str, Any]]:
    return [
        entity
        for entity in entry.entities
        if str(entity.get("entity_type", "")) in PERSON_TYPES
    ]


@dataclass(frozen=True)
class PersonConflict:
    """One detected person-sentiment reversal."""

    person: str
    old_sentiment: float
    new_sentiment: float
    entry_id: str
    date: str  # ISO date of the new entry

    def clarification_pair(self) -> dict[str, Any]:
        """Serialize into the profile's pending-clarification record."""
        return {
            "person": self.person,
            "was": self.old_sentiment,
            "now": self.new_sentiment,
            "date": self.date,
        }


def _entry_date(entry: EpisodicEntry) -> str:
    return entry.event_date or datetime.fromtimestamp(entry.timestamp).strftime(
        "%Y-%m-%d"
    )


def detect_person_conflicts(
    new_entries: list[EpisodicEntry],
    old_profile: UserProfile,
) -> list[PersonConflict]:
    """Detect person-sentiment sign flips between new entries and the profile.

    A conflict requires the person to already be in ``important_people``,
    the new entity sentiment to have the opposite sign, and the swing to
    be at least :data:`CONFLICT_MIN_DELTA` — small drifts stay with the
    promotion tolerance guards (P0-C).
    """
    people_by_name = {person.name: person for person in old_profile.important_people}
    conflicts: list[PersonConflict] = []
    seen: set[str] = set()
    for entry in new_entries:
        for entity in _person_entities(entry):
            name = str(entity.get("name", "")).strip()
            known = people_by_name.get(name)
            if known is None or name in seen:
                continue
            new_sentiment = float(entity.get("sentiment", 0.0) or 0.0)
            if (
                known.sentiment * new_sentiment < 0
                and abs(known.sentiment - new_sentiment) >= CONFLICT_MIN_DELTA
            ):
                seen.add(name)
                conflicts.append(
                    PersonConflict(
                        person=name,
                        old_sentiment=known.sentiment,
                        new_sentiment=new_sentiment,
                        entry_id=entry.entry_id,
                        date=_entry_date(entry),
                    )
                )
    return conflicts


def supersede_outdated_entries(
    all_entries: list[EpisodicEntry],
    conflict: PersonConflict,
) -> list[EpisodicEntry]:
    """Soft-retire the entries carrying the outdated view of the person.

    An entry is retired when it is not the trigger itself, is not already
    superseded, and mentions the person with a sentiment of the same sign
    as the old profile. The returned entries have been mutated in place
    (``superseded_by`` set to the trigger's id) — the caller persists
    them. The user's original text is never modified.
    """
    retired: list[EpisodicEntry] = []
    for entry in all_entries:
        if entry.entry_id == conflict.entry_id or entry.superseded_by is not None:
            continue
        for entity in _person_entities(entry):
            if str(entity.get("name", "")).strip() != conflict.person:
                continue
            sentiment = float(entity.get("sentiment", 0.0) or 0.0)
            if sentiment * conflict.old_sentiment > 0:  # same sign as outdated view
                entry.superseded_by = conflict.entry_id
                retired.append(entry)
            break
    return retired


def renderable_clarifications(
    pending: list[dict[str, Any]],
    *,
    today: str | None = None,
) -> list[dict[str, Any]]:
    """Filter the pending queue down to entries inside the freshness window."""
    if not pending:
        return []
    today = today or datetime.now().strftime("%Y-%m-%d")
    try:
        today_dt = datetime.strptime(today, "%Y-%m-%d")
    except ValueError:
        return []
    fresh: list[dict[str, Any]] = []
    for record in pending:
        if not isinstance(record, dict):
            continue
        try:
            record_dt = datetime.strptime(str(record.get("date", "")), "%Y-%m-%d")
        except ValueError:
            continue
        if 0 <= (today_dt - record_dt).days <= CLARIFICATION_WINDOW_DAYS:
            fresh.append(record)
    return fresh

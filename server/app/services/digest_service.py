"""Daily digest service — read/write ``daily_digests`` rows.

The digest is the per-day structured summary of scene 1's "tree-hole"
pipeline. Two write flows keep it consistent with **zero LLM cost on card
writes**:

- **Typed diary analyzed** (``analysis_service``): upserts the row with the
  diary section (LLM/rule extraction) merged with the day's existing card
  section.
- **Card created/updated/deleted** (``card_service``): calls
  :func:`refresh_cards_section` which re-aggregates *only* the ``cards``
  section (cheap, O(cards of the day)), never touching the diary section and
  never triggering an LLM call — a quick "记一笔" must not make the user wait.

Scene 2 consumes it via :func:`format_day_digest` — one choke point, two
shapes (basic / complex), and an empty string fallback for days without a
digest (old data renders full text as before).
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.infrastructure.models.daily_digest import DailyDigestRow
from app.infrastructure.models.memory_card import MemoryCardRow
from app.shared.digest import CardDigest, DiaryDigest, DiaryDigestPart

logger = logging.getLogger(__name__)

#: Momentary card timestamps are UTC; a "day" boundary is Beijing time
#: (UTC+8) — the diary corpus and users are China-based.
_BEIJING_OFFSET = timezone(timedelta(hours=8))


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Card helpers (small local parsers; card_service keeps its private ones) ──


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    with contextlib.suppress(json.JSONDecodeError, TypeError):
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if x]
    return []


def load_day_cards(db: Session, *, user_id: str, day: date) -> list[MemoryCardRow]:
    """Return the user's memory cards created on ``day`` (Beijing time)."""
    start = datetime(day.year, day.month, day.day, tzinfo=_BEIJING_OFFSET)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    # created_at is stored as UTC; convert the Beijing day window to UTC.
    start_utc = start.astimezone(UTC).replace(tzinfo=None)
    end_utc = end.astimezone(UTC).replace(tzinfo=None)
    return (
        db.query(MemoryCardRow)
        .filter(
            MemoryCardRow.user_id == user_id,
            MemoryCardRow.created_at >= start_utc,
            MemoryCardRow.created_at <= end_utc,
        )
        .order_by(MemoryCardRow.created_at.asc())
        .all()
    )


def cards_to_digest(cards: list[MemoryCardRow]) -> list[CardDigest]:
    """Map user-authored cards to the digest ``cards`` section (no LLM)."""
    return [
        CardDigest(
            emotion=row.emotion or "neutral",
            emotions=_json_list(row.emotions_json) or [row.emotion or "neutral"],
            mood=row.mood_score,
            tags=_json_list(row.tags_json),
            summary=(row.event_summary or "").strip(),
        )
        for row in cards
    ]


# ── Read / write ─────────────────────────────────────────────────────────


def get_digest(db: Session, *, user_id: str, day: date) -> DiaryDigest | None:
    """Return the stored digest for ``(user_id, day)`` or ``None``."""
    row = (
        db.query(DailyDigestRow)
        .filter(DailyDigestRow.user_id == user_id, DailyDigestRow.date == day)
        .first()
    )
    if row is None or not row.digest_json:
        return None
    try:
        return DiaryDigest.model_validate_json(row.digest_json)
    except Exception as exc:
        logger.warning(
            "Daily digest parse failed user_id=%s date=%s: %s", user_id, day, exc
        )
        return None


def upsert_digest(
    db: Session,
    *,
    user_id: str,
    day: date,
    digest: DiaryDigest,
) -> DailyDigestRow:
    """Create or update the ``(user_id, day)`` digest row (same transaction)."""
    row = (
        db.query(DailyDigestRow)
        .filter(DailyDigestRow.user_id == user_id, DailyDigestRow.date == day)
        .first()
    )
    digest.date = day
    digest.updated_at = _utcnow_iso()
    payload = digest.model_dump_json()
    if row is None:
        row = DailyDigestRow(
            user_id=user_id,
            date=day,
            digest_json=payload,
            updated_at=datetime.utcnow(),
        )
        db.add(row)
    else:
        row.digest_json = payload
        row.updated_at = datetime.utcnow()
    return row


def refresh_cards_section(
    db: Session,
    *,
    user_id: str,
    day: date,
    cards: list[MemoryCardRow] | None = None,
) -> DiaryDigest:
    """Re-aggregate the day's cards into the digest (zero LLM, never touches diary).

    If no digest row exists yet (card-only day), creates a basic card-only
    digest. Returns the updated in-memory digest — the caller commits.
    """
    if cards is None:
        cards = load_day_cards(db, user_id=user_id, day=day)
    existing = get_digest(db, user_id=user_id, day=day)
    if existing is None:
        digest = DiaryDigest(
            digest_type="basic",
            date=day,
            source="card" if cards else "card",
            cards=cards_to_digest(cards),
        )
    else:
        existing.cards = cards_to_digest(cards)
        # Source is deterministic from what sections exist: cards-only day →
        # "card"; typed diary only → "llm"; both → "card+llm". Never triggers
        # an LLM rerun on card writes.
        has_cards = bool(existing.cards)
        has_diary = bool(existing.diary.intent or existing.diary.summary)
        if has_cards and has_diary:
            existing.source = "card+llm"
        elif has_diary:
            existing.source = "llm"
        else:
            existing.source = "card"
        digest = existing
    upsert_digest(db, user_id=user_id, day=day, digest=digest)
    return digest


# ── Scene-2 consumption ──────────────────────────────────────────────────


def format_day_digest(db: Session, *, user_id: str, day: date) -> str:
    """Render the day digest as a compact prompt block for scene 2.

    Returns ``""`` when no digest exists — the caller falls back to the
    full-text rendering (backward compatible with pre-digest data).
    """
    digest = get_digest(db, user_id=user_id, day=day)
    if digest is None:
        return ""

    lines: list[str] = [f"【{day.isoformat()} 当日摘要】"]

    for card in digest.cards:
        tags = f"[{'、'.join(card.tags)}]" if card.tags else ""
        summary = card.summary or "（无文字）"
        lines.append(f"- 卡片{card.emotion}：{summary}{tags}")

    part: DiaryDigestPart = digest.diary
    if part.intent or part.summary or part.topics or part.emotion != "neutral":
        head = f"- 情绪：{part.emotion or '未知'}"
        if part.intent:
            head += f"（意图：{part.intent}）"
        if part.topics:
            head += f"｜话题：{'、'.join(part.topics)}"
        lines.append(head)
        if part.summary:
            lines.append(f"- 摘要：{part.summary}")
        if part.temporal_refs:
            refs = "；".join(
                f"{'过去' if r.direction == 'past' else '将来'}"
                f"({r.date_hint or '其他日期'}):{r.summary}"
                for r in part.temporal_refs
            )
            lines.append(f"- 提及非当日：{refs}")

    if digest.digest_type == "complex":
        if part.key_events:
            lines.append(f"- 关键事件：{'；'.join(part.key_events)}")
        if part.emotional_shifts:
            lines.append(f"- 情绪变化：{' → '.join(part.emotional_shifts)}")
        if part.relationships:
            rels = "；".join(
                f"{r.name}({r.relation or '关系不明'})" for r in part.relationships
            )
            lines.append(f"- 人物关系：{rels}")
        if part.conflicts:
            lines.append(f"- 冲突：{'；'.join(part.conflicts)}")
        if part.concerns:
            lines.append(f"- 担忧：{'；'.join(part.concerns)}")

    return "\n".join(lines)


__all__ = [
    "cards_to_digest",
    "format_day_digest",
    "get_digest",
    "load_day_cards",
    "refresh_cards_section",
    "upsert_digest",
]

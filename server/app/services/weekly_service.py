"""Weekly report ("周记") orchestration.

Aggregates a week's diary entries and memory cards into a single context, then
reuses the existing :class:`ExecutionPlanner` (multi-agent → InsightAgent weekly
report mode) to produce one reflective "weekly letter". Results are persisted in
the ``weekly_reports`` table, independent of any single diary entry.

Two flows mirror ``analysis_service``:
  MemoryCard + DiaryEntry → aggregated context → ExecutionPlanner.execute()
                                              → WeeklyReportRow
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.memory_card import MemoryCardRow
from app.infrastructure.models.weekly_report import WeeklyReportRow
from app.services import diary_service
from app.services.ai.router import ExecutionPlanner
from app.shared.errors import (
    WeeklyReportEmptyError,
    WeeklyReportExistsError,
    WeeklyReportNotFoundError,
)

if TYPE_CHECKING:
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

# Sentinel diary_id for planner logging/working-memory keying (no diary FK).
_WEEKLY_SENTINEL_ID = 0
_MAX_CARD_LINES = 30


# ── week bounds ──────────────────────────────────────────────────────────


def week_bounds(reference: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the ISO week containing ``reference``."""
    ref = reference or datetime.now(timezone.utc).date()
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


# ── aggregation ──────────────────────────────────────────────────────────


def _diaries_in_week(db: Session, start: date, end: date) -> list[DiaryEntryRow]:
    return (
        db.query(DiaryEntryRow)
        .filter(DiaryEntryRow.date >= start, DiaryEntryRow.date <= end)
        .order_by(DiaryEntryRow.date.asc())
        .all()
    )


def _cards_in_week(db: Session, start: date, end: date) -> list[MemoryCardRow]:
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end, time.max)
    return (
        db.query(MemoryCardRow)
        .filter(MemoryCardRow.created_at >= start_dt, MemoryCardRow.created_at <= end_dt)
        .order_by(MemoryCardRow.created_at.asc())
        .all()
    )


def _format_cards(cards: list[MemoryCardRow]) -> str:
    if not cards:
        return "（本周暂无记忆卡片）"
    lines: list[str] = []
    for card in cards[:_MAX_CARD_LINES]:
        day = card.created_at.date().isoformat() if card.created_at else "未知"
        summary = card.event_summary or "（仅情绪记录）"
        lines.append(f"[{day}] 情绪：{card.emotion} — {summary}")
    return "\n".join(lines)


def _avg_mood(cards: list[MemoryCardRow]) -> float | None:
    scores = [c.mood_score for c in cards if c.mood_score is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 3)


def _build_weekly_content(
    start: date,
    end: date,
    diaries: list[DiaryEntryRow],
    cards: list[MemoryCardRow],
) -> str:
    """Aggregate diaries + cards into one prompt body (contains the 本周/周报
    keyword so InsightAgent switches to weekly-report mode)."""
    diary_block = diary_service.format_history_summary(diaries)
    card_block = _format_cards(cards)
    return (
        f"这是本周（{start.isoformat()} 至 {end.isoformat()}）的周报回顾。"
        f"请基于以下本周的日记与记忆卡片，写一封温暖、有洞察的周记回信，"
        f"总结这一周的情绪起伏、反复出现的主题，并给出温和的建议。\n\n"
        f"【本周日记】\n{diary_block}\n\n"
        f"【本周记忆卡片】\n{card_block}"
    )


def _build_context(content: str) -> dict[str, str]:
    return {
        "current_content": content,
        "tags_context": "（周报聚合）",
        "history_summary": "（已包含在本周内容中）",
        "weather_info": "未获取天气信息",
    }


# ── persistence ──────────────────────────────────────────────────────────


def get_report_by_period(db: Session, period_start: date) -> WeeklyReportRow | None:
    return (
        db.query(WeeklyReportRow)
        .filter(WeeklyReportRow.period_start == period_start)
        .first()
    )


def get_latest_report(db: Session) -> WeeklyReportRow:
    row = (
        db.query(WeeklyReportRow)
        .order_by(desc(WeeklyReportRow.period_start))
        .first()
    )
    if row is None:
        raise WeeklyReportNotFoundError()
    return row


def list_reports(db: Session, *, skip: int = 0, limit: int = 20) -> list[WeeklyReportRow]:
    return (
        db.query(WeeklyReportRow)
        .order_by(desc(WeeklyReportRow.period_start))
        .offset(skip)
        .limit(limit)
        .all()
    )


def delete_report(db: Session, report_id: int) -> bool:
    row = db.query(WeeklyReportRow).filter(WeeklyReportRow.id == report_id).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    logger.info("周记删除成功: report_id=%d", report_id)
    return True


def delete_report_for_period(db: Session, period_start: date) -> bool:
    row = get_report_by_period(db, period_start)
    if row is None:
        return False
    return delete_report(db, row.id)


# ── generation ───────────────────────────────────────────────────────────


def create_weekly_report(
    db: Session,
    *,
    planner: ExecutionPlanner,
    reference: date | None = None,
) -> WeeklyReportRow:
    start, end = week_bounds(reference)

    if get_report_by_period(db, start) is not None:
        raise WeeklyReportExistsError()

    diaries = _diaries_in_week(db, start, end)
    cards = _cards_in_week(db, start, end)
    if not diaries and not cards:
        raise WeeklyReportEmptyError()

    content = _build_weekly_content(start, end, diaries, cards)
    result = planner.execute(
        diary_id=_WEEKLY_SENTINEL_ID,
        context=_build_context(content),
        content=content,
    )

    row = WeeklyReportRow(
        period_start=start,
        period_end=end,
        content=result.ai_ans,
        diary_count=len(diaries),
        card_count=len(cards),
        avg_mood=_avg_mood(cards),
        token_cost=result.token_cost,
        execution_tier=result.execution_tier,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "周记生成成功: report_id=%d period=%s..%s diaries=%d cards=%d tokens=%d",
        row.id,
        start.isoformat(),
        end.isoformat(),
        row.diary_count,
        row.card_count,
        row.token_cost or 0,
    )
    return row


def generate_weekly_report(
    db: Session,
    container: ServiceContainer,
    *,
    reference: date | None = None,
) -> WeeklyReportRow:
    """End-to-end entry: build planner from container and create a weekly report."""
    planner = container.build_execution_planner(db)
    return create_weekly_report(db, planner=planner, reference=reference)


def regenerate_weekly_report(
    db: Session,
    container: ServiceContainer,
    *,
    reference: date | None = None,
) -> WeeklyReportRow:
    """Force a fresh weekly report — replaces any existing one for the week."""
    start, _ = week_bounds(reference)
    delete_report_for_period(db, start)
    planner = container.build_execution_planner(db)
    return create_weekly_report(db, planner=planner, reference=reference)

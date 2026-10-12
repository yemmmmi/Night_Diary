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

import asyncio
import concurrent.futures
import json
import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, TypedDict

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.infrastructure.models.diary_entry import DiaryEntryRow
from app.infrastructure.models.memory_card import MemoryCardRow
from app.infrastructure.models.weekly_report import WeeklyReportRow
from app.services import diary_service, plan_service
from app.services.ai.router import ExecutionPlanner
from app.shared.errors import (
    WeeklyReportEmptyError,
    WeeklyReportExistsError,
    WeeklyReportNotFoundError,
)

if TYPE_CHECKING:
    from app.infrastructure.models import PlanRow, TaskRow
    from app.services.container import ServiceContainer

logger = logging.getLogger(__name__)

# Sentinel diary_id for planner logging/working-memory keying (no diary FK).
_WEEKLY_SENTINEL_ID = 0
_MAX_CARD_LINES = 30


# ── week bounds ──────────────────────────────────────────────────────────


def week_bounds(reference: date | None = None) -> tuple[date, date]:
    """Return (Monday, Sunday) of the ISO week containing ``reference``."""
    ref = reference or datetime.now(UTC).date()
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


# ── aggregation ──────────────────────────────────────────────────────────


def _diaries_in_week(db: Session, *, user_id: str, start: date, end: date) -> list[DiaryEntryRow]:
    return (
        db.query(DiaryEntryRow)
        .filter(
            DiaryEntryRow.user_id == user_id,
            DiaryEntryRow.date >= start,
            DiaryEntryRow.date <= end,
        )
        .order_by(DiaryEntryRow.date.asc())
        .all()
    )


def _cards_in_week(db: Session, *, user_id: str, start: date, end: date) -> list[MemoryCardRow]:
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end, time.max)
    return (
        db.query(MemoryCardRow)
        .filter(
            MemoryCardRow.user_id == user_id,
            MemoryCardRow.created_at >= start_dt,
            MemoryCardRow.created_at <= end_dt,
        )
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


class PlansInWeek(TypedDict):
    """Plans/tasks snapshot with activity (created or completed) in the week."""

    active_plans: list[PlanRow]
    week_tasks: list[TaskRow]


def _task_in_range(t: TaskRow, start: date, end: date) -> bool:
    """True if a task was created or completed within [start, end]."""
    if t.created_at and start <= t.created_at.date() <= end:
        return True
    return bool(t.completed_at and start <= t.completed_at.date() <= end)


def _plans_in_week(
    db: Session, *, user_id: str, start: date, end: date
) -> PlansInWeek:
    """Query plans/tasks that had activity (created or completed) this week.

    A plan counts as "active this week" when at least one of its tasks was
    created or completed within the window. Standalone tasks (no ``plan_id``)
    with in-window activity are collected separately so the weekly letter can
    mention them too.
    """
    active_plans: list[PlanRow] = []
    week_tasks: list[TaskRow] = []

    for plan in plan_service.list_plans(db, user_id=user_id, status="active"):
        in_range = [t for t in plan.tasks if _task_in_range(t, start, end)]
        if in_range:
            active_plans.append(plan)
            week_tasks.extend(in_range)

    # Standalone tasks (no plan_id) created or completed this week.
    for t in plan_service.list_tasks(db, user_id=user_id, status=None):
        if t.plan_id is None and _task_in_range(t, start, end):
            week_tasks.append(t)

    return {"active_plans": active_plans, "week_tasks": week_tasks}


def _plan_executions_snapshot(plans_data: PlansInWeek) -> list[dict[str, Any]]:
    """Structured plan execution summary for the weekly response."""
    items: list[dict[str, Any]] = []
    for plan in plans_data.get("active_plans", []):
        done = sum(1 for t in plan.tasks if t.status == "done")
        items.append(
            {
                "plan_id": plan.id,
                "title": plan.title,
                "done": done,
                "total": len(plan.tasks),
                "source_refs": json.loads(plan.source_refs_json or "[]"),
            }
        )
    return items


def _week_tasks_snapshot(plans_data: PlansInWeek) -> list[dict[str, Any]]:
    """Standalone (plan_id=None) task snapshots; plan tasks are aggregated above."""
    items: list[dict[str, Any]] = []
    for task in plans_data.get("week_tasks", []):
        if task.plan_id is None:
            items.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "source": task.source,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                }
            )
    return items


def _build_weekly_content(
    start: date,
    end: date,
    diaries: list[DiaryEntryRow],
    cards: list[MemoryCardRow],
    plans_data: PlansInWeek | None = None,
) -> str:
    """Aggregate diaries + cards into one prompt body (contains the 本周/周报
    keyword so InsightAgent switches to weekly-report mode)."""
    diary_block = diary_service.format_history_summary(diaries)
    card_block = _format_cards(cards)
    content = (
        f"这是本周（{start.isoformat()} 至 {end.isoformat()}）的周报回顾。"
        f"请基于以下本周的日记与记忆卡片，写一封温暖、有洞察的周记回信，"
        f"总结这一周的情绪起伏、反复出现的主题，并给出温和的建议。\n\n"
        f"【本周日记】\n{diary_block}\n\n"
        f"【本周记忆卡片】\n{card_block}"
    )
    if plans_data and (plans_data.get("active_plans") or plans_data.get("week_tasks")):
        content += "\n\n【本周计划执行】"
        for plan in plans_data.get("active_plans", []):
            done = sum(1 for t in plan.tasks if t.status == "done")
            total = len(plan.tasks)
            content += f"\n- 计划「{plan.title}」: {done}/{total} 完成"
        for task in plans_data.get("week_tasks", []):
            # 只列出不属于任何计划的独立任务, 计划内任务已汇总在上面.
            if task.plan_id is None:
                mark = "✓" if task.status == "done" else "○"
                content += f"\n- {mark} {task.title}"
    return content


def _build_context(content: str) -> dict[str, str]:
    return {
        "current_content": content,
        "tags_context": "（周报聚合）",
        "history_summary": "（已包含在本周内容中）",
        "weather_info": "未获取天气信息",
    }


# ── multi-dimensional analysis (D4) ──────────────────────────────────────
# Bounded borrowing from Hermes' delegate_task: instead of one monolithic
# weekly prompt, the week is sliced into isolated dimensions, each analysed
# separately and reduced to a short summary. No generic delegation and no tool
# access are introduced — the only reusable primitive is SubTaskRunner.

_MAX_DIMENSION_LINES = 20


def _diary_tag_names(entry: DiaryEntryRow) -> list[str]:
    return [t.name for t in entry.tags if getattr(t, "name", None)] if entry.tags else []


def _dimension_subtasks(
    diaries: list[DiaryEntryRow],
    cards: list[MemoryCardRow],
    plans_data: PlansInWeek,
) -> list[Any]:
    """Build isolated per-dimension sub-tasks from the week's data.

    Each sub-task carries only its own slice (mood / tags / plans / events) so
    no dimension can see the raw week wholesale — the "isolated context" half of
    D4. Dimensions with no data are skipped entirely.
    """
    from app.domain.agents.subtask import SubTask

    subtasks: list[SubTask] = []

    if cards:
        mood_lines = [
            f"[{c.created_at.date().isoformat() if c.created_at else '未知'}] "
            f"{c.emotion}（心情 {c.mood_score if c.mood_score is not None else '未知'}）"
            for c in cards[:_MAX_CARD_LINES]
        ]
        avg = _avg_mood(cards)
        header = f"本周均分心情：{avg}\n" if avg is not None else ""
        subtasks.append(
            SubTask(
                name="情绪曲线",
                context=header + "\n".join(mood_lines),
                instruction="概括本周情绪的总体走向与显著波动。",
            )
        )

    tag_counts: dict[str, int] = {}
    for entry in diaries:
        for name in _diary_tag_names(entry):
            tag_counts[name] = tag_counts.get(name, 0) + 1
    if tag_counts:
        ranked = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        subtasks.append(
            SubTask(
                name="反复主题",
                context="\n".join(f"{name}（出现 {n} 次）" for name, n in ranked[:_MAX_DIMENSION_LINES]),
                instruction="指出本周反复出现的主题或关注点。",
            )
        )

    plan_lines: list[str] = []
    for plan in plans_data.get("active_plans", []):
        done = sum(1 for t in plan.tasks if t.status == "done")
        plan_lines.append(f"计划「{plan.title}」：{done}/{len(plan.tasks)} 完成")
    for task in plans_data.get("week_tasks", []):
        if task.plan_id is None:
            plan_lines.append(f"{'✓' if task.status == 'done' else '○'} {task.title}")
    if plan_lines:
        subtasks.append(
            SubTask(
                name="计划执行",
                context="\n".join(plan_lines),
                instruction="评估本周计划与任务的推进情况。",
            )
        )

    event_lines: list[str] = []
    for entry in diaries:
        first_line = next((ln for ln in (entry.content or "").splitlines() if ln.strip()), "")
        day = entry.date.isoformat() if entry.date else "未知"
        event_lines.append(f"[{day}] {first_line.strip()[:80]}")
    if event_lines:
        subtasks.append(
            SubTask(
                name="生活事件",
                context="\n".join(event_lines[:_MAX_DIMENSION_LINES]),
                instruction="概括本周发生的主要事件。",
            )
        )

    return subtasks


def _dimension_worker(llm: Any) -> Any:
    """Adapt an LLM into a summary-only sub-task worker."""

    async def _worker(task: Any) -> str:
        from app.shared.llm import message_text

        prompt = (
            "你是周报的多维分析助手。只基于给定的【维度数据】输出该维度的一句话摘要"
            "（不超过 120 字），不要编造数据之外的信息，不要展开。\n\n"
            f"分析维度：{task.name}\n要求：{task.instruction}\n\n"
            f"【维度数据】\n{task.context}"
        )
        response = await llm.ainvoke(prompt)
        return message_text(response).strip()

    return _worker


def _run_async_sync(coro: Any) -> Any:
    """Run a coroutine from a sync context (mirrors analysis_service)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        if loop.is_closed():
            raise RuntimeError
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _weekly_dimension_block(
    planner: ExecutionPlanner,
    diaries: list[DiaryEntryRow],
    cards: list[MemoryCardRow],
    plans_data: PlansInWeek,
) -> str:
    """Return a 【多维分析摘要】 block, or "" when unavailable.

    Best-effort: any failure (no LLM, provider error) degrades to an empty
    block so weekly generation is never blocked by the dimension pre-pass.
    """
    from app.domain.agents.subtask import SubTaskRunner, format_subtask_summaries

    subtasks = _dimension_subtasks(diaries, cards, plans_data)
    if not subtasks:
        return ""
    llm = planner.llm_for_tier("light")
    if llm is None:
        return ""
    try:
        runner = SubTaskRunner(_dimension_worker(llm))
        outcomes = _run_async_sync(runner.run(subtasks))
    except Exception as exc:
        logger.warning("weekly dimension analysis skipped: %s", exc)
        return ""
    return format_subtask_summaries(outcomes)


# ── persistence ──────────────────────────────────────────────────────────


def get_report_by_period(
    db: Session, *, user_id: str, period_start: date
) -> WeeklyReportRow | None:
    return (
        db.query(WeeklyReportRow)
        .filter(
            WeeklyReportRow.user_id == user_id,
            WeeklyReportRow.period_start == period_start,
        )
        .first()
    )


def get_latest_report(db: Session, *, user_id: str) -> WeeklyReportRow:
    row = (
        db.query(WeeklyReportRow)
        .filter(WeeklyReportRow.user_id == user_id)
        .order_by(desc(WeeklyReportRow.period_start))
        .first()
    )
    if row is None:
        raise WeeklyReportNotFoundError()
    return row


def list_reports(
    db: Session, *, user_id: str, skip: int = 0, limit: int = 20
) -> list[WeeklyReportRow]:
    return (
        db.query(WeeklyReportRow)
        .filter(WeeklyReportRow.user_id == user_id)
        .order_by(desc(WeeklyReportRow.period_start))
        .offset(skip)
        .limit(limit)
        .all()
    )


def delete_report(db: Session, *, user_id: str, report_id: int) -> bool:
    row = (
        db.query(WeeklyReportRow)
        .filter(
            WeeklyReportRow.id == report_id,
            WeeklyReportRow.user_id == user_id,
        )
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    logger.info("周记删除成功: report_id=%d", report_id)
    return True


def delete_report_for_period(db: Session, *, user_id: str, period_start: date) -> bool:
    row = get_report_by_period(db, user_id=user_id, period_start=period_start)
    if row is None:
        return False
    return delete_report(db, user_id=user_id, report_id=row.id)


# ── generation ───────────────────────────────────────────────────────────


def create_weekly_report(
    db: Session,
    *,
    user_id: str,
    planner: ExecutionPlanner,
    reference: date | None = None,
) -> WeeklyReportRow:
    start, end = week_bounds(reference)

    # Application-level uniqueness check scoped to (user_id, period_start).
    if get_report_by_period(db, user_id=user_id, period_start=start) is not None:
        raise WeeklyReportExistsError()

    diaries = _diaries_in_week(db, user_id=user_id, start=start, end=end)
    cards = _cards_in_week(db, user_id=user_id, start=start, end=end)
    if not diaries and not cards:
        raise WeeklyReportEmptyError()

    plans_data = _plans_in_week(db, user_id=user_id, start=start, end=end)
    content = _build_weekly_content(start, end, diaries, cards, plans_data=plans_data)
    dimension_block = _weekly_dimension_block(planner, diaries, cards, plans_data)
    if dimension_block:
        content = f"{content}\n\n【本周多维分析摘要】\n{dimension_block}"
    result = planner.execute(
        diary_id=_WEEKLY_SENTINEL_ID,
        context=_build_context(content),
        content=content,
    )

    row = WeeklyReportRow(
        user_id=user_id,
        period_start=start,
        period_end=end,
        content=result.reply,
        diary_count=len(diaries),
        card_count=len(cards),
        avg_mood=_avg_mood(cards),
        token_cost=result.token_cost,
        execution_tier=result.execution_tier,
        created_at=datetime.now(UTC),
        plan_executions_json=json.dumps(
            _plan_executions_snapshot(plans_data), ensure_ascii=False
        ),
        week_tasks_json=json.dumps(
            _week_tasks_snapshot(plans_data), ensure_ascii=False
        ),
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
    user_id: str,
    reference: date | None = None,
) -> WeeklyReportRow:
    """End-to-end entry: build planner from container and create a weekly report."""
    planner = container.build_execution_planner(user_id=user_id)
    return create_weekly_report(db, user_id=user_id, planner=planner, reference=reference)


def regenerate_weekly_report(
    db: Session,
    container: ServiceContainer,
    *,
    user_id: str,
    reference: date | None = None,
) -> WeeklyReportRow:
    """Force a fresh weekly report — replaces any existing one for the week."""
    start, _ = week_bounds(reference)
    delete_report_for_period(db, user_id=user_id, period_start=start)
    planner = container.build_execution_planner(user_id=user_id)
    return create_weekly_report(db, user_id=user_id, planner=planner, reference=reference)

"""ModePromptBuilder — presentation layer of the V3.x user-mode system.

Consumes the *current mode* decided by :mod:`app.services.ai.mood_monitor`
(itself the judgement layer) and injects two blocks into the scene-2 system
prompt, per spec ``docs/superpowers/specs/2026-08-18-v3x-mode-system-design.md``
sec.4:

* **【当前计划与状态】** — the user's active plans / today's todos as a
  knowledge source (injected for ``daily`` and ``followup``; weakened/omitted
  for ``introspection``).
* **【模式语气指令】** — the tone directive matching the mode
  (``daily`` / ``followup`` / ``introspection``), enforcing the global
  no-pressure bottom line.

Separation-of-concerns: this middleware only *renders words* from a given mode —
it never decides the mode (that is ``MoodMonitor``'s job). It is defensive:
if no DB session or user context is available it returns the prompt unchanged, so a
degraded mode subsystem can never break the reply flow (same philosophy as the
other P7 middlewares).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.models.daily_mode import MODE
from app.shared.middleware.base import MiddlewareBase, MiddlewareContext

logger = logging.getLogger(__name__)

#: Default key we read the request-scoped SQLAlchemy session from in ctx.extra.
_DB_KEY = "db"

# Upper bound on the injected plan/todo block length (token budget).
_PLAN_BLOCK_MAX_CHARS = 320

# Central source of truth for per-mode tone directives (user-visible naming in
# frontend: 日常 / 跟进 / 内视). These back the injected 【模式语气指令】.
_TONE_DIRECTIVES: dict[str, str] = {
    MODE.DAILY: (
        "你是用户的并列生活助手，协助记录、规划与复盘。已知悉 ta 的计划与待办，"
        "可自然协助推进，但不得催促、不放大逾期、不用『必须/赶紧』等施压措辞，"
        "用户未要求时不要反复提醒。"
    ),
    MODE.FOLLOWUP: (
        "用户处于『跟进』档：你可以在 ta 尝试推进某项待办或被计划卡住时，"
        "温和提一句可执行的下一步。频率克制、一句话点到为止，绝不追责过往未完成项，"
        "同样不施加『必须/赶紧』等压力。"
    ),
    MODE.INTROSPECTION: (
        "用户此刻需要『内视』：先放下计划推进，专注回应 ta 当下的状态与卡住处。"
        "暂不主动提及待办与截止日期，语气平缓，不问『什么时候能做』。"
    ),
}

_GLOBAL_BOTTOM_LINE = "任何情况下都不要用『必须/赶紧/逾期警告』等方式对用户施加压力。"


class ModePromptBuilder(MiddlewareBase):
    """Inject mode tone + plan-state blocks into a conversation system prompt."""

    name = "mode"

    def __init__(
        self,
        *,
        store: Any = None,
        plan_block_max_chars: int = _PLAN_BLOCK_MAX_CHARS,
    ) -> None:
        # ``store`` defaults to a real DailyModeStore (lazy import to avoid
        # heavy coupling); an injected stub lets unit tests drive it without a DB.
        self._store = store
        self._plan_block_max_chars = plan_block_max_chars

    # -- helpers ------------------------------------------------------------
    def _resolve_session(self, ctx: MiddlewareContext) -> Session | None:
        """Best-effort DB session from the context; None when unavailable."""
        db = ctx.extra.get(_DB_KEY)
        if isinstance(db, Session):
            return db
        return None

    def _resolve_mode(self, db: Session | None, ctx: MiddlewareContext) -> str | None:
        """Current mode for (user, today); None when mode subsystem unavailable."""
        if db is None:
            return None
        try:
            from app.services.ai.mood_monitor import MoodMonitor

            monitor = MoodMonitor(store=self._store)
            from datetime import date

            return monitor.effective_mode(db, user_id=ctx.user_id, day=date.today())
        except Exception as exc:  # defensive: never break the reply
            logger.warning("ModePromptBuilder mode lookup failed: %s", exc)
            return None

    def _plan_state_block(
        self, db: Session | None, user_id: str, mode: str
    ) -> str:
        """The 【当前计划与状态】 knowledge block."""
        if mode == MODE.INTROSPECTION:
            return "【当前计划与状态】【本档暂不主动推进计划】\n- 这轮侧重回应此刻状态，暂缓提及待办。"
        if db is None:
            return "【当前计划与状态】（暂无计划知识可用）"
        try:
            from app.services import plan_service

            plans = plan_service.list_plans(db, user_id=user_id, status="active")
            today = plan_service.get_today_tasks(db, user_id=user_id)
            lines = []
            for p in plans[:2]:
                lines.append(f"- 计划：{p.title}（{p.status}）")
            done = sum(1 for t in today if t.status == "done")
            if today:
                lines.append(
                    f"- 今日待办：{len(today)} 项（已完成 {done}）"
                )
            if not lines:
                return "【当前计划与状态】（暂无活跃计划）"
            block = "【当前计划与状态】\n" + "\n".join(lines)
            return block[: self._plan_block_max_chars]
        except Exception as exc:
            logger.warning("ModePromptBuilder plan block failed: %s", exc)
            return "【当前计划与状态】（暂无计划知识可用）"

    def _tone_block(self, mode: str) -> str:
        directive = _TONE_DIRECTIVES.get(mode, _TONE_DIRECTIVES[MODE.DAILY])
        return f"【模式语气·{mode}】{directive}\n{_GLOBAL_BOTTOM_LINE}"

    # -- hook --------------------------------------------------------------
    def on_system_prompt(self, prompt: str, ctx: MiddlewareContext) -> str:
        db = self._resolve_session(ctx)
        mode = self._resolve_mode(db, ctx) or MODE.DAILY
        plan_block = self._plan_state_block(db, ctx.user_id, mode)
        tone_block = self._tone_block(mode)
        return f"{prompt}\n{plan_block}\n{tone_block}"

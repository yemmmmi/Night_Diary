"""Unit tests for the V3 P7 middleware pipeline.

Covers:
- Pipeline basics (empty = zero-cost no-op, ordering, error isolation).
- SafetyMiddleware (idempotent crisis-block injection, single source of truth).
- FinalizeMiddleware (emotion gate, severe-signal audit, diary always-write,
  degraded-memory skip, exception swallowing).
- build_default_pipeline factory.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.agents.prompts import EMPATHY_CRISIS_BLOCK
from app.shared.middleware import (
    FinalizeMiddleware,
    MiddlewareBase,
    MiddlewareContext,
    MiddlewarePipeline,
    SafetyMiddleware,
    build_default_pipeline,
)
from app.shared.middleware.safety import CRISIS_SYSTEM_BLOCK


def _ctx(**overrides) -> MiddlewareContext:
    defaults = dict(
        scenario="conversation",
        user_id="user-1",
        content="今天心情不错",
        reply_text="谢谢分享，保持好心情。",
    )
    defaults.update(overrides)
    return MiddlewareContext(**defaults)


# ── Pipeline basics ───────────────────────────────────────────────────


def test_empty_pipeline_is_zero_cost_noop():
    """空管道：is_empty=True，apply/run 都是无害 no-op。"""
    pipeline = MiddlewarePipeline()
    assert pipeline.is_empty is True
    ctx = _ctx()
    assert pipeline.apply_system_prompt("原始 prompt", ctx) == "原始 prompt"
    pipeline.run_on_reply(ctx)  # 不应抛异常


class _RecordingMiddleware(MiddlewareBase):
    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self._calls = calls

    def on_system_prompt(self, prompt: str, ctx: MiddlewareContext) -> str:
        self._calls.append(f"prompt:{self.name}")
        return f"{prompt}|{self.name}"

    def on_reply(self, ctx: MiddlewareContext) -> None:
        self._calls.append(f"reply:{self.name}")


def test_pipeline_applies_system_prompt_in_registration_order():
    """apply_system_prompt 按注册顺序 fold。"""
    calls: list[str] = []
    pipeline = MiddlewarePipeline()
    pipeline.add(_RecordingMiddleware("a", calls)).add(_RecordingMiddleware("b", calls))

    out = pipeline.apply_system_prompt("base", _ctx())

    assert calls == ["prompt:a", "prompt:b"]
    assert out == "base|a|b"


def test_pipeline_run_on_reply_runs_all_middlewares():
    """run_on_reply 逐个执行所有中间件。"""
    calls: list[str] = []
    pipeline = MiddlewarePipeline(
        [_RecordingMiddleware("a", calls), _RecordingMiddleware("b", calls)]
    )
    pipeline.run_on_reply(_ctx())
    assert calls == ["reply:a", "reply:b"]


def test_pipeline_on_reply_error_does_not_break_later_middlewares():
    """单个中间件 on_reply 抛异常不应中断后续中间件。"""
    calls: list[str] = []

    class _Boom(MiddlewareBase):
        name = "boom"

        def on_reply(self, ctx: MiddlewareContext) -> None:
            raise RuntimeError("boom")

    class _After(MiddlewareBase):
        name = "after"

        def on_reply(self, ctx: MiddlewareContext) -> None:
            calls.append("after")

    pipeline = MiddlewarePipeline([_Boom(), _After()])
    pipeline.run_on_reply(_ctx())  # 不应抛异常
    assert calls == ["after"]


# ── SafetyMiddleware ──────────────────────────────────────────────────


def test_safety_injects_crisis_block_into_plain_prompt():
    """无危机段的 prompt 应被注入共享危机响应块。"""
    mw = SafetyMiddleware()
    out = mw.on_system_prompt("你是夜记的回信者。", _ctx())
    assert "危机响应模式" in out
    assert out.startswith("你是夜记的回信者。")
    assert "自杀" in out or "极度痛苦" in out


def test_safety_is_idempotent():
    """已含危机标记的 prompt 不被二次注入。"""
    mw = SafetyMiddleware()
    prompt_with_block = f"你是夜记的回信者。\n{CRISIS_SYSTEM_BLOCK}"
    out = mw.on_system_prompt(prompt_with_block, _ctx())
    assert out == prompt_with_block


def test_safety_block_is_single_source_of_truth():
    """安全块与场景一 EMPATHY_CRISIS_BLOCK 同源，两场景危机准则永不漂移。"""
    assert CRISIS_SYSTEM_BLOCK == EMPATHY_CRISIS_BLOCK


# ── FinalizeMiddleware ────────────────────────────────────────────────


class _FakeEpisodic:
    """episodic memory stand-in: always present (non-None)."""


def _make_container(*, episodic=None) -> MagicMock:
    container = MagicMock()
    container.episodic_memory = episodic
    return container


@patch("app.infrastructure.task_queue.enqueue_task")
def test_finalize_skips_without_container(mock_enqueue):
    """container 为 None 时直接跳过。"""
    mw = FinalizeMiddleware()
    ctx = _ctx(container=None)
    mw.on_reply(ctx)
    mock_enqueue.assert_not_called()


@patch("app.infrastructure.task_queue.enqueue_task")
def test_finalize_skips_with_empty_reply(mock_enqueue):
    """reply_text 为空时直接跳过。"""
    mw = FinalizeMiddleware()
    ctx = _ctx(container=_make_container(episodic=_FakeEpisodic()), reply_text="")
    mw.on_reply(ctx)
    mock_enqueue.assert_not_called()


@patch("app.infrastructure.task_queue.enqueue_task")
def test_finalize_conversation_skips_low_emotion_safe_turn(mock_enqueue):
    """conversation：情绪分低且无 severe 信号 → 不写。"""
    mw = FinalizeMiddleware()
    ctx = _ctx(
        scenario="conversation",
        content="今天天气不错，出去走了走。",
        container=_make_container(episodic=_FakeEpisodic()),
    )
    mw.on_reply(ctx)
    mock_enqueue.assert_not_called()


@patch("app.infrastructure.task_queue.enqueue_task")
def test_finalize_conversation_writes_on_severe_signal(mock_enqueue):
    """conversation：severe 信号（危机）→ 必须写（安全审计轨迹）。"""
    mw = FinalizeMiddleware()
    ctx = _ctx(
        scenario="conversation",
        content="我不想活了",
        container=_make_container(episodic=_FakeEpisodic()),
    )
    mw.on_reply(ctx)
    mock_enqueue.assert_called_once()
    # 参数应是 (gw.persist_atom, atom)
    args = mock_enqueue.call_args
    assert callable(args.args[0]) and args.args[0].__name__ == "persist_atom"


@patch("app.infrastructure.task_queue.enqueue_task")
def test_finalize_diary_always_writes_even_neutral_content(mock_enqueue):
    """diary_reply：always_persist=True → 中性内容也写。"""
    mw = FinalizeMiddleware()
    entry = MagicMock()
    entry.content = "今天没什么特别的。"
    entry.tags = []
    entry.date = None
    entry.created_at = None
    ctx = _ctx(
        scenario="diary_reply",
        content=entry.content,
        always_persist=True,
        container=_make_container(episodic=_FakeEpisodic()),
        extra={"entry": entry},
    )
    mw.on_reply(ctx)
    mock_enqueue.assert_called_once()


@patch("app.infrastructure.task_queue.enqueue_task")
def test_finalize_skips_when_memory_degraded(mock_enqueue):
    """episodic 为 None（记忆降级）→ 跳过不写。"""
    mw = FinalizeMiddleware()
    ctx = _ctx(
        content="我不想活了",
        container=_make_container(episodic=None),
    )
    mw.on_reply(ctx)
    mock_enqueue.assert_not_called()


@patch("app.infrastructure.task_queue.enqueue_task")
@patch(
    "app.services.normalizer.ContentNormalizer.from_diary",
    side_effect=RuntimeError("normalizer boom"),
)
def test_finalize_exception_is_swallowed(mock_from_diary, mock_enqueue):
    """构建/写回过程抛异常 → 吞掉记日志，不向外传播。"""
    mw = FinalizeMiddleware()
    entry = MagicMock()
    entry.content = "今天心情不错"
    entry.tags = []
    entry.date = None
    entry.created_at = None
    ctx = _ctx(
        scenario="diary_reply",
        always_persist=True,
        container=_make_container(episodic=_FakeEpisodic()),
        extra={"entry": entry},
    )
    mw.on_reply(ctx)  # 不应抛异常
    mock_enqueue.assert_not_called()


def test_finalize_diary_without_entry_returns_none_atom():
    """diary 场景缺 entry → _build_atom 返回 None（日志警告）。"""
    mw = FinalizeMiddleware()
    estimator = MagicMock()
    atom = mw._build_atom(
        _ctx(scenario="diary_reply", extra={}), estimator, 0.0
    )
    assert atom is None


# ── build_default_pipeline ────────────────────────────────────────────


def test_build_default_pipeline_contains_safety_and_finalize():
    """默认管道含 Safety + Finalize 两个中间件。"""
    pipeline = build_default_pipeline()
    assert pipeline.is_empty is False
    names = [mw.name for mw in pipeline._middlewares]  # type: ignore[attr-defined]
    assert names == ["safety", "finalize"]

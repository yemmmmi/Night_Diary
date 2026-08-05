"""MultiAgentGraph — Supervisor + Worker 的纯 asyncio 编排。

V1 使用 LangGraph 来连接多智能体管道。V2 刻意放弃了该
依赖（它不在 ``pyproject.toml`` 中）：这里的图是一个小型、
显式的 ``asyncio`` 编排器。这使运行时透明，从打包的 sidecar 中移除了
沉重的依赖，并使超时/降级行为易于测试。

执行模型
---------------
1. **classify** — ``supervisor.classify`` 决定意图、层级、预算，以及
   ``activated_agents`` / ``activated_skills`` 集合。
2. **分阶段扇出** — Worker 分阶段运行以保证数据依赖：
   *provider* Worker（``retrieval``）先运行，然后 *consumer* Worker
   （``empathy`` / ``insight``）在检索上下文已合并到状态后并发运行。
   V1 一次性扇出所有 Worker，导致 insight 从未看到检索输出；
   分阶段模型修复了这一点，同时仍使用 ``asyncio.gather`` 进行并发阶段。
3. **synthesize** — ``supervisor.synthesize`` 合并 Worker 输出，容忍
   部分失败。

弹性
----------
每个 Worker 都被包装：它获得独立的 ``asyncio.wait_for`` 超时，
任何超时/异常都回退到该 Worker 的 ``fallback()``（安全模板）
并在 ``errors`` 通道中添加一条记录。一个 Worker 失败永远不会中止运行。

来自并发 Worker 的部分更新通过 :class:`MultiAgentState` 上声明的 reducer
合并（计数器/errors 用 ``operator.add``，activated-* 列表用
``merge_unique``），因此 B-7 状态契约得到遵守，而无需
LangGraph 应用通道。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast, get_origin, get_type_hints

from app.domain.agents.context_compressor import ContextCompressor, prepare_compressed_history
from app.domain.agents.state import MultiAgentState
from app.domain.agents.supervisor import SupervisorAgent
from app.shared.pipeline_trace import trace_span

logger = logging.getLogger(__name__)

WorkerRunner = Callable[[MultiAgentState], Awaitable[dict[str, Any]]]
WorkerFallback = Callable[[MultiAgentState], dict[str, Any]]

DEFAULT_WORKER_TIMEOUT_S = 30.0
PROVIDER_PHASE = 0  # retrieval——产生供后续阶段消费的上下文
CONSUMER_PHASE = 1  # empathy / insight——读取检索上下文


def _reducer_table() -> dict[str, tuple[Callable[[Any, Any], Any], Any]]:
    """从 MultiAgentState 的注解构建 {field: (reducer, identity)}。

    只返回声明为 ``Annotated[..., reducer]`` 的字段；其余所有
    字段在合并时采用后写覆盖策略。
    """
    table: dict[str, tuple[Callable[[Any, Any], Any], Any]] = {}
    hints = get_type_hints(MultiAgentState, include_extras=True)
    for name, hint in hints.items():
        metadata = getattr(hint, "__metadata__", None)
        if not metadata:
            continue
        reducer = metadata[0]
        base = hint.__args__[0]
        identity: Any = [] if (get_origin(base) or base) is list else 0
        table[name] = (reducer, identity)
    return table


_REDUCERS = _reducer_table()


def _merge(state: dict[str, Any], update: dict[str, Any]) -> None:
    """将节点的部分更新折叠到 ``state`` 中，遵守通道 reducer。"""
    for key, value in update.items():
        if key in _REDUCERS:
            reducer, identity = _REDUCERS[key]
            current = state.get(key, identity)
            state[key] = reducer(current, value)
        else:
            state[key] = value


class MultiAgentGraph:
    """为单个日记轮次运行 Supervisor + Worker 管道。"""

    def __init__(
        self,
        supervisor: SupervisorAgent,
        workers: dict[str, WorkerRunner],
        fallbacks: dict[str, WorkerFallback],
        phases: dict[str, int],
        *,
        worker_timeout_s: float = DEFAULT_WORKER_TIMEOUT_S,
        context_compressor: ContextCompressor | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._workers = workers
        self._fallbacks = fallbacks
        self._phases = phases
        self._timeout = worker_timeout_s
        self._compressor = context_compressor

    async def invoke(self, state: MultiAgentState) -> MultiAgentState:
        merged: dict[str, Any] = dict(state)
        _merge(merged, prepare_compressed_history(merged, self._compressor))

        with trace_span(
            "S3_classify",
            "意图分类与路由",
            input_snapshot={"diary_id": merged.get("diary_id", "")},
        ) as span:
            classify_update = await self._supervisor.classify(
                cast(MultiAgentState, merged)
            )
            if span:
                span.set_output(
                    {
                        "intent": classify_update.get("intent"),
                        "tier": classify_update.get("tier"),
                        "activated_agents": classify_update.get("activated_agents"),
                    }
                )
        _merge(merged, classify_update)

        activated = [name for name in merged.get("activated_agents", []) if name in self._workers]
        for phase in sorted({self._phases.get(name, CONSUMER_PHASE) for name in activated}):
            phase_workers = [
                name for name in activated if self._phases.get(name, CONSUMER_PHASE) == phase
            ]
            if not phase_workers:
                continue
            phase_label = "检索阶段" if phase == PROVIDER_PHASE else "生成阶段"
            with trace_span(
                f"S4_phase{phase}",
                phase_label,
                input_snapshot={"workers": phase_workers},
            ) as span:
                results = await asyncio.gather(
                    *(self._run_safe(name, cast(MultiAgentState, merged)) for name in phase_workers),
                    return_exceptions=True,
                )
                if span:
                    span.set_output(
                        {
                            "worker_count": len(phase_workers),
                            "success_count": sum(
                                1 for r in results if not isinstance(r, BaseException)
                            ),
                        }
                    )
            for name, result in zip(phase_workers, results, strict=True):
                if isinstance(result, BaseException):
                    # _run_safe 不应抛出异常；这用于防范其中的 bug。
                    logger.error("worker %s raised past safety wrapper: %s", name, result)
                    update = dict(self._fallbacks[name](cast(MultiAgentState, merged)))
                    update["errors"] = [f"worker '{name}' crashed: {result!r}"]
                    _merge(merged, update)
                else:
                    _merge(merged, result)

        with trace_span(
            "S5_synthesize",
            "回复合成",
            input_snapshot={"tier": merged.get("tier", "")},
        ) as span:
            synth_update = await self._supervisor.synthesize(cast(MultiAgentState, merged))
            if span:
                span.set_output(
                    {"final_response_len": len(synth_update.get("final_response", ""))}
                )
        _merge(merged, synth_update)
        return cast(MultiAgentState, merged)

    async def _run_safe(self, name: str, state: MultiAgentState) -> dict[str, Any]:
        runner = self._workers[name]
        fallback = self._fallbacks[name]
        try:
            return await asyncio.wait_for(runner(state), timeout=self._timeout)
        except asyncio.TimeoutError:  # noqa: UP041
            logger.warning("worker %s timed out after %.1fs, using fallback", name, self._timeout)
            update = dict(fallback(state))
            update["errors"] = [f"worker '{name}' timeout after {self._timeout}s"]
            return update
        except Exception as exc:
            logger.warning("worker %s failed (%s), using fallback", name, type(exc).__name__)
            update = dict(fallback(state))
            update["errors"] = [f"worker '{name}' failed: {type(exc).__name__}: {exc}"]
            return update


class MultiAgentGraphBuilder:
    """:class:`MultiAgentGraph` 的流式构建器。"""

    def __init__(
        self,
        *,
        worker_timeout_s: float = DEFAULT_WORKER_TIMEOUT_S,
        context_compressor: ContextCompressor | None = None,
    ) -> None:
        self._supervisor: SupervisorAgent | None = None
        self._workers: dict[str, WorkerRunner] = {}
        self._fallbacks: dict[str, WorkerFallback] = {}
        self._phases: dict[str, int] = {}
        self._timeout = worker_timeout_s
        self._compressor = context_compressor

    def set_supervisor(self, supervisor: SupervisorAgent) -> MultiAgentGraphBuilder:
        self._supervisor = supervisor
        return self

    def add_worker(
        self,
        name: str,
        runner: WorkerRunner,
        fallback: WorkerFallback,
        *,
        phase: int = CONSUMER_PHASE,
    ) -> MultiAgentGraphBuilder:
        self._workers[name] = runner
        self._fallbacks[name] = fallback
        self._phases[name] = phase
        return self

    def build(self) -> MultiAgentGraph:
        if self._supervisor is None:
            raise ValueError("MultiAgentGraph requires a supervisor (call set_supervisor)")
        return MultiAgentGraph(
            self._supervisor,
            self._workers,
            self._fallbacks,
            self._phases,
            worker_timeout_s=self._timeout,
            context_compressor=self._compressor,
        )


def create_multi_agent_graph(
    supervisor: SupervisorAgent,
    empathy_agent: Any,
    retrieval_agent: Any,
    insight_agent: Any,
    *,
    worker_timeout_s: float = DEFAULT_WORKER_TIMEOUT_S,
    context_compressor: ContextCompressor | None = None,
    prompt_tuner: Any = None,
) -> MultiAgentGraph:
    """将三个 Worker 智能体连接成具有正确阶段/回退的图。

    ``retrieval`` 是 provider（阶段 0）；``empathy``/``insight`` 是 consumer
    （阶段 1），因此它们能观察到检索上下文。每个 Worker 的 ``fallback``
    被适配为图所期望的统一 ``(state) -> dict`` 签名。

    ``prompt_tuner``（可选）在 empathy/insight 智能体运行前从用户反馈
    历史生成 ``style_fragment``，闭合反馈循环。
    """

    def _build_style_fragment(state: MultiAgentState) -> str | None:
        if prompt_tuner is None:
            return state.get("style_fragment") or None
        try:
            diary_content = state.get("diary_content", "")
            word_count = len(diary_content)
            return cast(
                str,
                prompt_tuner.build_dynamic_prompt(
                    agent_type="empathy",
                    diary_word_count=word_count,
                ),
            )
        except Exception:
            return state.get("style_fragment") or None

    builder = MultiAgentGraphBuilder(
        worker_timeout_s=worker_timeout_s,
        context_compressor=context_compressor,
    )
    builder.set_supervisor(supervisor)
    builder.add_worker(
        "retrieval",
        lambda state: retrieval_agent.run(state),
        lambda state: retrieval_agent.fallback(),
        phase=PROVIDER_PHASE,
    )
    builder.add_worker(
        "empathy",
        lambda state: empathy_agent.run(state, style_fragment=_build_style_fragment(state)),
        lambda state: empathy_agent.fallback(
            state.get("intent", "pure_record"),
            is_crisis=state.get("tier") == "crisis",
        ),
        phase=CONSUMER_PHASE,
    )
    builder.add_worker(
        "insight",
        lambda state: insight_agent.run(state, style_fragment=_build_style_fragment(state)),
        lambda state: insight_agent.fallback(),
        phase=CONSUMER_PHASE,
    )
    return builder.build()


__all__ = [
    "DEFAULT_WORKER_TIMEOUT_S",
    "MultiAgentGraph",
    "MultiAgentGraphBuilder",
    "create_multi_agent_graph",
]

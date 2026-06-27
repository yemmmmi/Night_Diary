"""MultiAgentGraph — pure-asyncio orchestration of the Supervisor + Workers.

V1 used LangGraph to wire the multi-agent pipeline. V2 deliberately drops that
dependency (it is not in ``pyproject.toml``): the graph here is a small,
explicit ``asyncio`` orchestrator. This keeps the runtime transparent, removes a
heavy dependency from the packaged sidecar, and makes timeout/degradation
behaviour easy to test.

Execution model
---------------
1. **classify** — ``supervisor.classify`` decides intent, tier, budget, and the
   ``activated_agents`` / ``activated_skills`` sets.
2. **phased fan-out** — workers run in phases so data dependencies hold:
   *provider* workers (``retrieval``) run first, then *consumer* workers
   (``empathy`` / ``insight``) run concurrently with the retrieval context
   already merged into the state. V1 fanned all workers out at once, so insight
   never saw retrieval output; the phased model fixes that while still using
   ``asyncio.gather`` for the concurrent phase.
3. **synthesize** — ``supervisor.synthesize`` merges worker outputs, tolerating
   partial failures.

Resilience
----------
Each worker is wrapped: it gets an independent ``asyncio.wait_for`` timeout, and
any timeout/exception falls back to that worker's ``fallback()`` (a safe template)
plus an entry in the ``errors`` channel. One worker failing never aborts the run.

Partial updates from concurrent workers are merged with the reducers declared on
:class:`MultiAgentState` (``operator.add`` for counters/errors, ``merge_unique``
for the activated-* lists), so the B-7 state contract is honoured without
LangGraph applying the channels.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast, get_origin, get_type_hints

from app.domain.agents.context_compressor import ContextCompressor, prepare_compressed_history
from app.domain.agents.state import MultiAgentState
from app.domain.agents.supervisor import SupervisorAgent

logger = logging.getLogger(__name__)

WorkerRunner = Callable[[MultiAgentState], Awaitable[dict[str, Any]]]
WorkerFallback = Callable[[MultiAgentState], dict[str, Any]]

DEFAULT_WORKER_TIMEOUT_S = 30.0
PROVIDER_PHASE = 0  # retrieval — produces context consumed by later phases
CONSUMER_PHASE = 1  # empathy / insight — read retrieval context


def _reducer_table() -> dict[str, tuple[Callable[[Any, Any], Any], Any]]:
    """Build {field: (reducer, identity)} from MultiAgentState's annotations.

    Only fields declared ``Annotated[..., reducer]`` are returned; everything
    else is last-write-wins during merge.
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
    """Fold a node's partial update into ``state`` honouring channel reducers."""
    for key, value in update.items():
        if key in _REDUCERS:
            reducer, identity = _REDUCERS[key]
            current = state.get(key, identity)
            state[key] = reducer(current, value)
        else:
            state[key] = value


class MultiAgentGraph:
    """Runs the Supervisor + Worker pipeline for a single diary turn."""

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

        classify_update = await self._supervisor.classify(cast(MultiAgentState, merged))
        _merge(merged, classify_update)

        activated = [
            name for name in merged.get("activated_agents", []) if name in self._workers
        ]
        for phase in sorted({self._phases.get(name, CONSUMER_PHASE) for name in activated}):
            phase_workers = [
                name for name in activated if self._phases.get(name, CONSUMER_PHASE) == phase
            ]
            if not phase_workers:
                continue
            results = await asyncio.gather(
                *(self._run_safe(name, cast(MultiAgentState, merged)) for name in phase_workers),
                return_exceptions=True,
            )
            for name, result in zip(phase_workers, results, strict=True):
                if isinstance(result, BaseException):
                    # _run_safe should never raise; this guards against bugs in it.
                    logger.error("worker %s raised past safety wrapper: %s", name, result)
                    update = dict(self._fallbacks[name](cast(MultiAgentState, merged)))
                    update["errors"] = [f"worker '{name}' crashed: {result!r}"]
                    _merge(merged, update)
                else:
                    _merge(merged, result)

        synth_update = await self._supervisor.synthesize(cast(MultiAgentState, merged))
        _merge(merged, synth_update)
        return cast(MultiAgentState, merged)

    async def _run_safe(self, name: str, state: MultiAgentState) -> dict[str, Any]:
        runner = self._workers[name]
        fallback = self._fallbacks[name]
        try:
            return await asyncio.wait_for(runner(state), timeout=self._timeout)
        except TimeoutError:
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
    """Fluent builder for :class:`MultiAgentGraph`."""

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
    """Wire the three Worker agents into a graph with correct phases/fallbacks.

    ``retrieval`` is a provider (phase 0); ``empathy``/``insight`` are consumers
    (phase 1) so they observe the retrieval context. Each worker's ``fallback``
    is adapted to the uniform ``(state) -> dict`` signature the graph expects.

    ``prompt_tuner`` (optional) generates a ``style_fragment`` from user feedback
    history before empathy/insight agents run, closing the feedback loop.
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

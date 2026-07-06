"""Tracing interfaces and record types for LLM and Skill observability.

These are *ports*: pure record dataclasses plus ``Protocol`` interfaces that the
domain layer (agents, skills) depends on. The concrete SQLite-backed
implementations live in ``app.infrastructure`` so the domain never imports the
ORM directly (keeps the ``domain → infrastructure`` boundary one-way and lets
unit tests inject the in-memory tracers below).

Every tracer exposes a single ``record(entry)`` method so callers treat all
three observability streams (LLM calls, agent decisions, skill activations)
uniformly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SkillActivationRecord:
    """One skill activation evaluation captured during registry selection."""

    skill_name: str
    score: float
    threshold: float
    activated: bool
    reason: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    decision_id: str = ""
    input_digest: str = ""
    latency_ms: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SkillActivationTracer(Protocol):
    """Port for recording skill activation/suppression decisions."""

    def record(self, entry: SkillActivationRecord) -> None: ...


class NoOpSkillActivationTracer:
    """Default tracer that discards records."""

    def record(self, entry: SkillActivationRecord) -> None:
        _ = entry


class InMemorySkillActivationTracer:
    """Collect activation records in memory — for unit tests."""

    def __init__(self) -> None:
        self.records: list[SkillActivationRecord] = []

    def record(self, entry: SkillActivationRecord) -> None:
        self.records.append(entry)


@dataclass(frozen=True, slots=True)
class LLMCallRecord:
    """One LLM invocation captured for cost/latency observability.

    Written to ``llm_call_logs``. ``tokens_in``/``tokens_out`` feed the cost
    regression check in ``make eval``; ``tier`` ties the call back to the
    Supervisor's routing decision.
    """

    agent_name: str  # "supervisor" | "empathy" | "retrieval" | "insight"
    call_type: str  # "classify" | "generate" | "rerank" | "synthesize"
    model: str
    tier: str = ""  # "light" | "medium" | "heavy" | "crisis"
    prompt: str = ""
    response: str = ""
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    decision_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class LLMCallTracer(Protocol):
    """Port for recording each LLM call (injected into agents via DI)."""

    def record(self, entry: LLMCallRecord) -> None: ...


class NoOpLLMCallTracer:
    """Default tracer that discards records."""

    def record(self, entry: LLMCallRecord) -> None:
        _ = entry


class InMemoryLLMCallTracer:
    """Collect LLM-call records in memory — for unit tests."""

    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    def record(self, entry: LLMCallRecord) -> None:
        self.records.append(entry)


@dataclass(frozen=True, slots=True)
class AgentDecisionRecord:
    """One Supervisor/agent routing decision captured for traceability.

    Written to ``agent_decisions``. ``skill_ids`` mirrors the skills the
    Supervisor activated for this turn (the ``skill_ids`` JSON column), linking a
    decision to its ``SkillActivationRecord`` rows via ``id``/``decision_id``.
    """

    agent_name: str  # "supervisor" | "empathy" | ...
    decision_type: (
        str  # "intent_classification" | "tier_routing" | "skill_activation" | "worker_routing"
    )
    diary_id: str = ""
    intent: str = ""
    tier: str = ""
    skill_ids: tuple[str, ...] = ()
    reasoning: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AgentDecisionLogger(Protocol):
    """Port for recording agent decisions (injected into the Supervisor)."""

    def record(self, entry: AgentDecisionRecord) -> None: ...


class NoOpAgentDecisionLogger:
    """Default logger that discards records."""

    def record(self, entry: AgentDecisionRecord) -> None:
        _ = entry


class InMemoryAgentDecisionLogger:
    """Collect agent-decision records in memory — for unit tests."""

    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    def record(self, entry: AgentDecisionRecord) -> None:
        self.records.append(entry)

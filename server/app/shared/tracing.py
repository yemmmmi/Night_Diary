"""用于 LLM 和技能可观测性的追踪接口与记录类型。

这些是*端口*：纯记录数据类加上领域层（智能体、技能）依赖的 ``Protocol``
接口。具体的基于 SQLite 的实现位于 ``app.infrastructure`` 中，因此领域层
永远不会直接导入 ORM（保持 ``domain → infrastructure`` 边界单向，并允许
单元测试注入下方的内存追踪器）。

每个追踪器都暴露单一的 ``record(entry)`` 方法，因此调用方可以统一对待
三个可观测性流（LLM 调用、智能体决策、技能激活）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SkillActivationRecord:
    """在技能注册表选择期间捕获的一次技能激活评估。"""

    skill_name: str
    score: float
    threshold: float
    activated: bool
    reason: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    decision_id: str = ""
    input_digest: str = ""
    latency_ms: float = 0.0
    trace_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SkillActivationTracer(Protocol):
    """用于记录技能激活/抑制决策的端口。"""

    def record(self, entry: SkillActivationRecord) -> None: ...


class NoOpSkillActivationTracer:
    """丢弃记录的默认追踪器。"""

    def record(self, entry: SkillActivationRecord) -> None:
        _ = entry


class InMemorySkillActivationTracer:
    """在内存中收集激活记录——用于单元测试。"""

    def __init__(self) -> None:
        self.records: list[SkillActivationRecord] = []

    def record(self, entry: SkillActivationRecord) -> None:
        self.records.append(entry)


@dataclass(frozen=True, slots=True)
class LLMCallRecord:
    """为成本/延迟可观测性捕获的一次 LLM 调用。

    写入 ``llm_call_logs``。``tokens_in``/``tokens_out`` 为 ``make eval``
    中的成本回归检查提供数据；``tier`` 将调用关联回 Supervisor 的路由决策。
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
    trace_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class LLMCallTracer(Protocol):
    """用于记录每次 LLM 调用的端口（通过依赖注入注入到智能体中）。"""

    def record(self, entry: LLMCallRecord) -> None: ...


class NoOpLLMCallTracer:
    """丢弃记录的默认追踪器。"""

    def record(self, entry: LLMCallRecord) -> None:
        _ = entry


class InMemoryLLMCallTracer:
    """在内存中收集 LLM 调用记录——用于单元测试。"""

    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    def record(self, entry: LLMCallRecord) -> None:
        self.records.append(entry)


@dataclass(frozen=True, slots=True)
class AgentDecisionRecord:
    """为可追溯性捕获的一次 Supervisor/智能体路由决策。

    写入 ``agent_decisions``。``skill_ids`` 镜像了 Supervisor 在本轮中激活的
    技能（``skill_ids`` JSON 列），通过 ``id``/``decision_id`` 将决策关联到
    其 ``SkillActivationRecord`` 行。
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
    trace_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AgentDecisionLogger(Protocol):
    """用于记录智能体决策的端口（注入到 Supervisor 中）。"""

    def record(self, entry: AgentDecisionRecord) -> None: ...


class NoOpAgentDecisionLogger:
    """丢弃记录的默认日志器。"""

    def record(self, entry: AgentDecisionRecord) -> None:
        _ = entry


class InMemoryAgentDecisionLogger:
    """在内存中收集智能体决策记录——用于单元测试。"""

    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    def record(self, entry: AgentDecisionRecord) -> None:
        self.records.append(entry)

"""Tracing interfaces and record types for LLM and Skill observability."""

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

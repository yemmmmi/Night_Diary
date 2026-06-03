"""Shared types for the Worker Agents and the IntentClassifier.

``IntentResult`` is the structured output of :class:`~app.domain.agents.intent_classifier.IntentClassifier`.
It mirrors V1's classifier contract (``need_retrieval`` / ``need_weather`` /
``need_analysis`` routing flags + a coarse ``intent_category`` + ``confidence``)
but is a Pydantic model so callers get validation and JSON round-tripping for
free, and ``intent_category`` is constrained to the four canonical intents that
``MultiAgentState.intent`` also uses.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class IntentCategory(StrEnum):
    """The four canonical diary intents shared with ``MultiAgentState.intent``."""

    PURE_RECORD = "pure_record"
    EMOTIONAL_SUPPORT = "emotional_support"
    RETROSPECTIVE_REVIEW = "retrospective_review"
    HABIT_TRACKING = "habit_tracking"


class IntentResult(BaseModel):
    """Structured intent-classification result used to route the pipeline."""

    intent_category: str = IntentCategory.PURE_RECORD.value
    need_retrieval: bool = False
    need_weather: bool = False
    need_analysis: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


__all__ = ["IntentCategory", "IntentResult"]

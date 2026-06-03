"""Multi-agent pipeline: shared state, intent classification, Workers, orchestration.

B-8 delivered the three Worker Agents (Empathy / Retrieval / Insight) and the
IntentClassifier. B-9 adds the :class:`SupervisorAgent` (intent + Skill
integration + tier routing + synthesis) and the pure-asyncio
:class:`MultiAgentGraph` that orchestrates them (no LangGraph).
"""

from __future__ import annotations

from app.domain.agents.empathy_agent import EmpathyAgent
from app.domain.agents.graph import (
    MultiAgentGraph,
    MultiAgentGraphBuilder,
    create_multi_agent_graph,
)
from app.domain.agents.insight_agent import InsightAgent
from app.domain.agents.intent_classifier import IntentClassifier
from app.domain.agents.retrieval_agent import RetrievalAgent
from app.domain.agents.state import MultiAgentState, extract_token_usage, merge_unique
from app.domain.agents.supervisor import SupervisorAgent, allocate_token_budget
from app.domain.agents.types import IntentCategory, IntentResult

__all__ = [
    "EmpathyAgent",
    "InsightAgent",
    "IntentCategory",
    "IntentClassifier",
    "IntentResult",
    "MultiAgentGraph",
    "MultiAgentGraphBuilder",
    "MultiAgentState",
    "RetrievalAgent",
    "SupervisorAgent",
    "allocate_token_budget",
    "create_multi_agent_graph",
    "extract_token_usage",
    "merge_unique",
]

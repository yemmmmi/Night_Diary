"""Multi-agent pipeline: shared state, intent classification, workers, orchestration.

B-8 delivered the three worker agents (Empathy / Retrieval / Insight) and
IntentClassifier. B-9 added :class:`SupervisorAgent` (intent + skill
integration + tiered routing + synthesis) and the pure-asyncio
:class:`MultiAgentGraph` that orchestrates them (no LangGraph).

This module lazy-loads via ``__getattr__`` so importing it does not pull the
heavy langchain / chromadb / sentence_transformers dependency chain at startup.
Direct submodule imports (e.g. ``from app.domain.agents.graph import
MultiAgentGraph``) bypass this ``__init__`` and load only what is needed.
"""

from __future__ import annotations

__all__ = [
    "ContextCompressor",
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


def __getattr__(name: str) -> object:
    if name in __all__:
        import importlib

        # Map the public names to their source modules.
        _module_map = {
            "ContextCompressor": "app.domain.agents.context_compressor",
            "EmpathyAgent": "app.domain.agents.empathy_agent",
            "InsightAgent": "app.domain.agents.insight_agent",
            "IntentCategory": "app.domain.agents.types",
            "IntentClassifier": "app.domain.agents.intent_classifier",
            "IntentResult": "app.domain.agents.types",
            "MultiAgentGraph": "app.domain.agents.graph",
            "MultiAgentGraphBuilder": "app.domain.agents.graph",
            "MultiAgentState": "app.domain.agents.state",
            "RetrievalAgent": "app.domain.agents.retrieval_agent",
            "SupervisorAgent": "app.domain.agents.supervisor",
            "allocate_token_budget": "app.domain.agents.supervisor",
            "create_multi_agent_graph": "app.domain.agents.graph",
            "extract_token_usage": "app.domain.agents.state",
            "merge_unique": "app.domain.agents.state",
        }
        mod_name = _module_map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

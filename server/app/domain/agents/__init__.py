"""多智能体管道：共享状态、意图分类、Worker、编排。

B-8 交付了三个 Worker 智能体（Empathy / Retrieval / Insight）和
IntentClassifier。B-9 新增 :class:`SupervisorAgent`（意图 + 技能
集成 + 层级路由 + 合成）以及编排它们的纯 asyncio
:class:`MultiAgentGraph`（不使用 LangGraph）。

模块通过 ``__getattr__`` 懒加载，避免在启动时拉入沉重的
langchain / chromadb / sentence_transformers 依赖链。直接子模块导入（如
``from app.domain.agents.graph import MultiAgentGraph``）会绕过此
``__init__``，只加载实际需要的部分。
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

        # 将公开名称映射到其源模块。
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

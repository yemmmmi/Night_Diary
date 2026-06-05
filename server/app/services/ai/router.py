"""ExecutionPlanner — tier routing and executor selection."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy.orm import Session

from app.infrastructure.models.model_provider import ModelProviderRow
from app.services.ai import agent_executor, chain_executor, multi_agent_executor
from app.services.ai.prompts import FALLBACK_FEEDBACK, TEMPORAL_KEYWORDS
from app.services.ai.tool_factory import build_tool_map
from app.shared.errors import AIServiceUnavailableError
from app.shared.llm import LLMClient
from app.shared.tracing import AgentDecisionLogger, AgentDecisionRecord, NoOpAgentDecisionLogger
from app.shared.tracing_llm import TracingLLMClient

logger = logging.getLogger(__name__)


class ExecutionMode(StrEnum):
    MULTI_AGENT = "multi_agent"
    AGENT = "agent"
    CHAIN = "chain"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    mode: ExecutionMode
    tier: str
    estimated_tokens: int
    reason: str


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    ai_ans: str
    token_cost: int
    cache_hit_tokens: int
    cache_miss_tokens: int
    output_tokens: int
    thk_log: str
    agent_mode: str
    execution_tier: str
    activated_agents: str


class ExecutionPlanner:
    """Route diary analysis to multi-agent / agent / chain executors."""

    TIER_TOKEN_ESTIMATE: ClassVar[dict[str, int]] = {
        "light": 500,
        "medium": 1200,
        "heavy": 2000,
        "crisis": 200,
    }

    def __init__(
        self,
        *,
        llm_by_tier: dict[str, LLMClient],
        multi_agent_graph: Any | None = None,
        retriever: Any | None = None,
        episodic: Any | None = None,
        long_term: Any | None = None,
        working_memory: Any | None = None,
        decision_logger: AgentDecisionLogger | None = None,
        db: Session | None = None,
        multi_agent_enabled: bool = True,
    ) -> None:
        self._llm_by_tier = llm_by_tier
        self._graph = multi_agent_graph
        self._retriever = retriever
        self._episodic = episodic
        self._long_term = long_term
        self._working_memory = working_memory
        self._decision_logger = decision_logger or NoOpAgentDecisionLogger()
        self._db = db
        self._multi_agent_enabled = multi_agent_enabled

    def plan(
        self,
        *,
        diary_id: int,
        content: str,
        diary_length: int,
    ) -> RoutingDecision:
        has_temporal = any(kw in content for kw in TEMPORAL_KEYWORDS)
        if diary_length < 100 and not has_temporal:
            tier = "light"
        elif has_temporal or diary_length >= 300:
            tier = "heavy" if diary_length >= 500 else "medium"
        else:
            tier = "medium"

        if self._multi_agent_enabled and self._graph is not None:
            mode = ExecutionMode.MULTI_AGENT
            reason = "multi-agent graph available"
        elif has_temporal and self._db is not None and self._retriever is not None:
            mode = ExecutionMode.AGENT
            reason = "temporal keywords detected"
        elif self._llm_by_tier:
            mode = ExecutionMode.CHAIN
            reason = "default chain mode"
        else:
            mode = ExecutionMode.FALLBACK
            reason = "no LLM configured"
            tier = "light"

        return RoutingDecision(
            mode=mode,
            tier=tier,
            estimated_tokens=self.TIER_TOKEN_ESTIMATE.get(tier, 800),
            reason=reason,
        )

    def _log_routing(
        self,
        *,
        diary_id: int,
        decision: RoutingDecision,
        content: str,
        intent: str = "",
        activated_skills: tuple[str, ...] = (),
        decision_type: str = "route",
    ) -> None:
        record = AgentDecisionRecord(
            id=uuid.uuid4().hex,
            agent_name="execution_planner",
            decision_type=decision_type,
            diary_id=str(diary_id),
            intent=intent,
            tier=decision.tier,
            skill_ids=activated_skills,
            reasoning=(
                f"mode={decision.mode.value}; diary_length={len(content)}; "
                f"estimated_tokens={decision.estimated_tokens}; {decision.reason}"
            ),
        )
        self._decision_logger.record(record)

    def execute(
        self,
        *,
        diary_id: int,
        context: dict[str, str],
        content: str,
    ) -> AnalysisResult:
        decision = self.plan(
            diary_id=diary_id,
            content=content,
            diary_length=len(content),
        )
        self._log_routing(diary_id=diary_id, decision=decision, content=content)

        if decision.mode == ExecutionMode.FALLBACK:
            return AnalysisResult(
                ai_ans=FALLBACK_FEEDBACK,
                token_cost=0,
                cache_hit_tokens=0,
                cache_miss_tokens=0,
                output_tokens=0,
                thk_log=f"[Fallback] {decision.reason}",
                agent_mode="fallback",
                execution_tier=decision.tier,
                activated_agents="",
            )

        llm = self._resolve_llm(decision.tier)
        activated_agents = ""

        try:
            if decision.mode == ExecutionMode.MULTI_AGENT and self._graph is not None:
                run = multi_agent_executor.run_multi_agent(
                    self._graph,
                    diary_id=diary_id,
                    diary_content=content,
                    episodic=self._episodic,
                    long_term=self._long_term,
                    working_memory=self._working_memory,
                )
                activated_agents = ",".join(run.activated_agents)
                self._log_routing(
                    diary_id=diary_id,
                    decision=RoutingDecision(
                        mode=decision.mode,
                        tier=run.tier,
                        estimated_tokens=decision.estimated_tokens,
                        reason=decision.reason,
                    ),
                    content=content,
                    intent=run.intent,
                    activated_skills=tuple(run.activated_skills),
                    decision_type="tier_routing",
                )
                return AnalysisResult(
                    ai_ans=run.text,
                    token_cost=run.tokens["total_tokens"],
                    cache_hit_tokens=run.tokens["cache_hit_tokens"],
                    cache_miss_tokens=run.tokens["cache_miss_tokens"],
                    output_tokens=run.tokens["output_tokens"],
                    thk_log=run.log,
                    agent_mode="multi_agent",
                    execution_tier=run.tier,
                    activated_agents=activated_agents,
                )

            if decision.mode == ExecutionMode.AGENT and self._db is not None:
                tools = build_tool_map(self._db, retriever=self._retriever, llm=llm)
                text, tokens, log = agent_executor.run_agent(llm, context, tools)
                activated_agents = "react_tools"
                return AnalysisResult(
                    ai_ans=text,
                    token_cost=tokens["total_tokens"],
                    cache_hit_tokens=tokens["cache_hit_tokens"],
                    cache_miss_tokens=tokens["cache_miss_tokens"],
                    output_tokens=tokens["output_tokens"],
                    thk_log=log,
                    agent_mode="agent",
                    execution_tier=decision.tier,
                    activated_agents=activated_agents,
                )

            text, tokens, log = chain_executor.run_chain(llm, context)
            return AnalysisResult(
                ai_ans=text,
                token_cost=tokens["total_tokens"],
                cache_hit_tokens=tokens["cache_hit_tokens"],
                cache_miss_tokens=tokens["cache_miss_tokens"],
                output_tokens=tokens["output_tokens"],
                thk_log=log,
                agent_mode="chain",
                execution_tier=decision.tier,
                activated_agents="",
            )
        except AIServiceUnavailableError:
            raise
        except Exception as exc:
            logger.error("Execution failed, degrading to fallback: %s", exc, exc_info=True)
            return AnalysisResult(
                ai_ans=FALLBACK_FEEDBACK,
                token_cost=0,
                cache_hit_tokens=0,
                cache_miss_tokens=0,
                output_tokens=0,
                thk_log=f"[降级] {exc}",
                agent_mode="fallback",
                execution_tier=decision.tier,
                activated_agents="",
            )

    def _resolve_llm(self, tier: str) -> LLMClient:
        llm = self._llm_by_tier.get(tier) or self._llm_by_tier.get("default")
        if llm is None and self._llm_by_tier:
            llm = next(iter(self._llm_by_tier.values()))
        if llm is None:
            raise AIServiceUnavailableError(f"未配置 tier={tier} 的 LLM 模型")
        return llm


def resolve_llm_clients_by_tier(
    db: Session,
    *,
    llm_factory: Any,
    tracer: Any | None = None,
    prefer_active: bool = True,
) -> dict[str, LLMClient]:
    """Build per-tier LLM clients from ``model_providers`` table."""
    query = db.query(ModelProviderRow).filter(ModelProviderRow.api_key_encrypted.isnot(None))
    if prefer_active:
        query = query.filter(ModelProviderRow.is_active.is_(True))
    providers = query.order_by(ModelProviderRow.id.asc()).all()

    clients: dict[str, LLMClient] = {}
    for provider in providers:
        tier = provider.tier or "default"
        if tier in clients:
            continue
        try:
            inner = llm_factory.create_from_provider(provider)
            model_name = provider.model_name
            if tracer is not None:
                clients[tier] = TracingLLMClient(
                    inner,
                    model=model_name,
                    tier=tier,
                    tracer=tracer,
                )
            else:
                clients[tier] = inner
        except Exception as exc:
            logger.warning("Skip provider id=%s tier=%s: %s", provider.id, tier, exc)
    return clients

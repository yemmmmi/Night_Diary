"""Service-layer dependency container — wires domain + infrastructure for C-1."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.domain.agents.empathy_agent import EmpathyAgent
from app.domain.agents.graph import MultiAgentGraph, create_multi_agent_graph
from app.domain.agents.insight_agent import InsightAgent
from app.domain.agents.intent_classifier import IntentClassifier
from app.domain.agents.retrieval_agent import RetrievalAgent
from app.domain.agents.supervisor import SupervisorAgent
from app.domain.knowledge.store import DomainKnowledgeStore
from app.domain.memory.episodic import EpisodicMemory
from app.domain.memory.long_term import LongTermMemory
from app.domain.memory.working import WorkingMemory
from app.domain.rag.bm25 import BM25Index
from app.domain.rag.collections import DiaryCollectionManager
from app.domain.rag.retriever import HybridRetriever
from app.domain.skills.registry import create_default_registry
from app.infrastructure.agent_decision_logger import SqliteAgentDecisionLogger
from app.infrastructure.database import create_db_engine, create_session_factory, init_db
from app.infrastructure.feedback_repository import SqliteStylePreferenceStore
from app.infrastructure.llm_call_tracer import SqliteLLMCallTracer
from app.infrastructure.memory_repository import (
    SqliteEpisodicMemoryStore,
    SqliteLongTermProfileStore,
)
from app.services.ai.router import ExecutionPlanner, resolve_llm_clients_by_tier
from app.shared.errors import AIServiceUnavailableError
from app.shared.llm import LLMClient
from app.shared.llm_factory import LLMFactory
from app.shared.tracing_llm import TracingLLMClient

logger = logging.getLogger(__name__)


@dataclass
class ServiceContainer:
    """Holds long-lived dependencies and builds per-request :class:`ExecutionPlanner` instances."""

    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    llm_factory: LLMFactory
    diary_collection: DiaryCollectionManager
    knowledge_store: DomainKnowledgeStore
    bm25_index: BM25Index
    retriever: HybridRetriever
    episodic_memory: EpisodicMemory
    long_term_memory: LongTermMemory
    working_memory: WorkingMemory
    llm_tracer: SqliteLLMCallTracer
    decision_logger: SqliteAgentDecisionLogger
    style_preference_store: SqliteStylePreferenceStore
    _multi_agent_graph: MultiAgentGraph | None = field(default=None, repr=False)

    @classmethod
    def create(cls, settings: Settings | None = None) -> ServiceContainer:
        cfg = settings or get_settings()
        for path in (
            Path(cfg.data_dir),
            Path(cfg.chroma_persist_dir),
            Path(cfg.models_dir),
            Path(cfg.backups_dir),
            Path(cfg.logs_dir),
        ):
            path.mkdir(parents=True, exist_ok=True)
        engine = create_db_engine(cfg.database_url)
        init_db(engine)
        factory = create_session_factory(engine)

        diary_collection = DiaryCollectionManager(settings=cfg)
        knowledge_store = DomainKnowledgeStore(settings=cfg)
        bm25 = BM25Index()
        retriever = HybridRetriever(
            collection_manager=diary_collection,
            bm25_index=bm25,
        )

        episodic_store = SqliteEpisodicMemoryStore(factory)
        episodic = EpisodicMemory(store=episodic_store, user_id="default")
        try:
            episodic.load()
        except Exception as exc:
            logger.warning("Episodic memory load skipped: %s", exc)

        long_term = LongTermMemory(store=SqliteLongTermProfileStore(factory))
        working = WorkingMemory()

        return cls(
            settings=cfg,
            engine=engine,
            session_factory=factory,
            llm_factory=LLMFactory(cfg),
            diary_collection=diary_collection,
            knowledge_store=knowledge_store,
            bm25_index=bm25,
            retriever=retriever,
            episodic_memory=episodic,
            long_term_memory=long_term,
            working_memory=working,
            llm_tracer=SqliteLLMCallTracer(factory),
            decision_logger=SqliteAgentDecisionLogger(factory),
            style_preference_store=SqliteStylePreferenceStore(factory),
        )

    def session(self) -> Session:
        return self.session_factory()

    def _llm_for_tier(
        self,
        db: Session,
        tier: str,
        *,
        agent_name: str = "execution_planner",
    ) -> LLMClient | None:
        clients = resolve_llm_clients_by_tier(
            db,
            llm_factory=self.llm_factory,
            tracer=self.llm_tracer,
            prefer_active=True,
        )
        if clients:
            return clients.get(tier) or clients.get("default") or next(iter(clients.values()))
        try:
            inner = self.llm_factory.create_default()
            return TracingLLMClient(
                inner,
                model=self.settings.llm_model,
                tier=tier,
                tracer=self.llm_tracer,
                agent_name=agent_name,
            )
        except AIServiceUnavailableError:
            return None

    def build_multi_agent_graph(self, db: Session) -> MultiAgentGraph | None:
        if self._multi_agent_graph is not None:
            return self._multi_agent_graph

        llm = self._llm_for_tier(db, "heavy", agent_name="supervisor")
        if llm is None:
            return None

        model_name = getattr(llm, "model", self.settings.llm_model)
        supervisor = SupervisorAgent(
            IntentClassifier(llm, model=model_name),
            create_default_registry(),
            llm=llm,
            model=model_name,
            decision_logger=self.decision_logger,
            llm_tracer=self.llm_tracer,
        )
        graph = create_multi_agent_graph(
            supervisor,
            EmpathyAgent(
                self._llm_for_tier(db, "medium", agent_name="empathy") or llm,
                self.knowledge_store,
                model=model_name,
                tracer=self.llm_tracer,
            ),
            RetrievalAgent(self.retriever, self.knowledge_store),
            InsightAgent(
                self._llm_for_tier(db, "heavy", agent_name="insight") or llm,
                self.knowledge_store,
                model=model_name,
                tracer=self.llm_tracer,
            ),
        )
        self._multi_agent_graph = graph
        return graph

    def build_execution_planner(self, db: Session) -> ExecutionPlanner:
        llm_by_tier = resolve_llm_clients_by_tier(
            db,
            llm_factory=self.llm_factory,
            tracer=self.llm_tracer,
            prefer_active=True,
        )
        if not llm_by_tier:
            try:
                default = self.llm_factory.create_default()
                wrapped = TracingLLMClient(
                    default,
                    model=self.settings.llm_model,
                    tier="default",
                    tracer=self.llm_tracer,
                )
                llm_by_tier = {
                    "light": wrapped,
                    "medium": wrapped,
                    "heavy": wrapped,
                    "default": wrapped,
                }
            except AIServiceUnavailableError:
                llm_by_tier = {}

        graph = self.build_multi_agent_graph(db) if llm_by_tier else None
        return ExecutionPlanner(
            llm_by_tier=llm_by_tier,
            multi_agent_graph=graph,
            retriever=self.retriever,
            episodic=self.episodic_memory,
            long_term=self.long_term_memory,
            working_memory=self.working_memory,
            decision_logger=self.decision_logger,
            db=db,
            multi_agent_enabled=graph is not None,
        )

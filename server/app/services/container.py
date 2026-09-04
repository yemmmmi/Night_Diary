"""Service-layer dependency container — wires domain + infrastructure for C-1."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.infrastructure.agent_decision_logger import SqliteAgentDecisionLogger
from app.infrastructure.database import create_db_engine, create_session_factory, init_db
from app.infrastructure.feedback_repository import SqliteStylePreferenceStore
from app.infrastructure.llm_call_tracer import SqliteLLMCallTracer
from app.infrastructure.memory_repository import (
    SqliteEpisodicMemoryStore,
    SqliteLongTermProfileStore,
)
from app.infrastructure.skill_activation_tracer import SqliteSkillActivationTracer
from app.shared.embeddings import build_embedding_function
from app.shared.errors import AIServiceUnavailableError
from app.shared.llm import LLMClient
from app.shared.llm_factory import LLMFactory
from app.shared.tracing_llm import TracingLLMClient

# Heavy AI/RAG imports deferred to TYPE_CHECKING so that ``create_core``
# (diary CRUD only) doesn't trigger langchain / chromadb / torch loads.
# These modules are imported lazily inside methods that actually need them.
if TYPE_CHECKING:
    from app.domain.agents.chat_intent_classifier import ChatIntentClassifier
    from app.domain.agents.graph import MultiAgentGraph
    from app.domain.knowledge.store import DomainKnowledgeStore
    from app.domain.memory.episodic import EpisodicMemory
    from app.domain.memory.long_term import LongTermMemory
    from app.domain.memory.working import WorkingMemory
    from app.domain.rag.bm25 import BM25Index
    from app.domain.rag.card_collections import CardCollectionManager
    from app.domain.rag.collections import DiaryCollectionManager
    from app.domain.rag.reranker import Reranker
    from app.domain.rag.retriever import HybridRetriever
    from app.services.ai.router import ExecutionPlanner
    from app.services.ai.tool_registry import ToolRegistry
    from app.shared.embed_utils import Embedder

logger = logging.getLogger(__name__)


@dataclass
class ServiceContainer:
    """Holds long-lived dependencies and builds per-request :class:`ExecutionPlanner` instances."""

    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    llm_factory: LLMFactory
    llm_tracer: SqliteLLMCallTracer
    decision_logger: SqliteAgentDecisionLogger
    style_preference_store: SqliteStylePreferenceStore
    skill_tracer: SqliteSkillActivationTracer | None = field(default=None, repr=False)
    diary_collection: DiaryCollectionManager | None = field(default=None, repr=False)
    card_collection: CardCollectionManager | None = field(default=None, repr=False)
    knowledge_store: DomainKnowledgeStore | None = field(default=None, repr=False)
    bm25_index: BM25Index | None = field(default=None, repr=False)
    retriever: HybridRetriever | None = field(default=None, repr=False)
    episodic_memory: EpisodicMemory | None = field(default=None, repr=False)
    long_term_memory: LongTermMemory | None = field(default=None, repr=False)
    working_memory: WorkingMemory | None = field(default=None, repr=False)
    _multi_agent_graph: MultiAgentGraph | None = field(default=None, repr=False)
    _chat_intent_classifier: ChatIntentClassifier | None = field(default=None, repr=False)
    _chat_skill_registry: Any | None = field(default=None, repr=False)
    _conversation_graph: Any | None = field(default=None, repr=False)
    # ── V3 P4: singleton caches for embedder + reranker (shared across users) ──
    _embedder: Embedder | None = field(default=None, repr=False)
    _reranker_cache: Reranker | None = field(default=None, repr=False)
    _reranker_resolved: bool = field(default=False, repr=False)
    _ai_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    tool_registry: ToolRegistry | None = field(default=None, repr=False)
    _registry_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def create_core(cls, settings: Settings | None = None) -> ServiceContainer:
        """Fast path: SQLite + tracers only (diary CRUD). AI stack loads lazily."""
        import time as _time

        t0 = _time.perf_counter()
        cfg = settings or get_settings()
        for path in (
            Path(cfg.data_dir),
            Path(cfg.chroma_persist_dir),
            Path(cfg.models_dir),
            Path(cfg.backups_dir),
            Path(cfg.logs_dir),
        ):
            path.mkdir(parents=True, exist_ok=True)
        t_dirs = _time.perf_counter()

        engine = create_db_engine(cfg.database_url)
        t_engine = _time.perf_counter()

        init_db(engine)
        t_init = _time.perf_counter()

        factory = create_session_factory(engine)
        t_factory = _time.perf_counter()

        container = cls(
            settings=cfg,
            engine=engine,
            session_factory=factory,
            llm_factory=LLMFactory(cfg),
            llm_tracer=SqliteLLMCallTracer(factory),
            decision_logger=SqliteAgentDecisionLogger(factory),
            style_preference_store=SqliteStylePreferenceStore(factory),
            skill_tracer=SqliteSkillActivationTracer(factory),
        )
        t_tracers = _time.perf_counter()

        import logging

        logging.getLogger(__name__).info(
            "create_core: dirs=%.2fs engine=%.2fs init_db=%.2fs factory=%.2fs tracers=%.2fs total=%.2fs",
            t_dirs - t0,
            t_engine - t_dirs,
            t_init - t_engine,
            t_factory - t_init,
            t_tracers - t_factory,
            t_tracers - t0,
        )
        return container

    def _ensure_memory_layers_locked(self, *, user_id: str = "default") -> None:
        """Initialise the three in-process memory layers (cheap, SQLite-backed).

        Must be called while holding ``self._ai_lock``. Idempotent — once
        initialised, subsequent calls are no-ops (the first ``user_id`` wins).

        V3 P4: injects a singleton :class:`BgeEmbedder` (vector retrieval)
        and the shared :class:`Reranker` (cross-encoder reranking) into
        :class:`EpisodicMemory`, enabling two-stage vector retrieval + optional
        Stage-3 rerank. Both deps degrade gracefully when ``None`` (model
        unavailable) — ``EpisodicMemory`` falls back to char-Jaccard similarity.
        """
        if self.episodic_memory is not None:
            return

        from app.domain.memory.episodic import EpisodicMemory
        from app.domain.memory.long_term import LongTermMemory
        from app.domain.memory.working import WorkingMemory

        episodic_store = SqliteEpisodicMemoryStore(self.session_factory)
        embedder = self._build_embedder()
        reranker = self._get_reranker()
        episodic = EpisodicMemory(
            store=episodic_store,
            user_id=user_id,
            embedder=embedder,
            reranker=reranker,
        )
        try:
            episodic.load()
        except Exception as exc:
            logger.warning("Episodic memory load skipped: %s", exc)

        self.episodic_memory = episodic
        self.long_term_memory = LongTermMemory(
            store=SqliteLongTermProfileStore(self.session_factory)
        )
        self.working_memory = WorkingMemory()

    def _ensure_card_collection_locked(self) -> None:
        """Initialise the card Chroma collection. Hold ``self._ai_lock``. Idempotent."""
        if self.card_collection is None:
            from app.domain.rag.card_collections import CardCollectionManager

            self.card_collection = CardCollectionManager(
                settings=self.settings,
                embedding_function=build_embedding_function(self.settings),
            )

    def ensure_tool_registry(self) -> ToolRegistry | None:
        """Create the ToolRegistry (local + MCP tools) once, lazily.

        Separate lock from ``_ai_lock`` so the Dev API can build the registry
        without loading the full AI stack. With no MCP endpoints configured
        this is nearly free.
        """
        if self.tool_registry is not None:
            return self.tool_registry
        with self._registry_lock:
            if self.tool_registry is None:
                from app.services.ai.tool_registry import ToolRegistry

                registry = ToolRegistry(self, self.settings)
                registry.initialize()
                self.tool_registry = registry
        return self.tool_registry

    def ensure_memory(self, *, user_id: str = "default") -> None:
        """Lightweight path for card flows: three-layer memory + card collection.

        Avoids loading the full RAG/agent stack (knowledge store, BM25, retriever,
        diary collection, graph) on first card creation/search. Idempotent.
        """
        if self.episodic_memory is not None and self.card_collection is not None:
            return

        with self._ai_lock:
            self._ensure_memory_layers_locked(user_id=user_id)
            self._ensure_card_collection_locked()

    def ensure_ai_stack(self, *, user_id: str = "default") -> None:
        """Load RAG / memory / agent graph (heavy — defer until first AI call)."""
        if self.diary_collection is not None:
            return

        with self._ai_lock:
            if self.diary_collection is not None:
                return

            cfg = self.settings
            from app.domain.knowledge.store import DomainKnowledgeStore
            from app.domain.rag.bm25 import BM25Index
            from app.domain.rag.collections import DiaryCollectionManager
            from app.domain.rag.retriever import HybridRetriever

            embedding_fn = build_embedding_function(cfg)
            diary_collection = DiaryCollectionManager(
                settings=cfg,
                embedding_function=embedding_fn,
            )
            self._ensure_card_collection_locked()
            knowledge_store = DomainKnowledgeStore(settings=cfg)
            bm25 = BM25Index()
            reranker = self._get_reranker()
            retriever = HybridRetriever(
                collection_manager=diary_collection,
                bm25_index=bm25,
                reranker=reranker,
            )

            self._ensure_memory_layers_locked(user_id=user_id)

            self.diary_collection = diary_collection
            self.knowledge_store = knowledge_store
            self.bm25_index = bm25
            self.retriever = retriever
            self.ensure_tool_registry()
            logger.info("AI stack ready (RAG + memory + agents)")

    def _build_embedder(self) -> Embedder:
        """Build the episodic-memory embedder as a process-wide singleton.

        Cloud-first, mirroring :func:`app.shared.embeddings.build_embedding_function`:
        when ``embedding_api_key`` is configured, episodic vector search calls the
        same OpenAI-compatible ``/embeddings`` endpoint instead of a local model
        (no ``sentence-transformers`` runtime needed). Without a key it falls
        back to the local :class:`BgeEmbedder` (requires the ``[eval]`` extra;
        the model loads lazily on the first ``embed`` call).
        """
        if self._embedder is None:
            if self.settings.embedding_api_key:
                from app.shared.embed_utils import ApiEmbedder

                self._embedder = ApiEmbedder(
                    api_key=self.settings.embedding_api_key,
                    base_url=self.settings.embedding_base_url,
                    model=self.settings.embedding_model,
                )
            else:
                from app.shared.embed_utils import BgeEmbedder

                self._embedder = BgeEmbedder()
        return self._embedder

    def _get_reranker(self) -> Reranker | None:
        """Return the cached reranker, building it on first access.

        The cross-encoder is shared between RAG hybrid retrieval
        (:class:`HybridRetriever`) and episodic memory Stage-3 reranking
        (:meth:`Reranker.rerank_episodic`). Cached so the model loads at most
        once per container lifetime.

        Returns ``None`` when the model is unavailable (graceful degradation);
        callers must handle ``None`` — both ``HybridRetriever`` and
        ``EpisodicMemory`` skip reranking when the reranker is ``None``.

        The ``_reranker_resolved`` flag distinguishes "built but None" (model
        unavailable) from "not yet built", preventing repeated expensive load
        attempts on every call.
        """
        if not self._reranker_resolved:
            self._reranker_cache = self._build_reranker(self.settings)
            self._reranker_resolved = True
        return self._reranker_cache

    @staticmethod
    def _build_reranker(cfg: Settings) -> Reranker | None:
        """Build a reranker from local model weights, gracefully degrade to None.

        Looks for a fine-tuned reranker under ``models_dir/reranker-night-diary``;
        falls back to the base ``BAAI/bge-reranker-base`` if the fine-tuned
        directory is absent. Any load failure is caught and logged — the
        retriever still works without reranking (RRF-fused order is returned).

        Returns ``None`` immediately (single info log, no load attempt) when
        ``sentence-transformers`` is not installed — the ``[eval]`` extra is
        optional at runtime, and the reranker is a pure local-model feature
        with no cloud equivalent.
        """
        import importlib.util

        if importlib.util.find_spec("sentence_transformers") is None:
            logger.info(
                "sentence-transformers not installed; cross-encoder reranking "
                "disabled (install the [eval] extra and model weights to enable)"
            )
            return None

        fine_tuned = Path(cfg.models_dir) / "reranker-night-diary"
        model_name = str(fine_tuned) if fine_tuned.exists() else "BAAI/bge-reranker-base"
        from app.domain.rag.reranker import Reranker

        try:
            return Reranker(model_name=model_name, local_files_only=True)
        except Exception as exc:
            logger.warning("Reranker init skipped (%s); degrading to no-rerank: %s", model_name, exc)
            return None

    def warmup_models(self) -> None:
        """Preload embedding + reranker models (best-effort, non-blocking on failure).

        Triggered as a background task after core bootstrap so the first real
        AI request doesn't pay the 3-8s cold-start penalty (model download +
        ``sentence-transformers`` load). Each stage is independently wrapped:
        any failure is logged as a warning and skipped — startup, ``/ready``,
        and request handling are never blocked.
        """
        import time as _t

        t0 = _t.perf_counter()
        try:
            self.ensure_ai_stack()
            embedder = self._build_embedder()
            embedder.embed("预热")
            logger.info("Embedder warmed up in %.2fs", _t.perf_counter() - t0)
        except Exception as exc:
            logger.warning("Embedder warmup failed (non-fatal): %s", exc)
        try:
            reranker = self._get_reranker()
            if reranker is None:
                logger.info("Reranker unavailable; skipping reranker warmup")
            else:
                from app.domain.memory.types import EpisodicEntry

                dummy = EpisodicEntry(
                    event_summary="预热",
                    emotion="neutral",
                    reply_insight="",
                    timestamp=_t.time(),
                    importance=0.6,
                )
                reranker.rerank_episodic("预热", [dummy])
                logger.info("Reranker warmed up in %.2fs", _t.perf_counter() - t0)
        except Exception as exc:
            logger.warning("Reranker warmup failed (non-fatal): %s", exc)

    @classmethod
    def create(cls, settings: Settings | None = None) -> ServiceContainer:
        """Full container for tests and the production backend."""
        core = cls.create_core(settings)
        core.ensure_ai_stack()
        return core

    def session(self) -> Session:
        return self.session_factory()

    def _llm_for_tier(
        self,
        tier: str,
        *,
        agent_name: str = "execution_planner",
    ) -> LLMClient | None:
        """Resolve an LLM client for a given tier using a short-lived session.

        The DB query (reading model_providers rows) is a quick operation, so
        we open a dedicated session, fetch the config, and close it immediately
        — the connection is released back to the pool before this method
        returns.  This avoids holding a connection during long LLM calls.
        """
        from app.services.ai.router import resolve_llm_clients_by_tier

        with self.session_factory() as session:
            clients = resolve_llm_clients_by_tier(
                session,
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

    def get_chat_intent_classifier(
        self, *, user_id: str = "default"
    ) -> ChatIntentClassifier:
        """Get a cached ChatIntentClassifier wired with a light-tier LLM.

        The classifier is stateless beyond its LLM/tracer deps, so one instance
        per container is safe. The light-tier LLM is used for the LLM fallback
        layer (rule layer is zero-token).
        """
        if self._chat_intent_classifier is not None:
            return self._chat_intent_classifier
        from app.domain.agents.chat_intent_classifier import ChatIntentClassifier

        llm = self._llm_for_tier("light", agent_name="chat_intent_classifier")
        self._chat_intent_classifier = ChatIntentClassifier(
            llm=llm,
            tracer=self.llm_tracer,
            model=getattr(llm, "model", self.settings.llm_model) if llm else "",
        )
        return self._chat_intent_classifier

    def get_chat_skill_registry(self) -> Any:
        """Get the cached scene-2 SkillRegistry.

        Shares crisis_detector and sentiment_skill with scene 1, plus
        scene-2-specific skills (memory_recall, entity_tracker).
        """
        if self._chat_skill_registry is not None:
            return self._chat_skill_registry
        from app.domain.skills.registry import create_chat_registry

        self._chat_skill_registry = create_chat_registry(tracer=self.skill_tracer)
        return self._chat_skill_registry

    def get_conversation_graph(self) -> Any:
        """Get the cached conversation StateGraph (LangGraph).

        Returns None if LangGraph is not installed. The graph is compiled
        once and cached for the lifetime of the container.
        """
        if self._conversation_graph is not None:
            return self._conversation_graph
        from app.services.ai.conversation_graph import build_conversation_graph

        self._conversation_graph = build_conversation_graph()
        return self._conversation_graph

    def build_multi_agent_graph(
        self, *, user_id: str = "default"
    ) -> MultiAgentGraph | None:
        self.ensure_ai_stack(user_id=user_id)
        assert self.knowledge_store is not None and self.retriever is not None

        if self._multi_agent_graph is not None:
            return self._multi_agent_graph

        # Lazy imports — only loaded when multi-agent graph is actually built.
        from app.domain.agents.context_compressor import ContextCompressor
        from app.domain.agents.empathy_agent import EmpathyAgent
        from app.domain.agents.graph import create_multi_agent_graph
        from app.domain.agents.insight_agent import InsightAgent
        from app.domain.agents.intent_classifier import IntentClassifier
        from app.domain.agents.retrieval_agent import RetrievalAgent
        from app.domain.agents.supervisor import SupervisorAgent
        from app.domain.skills.registry import create_diary_registry

        llm = self._llm_for_tier("heavy", agent_name="supervisor")
        if llm is None:
            return None

        model_name = getattr(llm, "model", self.settings.llm_model)
        supervisor = SupervisorAgent(
            IntentClassifier(llm, model=model_name),
            create_diary_registry(tracer=self.skill_tracer),
            llm=llm,
            model=model_name,
            decision_logger=self.decision_logger,
            llm_tracer=self.llm_tracer,
        )
        context_compressor = ContextCompressor(llm=llm)
        graph = create_multi_agent_graph(
            supervisor,
            EmpathyAgent(
                self._llm_for_tier("medium", agent_name="empathy") or llm,
                self.knowledge_store,
                model=model_name,
                tracer=self.llm_tracer,
            ),
            RetrievalAgent(self.retriever, self.knowledge_store),
            InsightAgent(
                self._llm_for_tier("heavy", agent_name="insight") or llm,
                self.knowledge_store,
                model=model_name,
                tracer=self.llm_tracer,
            ),
            context_compressor=context_compressor,
        )
        self._multi_agent_graph = graph
        return graph

    def build_execution_planner(self, *, user_id: str = "default") -> ExecutionPlanner:
        from app.services.ai.router import ExecutionPlanner, resolve_llm_clients_by_tier

        self.ensure_ai_stack(user_id=user_id)
        assert (
            self.retriever is not None
            and self.episodic_memory is not None
            and self.long_term_memory is not None
            and self.working_memory is not None
        )

        # Use a short-lived session for LLM client resolution so the
        # connection is released immediately (before any LLM network call).
        with self.session_factory() as session:
            llm_by_tier = resolve_llm_clients_by_tier(
                session,
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

        graph = self.build_multi_agent_graph(user_id=user_id) if llm_by_tier else None
        return ExecutionPlanner(
            llm_by_tier=llm_by_tier,
            multi_agent_graph=graph,
            retriever=self.retriever,
            episodic=self.episodic_memory,
            long_term=self.long_term_memory,
            working_memory=self.working_memory,
            decision_logger=self.decision_logger,
            session_factory=self.session_factory,
            multi_agent_enabled=graph is not None,
        )

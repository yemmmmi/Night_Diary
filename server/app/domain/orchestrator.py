"""Orchestrator protocol — unified interface for both AI scenes.

This module defines a ``runtime_checkable`` Protocol that both scene 1
(diary analysis) and scene 2 (conversation) implement. The protocol enables:

1. **Cross-scene consistency**: both scenes share the same input/output contract.
2. **Shared sub-components**: crisis detection, memory gateway, entity extraction
   are invoked through the same interface.
3. **Future extensibility**: new scenes (e.g., card generation) can implement
   the same protocol.

Design decision: "shared sub-components + independent orchestration".
Each orchestrator wraps its scene-specific execution logic (ExecutionPlanner
for scene 1, ConversationLoop for scene 2) but exposes the same interface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SessionType(StrEnum):
    """AI scene type — determines which orchestrator to use."""

    DIARY = "diary"
    CHAT = "chat"


@dataclass
class OrchestratorInput:
    """Unified input for both scenes.

    Scene-specific fields are passed via ``context`` to avoid bloating the
    common interface. Required fields are scene-agnostic.

    Attributes:
        content: User input (diary text or chat message).
        user_id: User identifier for multi-tenant isolation.
        session_type: Which scene this input belongs to.
        context: Scene-specific parameters (diary_id, conversation_id,
                 pinned_diaries, style_fragment, etc.).
    """

    content: str
    user_id: str
    session_type: SessionType
    context: dict[str, Any] = field(default_factory=dict)

    # Convenience accessors for common context fields
    @property
    def diary_id(self) -> int | None:
        return self.context.get("diary_id")

    @property
    def conversation_id(self) -> str | None:
        return self.context.get("conversation_id")

    @property
    def style_fragment(self) -> str | None:
        return self.context.get("style_fragment")

    @property
    def pinned_diaries(self) -> list[int]:
        return self.context.get("pinned_diaries", [])

    @property
    def use_graph(self) -> bool:
        return self.context.get("use_graph", True)


@dataclass
class OrchestratorOutput:
    """Unified output from both scenes.

    Attributes:
        reply: AI-generated response text.
        token_info: Token usage breakdown by tier.
        metadata: Scene-specific metadata (intent, skills, tools, citations, etc.).
        error: Error message if orchestration failed (None on success).
    """

    reply: str
    token_info: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.error is None


@runtime_checkable
class OrchestratorProtocol(Protocol):
    """Unified orchestration protocol — both scenes implement this interface.

    Implementations:
    - ``DiaryOrchestrator``: wraps ExecutionPlanner + MultiAgentGraph (scene 1)
    - ``ConversationOrchestrator``: wraps ConversationLoop + preprocessing (scene 2)
    """

    def orchestrate(
        self,
        db: Session,
        container: Any,
        input: OrchestratorInput,
    ) -> OrchestratorOutput:
        """Execute the AI pipeline for the given input.

        Args:
            db: Database session.
            container: ServiceContainer with all dependencies.
            input: Unified input with content, user_id, session_type, and context.

        Returns:
            OrchestratorOutput with reply, token_info, and metadata.
        """
        ...


class DiaryOrchestrator:
    """Scene-1 orchestrator — wraps ExecutionPlanner + MultiAgentGraph.

    Delegates to ``analysis_service.trigger_analysis`` for the actual execution,
    but converts the result to the unified OrchestratorOutput format.
    """

    def orchestrate(
        self,
        db: Session,
        container: Any,
        input: OrchestratorInput,
    ) -> OrchestratorOutput:
        """Execute diary analysis pipeline.

        Expected context fields:
        - diary_id: int (required)
        - style_fragment: str (optional)
        """
        from app.services.analysis_service import trigger_analysis

        diary_id = input.diary_id
        if diary_id is None:
            return OrchestratorOutput(
                reply="",
                error="diary_id is required for diary orchestration",
            )

        try:
            analysis_row, mem_count = trigger_analysis(
                db,
                diary_id,
                container,
                user_id=input.user_id,
                style_fragment=input.style_fragment,
            )

            return OrchestratorOutput(
                reply=analysis_row.reply or "",
                token_info={
                    "total_tokens_used": getattr(analysis_row, "tokens_used", 0) or 0,
                },
                metadata={
                    "analysis_id": analysis_row.id,
                    "diary_id": diary_id,
                    "mode": getattr(analysis_row, "mode", "unknown"),
                    "memory_count": mem_count,
                    "session_type": SessionType.DIARY.value,
                },
            )
        except Exception as exc:
            logger.error("DiaryOrchestrator failed: %s", exc)
            return OrchestratorOutput(
                reply="抱歉，日记分析暂时不可用，请稍后再试。",
                error=str(exc),
                metadata={"session_type": SessionType.DIARY.value},
            )


class ConversationOrchestrator:
    """Scene-2 orchestrator — wraps ConversationLoop + preprocessing.

    Delegates to ``conversation_ai_service.generate_reply`` for the actual
    execution, but converts the result to the unified OrchestratorOutput format.
    """

    def orchestrate(
        self,
        db: Session,
        container: Any,
        input: OrchestratorInput,
    ) -> OrchestratorOutput:
        """Execute conversation pipeline.

        Expected context fields:
        - conversation_id: str (required)
        - pinned_diaries: list[int] (optional)
        - use_graph: bool (optional, default True)
        """
        from app.services.conversation_ai_service import generate_reply

        conversation_id = input.conversation_id
        if not conversation_id:
            return OrchestratorOutput(
                reply="",
                error="conversation_id is required for chat orchestration",
            )

        try:
            reply_text, token_info, metadata = generate_reply(
                db,
                container,
                conversation_id=conversation_id,
                content=input.content,
                pinned_diaries=input.pinned_diaries,
                user_id=input.user_id,
                use_graph=input.use_graph,
            )

            return OrchestratorOutput(
                reply=reply_text,
                token_info=token_info,
                metadata={
                    **metadata,
                    "conversation_id": conversation_id,
                    "session_type": SessionType.CHAT.value,
                },
            )
        except Exception as exc:
            logger.error("ConversationOrchestrator failed: %s", exc)
            return OrchestratorOutput(
                reply="抱歉，对话服务暂时不可用，请稍后再试。",
                error=str(exc),
                metadata={"session_type": SessionType.CHAT.value},
            )


def get_orchestrator(session_type: SessionType) -> OrchestratorProtocol:
    """Factory: return the appropriate orchestrator for the given session type.

    Args:
        session_type: DIARY or CHAT.

    Returns:
        Orchestrator instance implementing OrchestratorProtocol.
    """
    if session_type == SessionType.DIARY:
        return DiaryOrchestrator()
    elif session_type == SessionType.CHAT:
        return ConversationOrchestrator()
    else:
        raise ValueError(f"Unknown session type: {session_type}")


__all__ = [
    "SessionType",
    "OrchestratorInput",
    "OrchestratorOutput",
    "OrchestratorProtocol",
    "DiaryOrchestrator",
    "ConversationOrchestrator",
    "get_orchestrator",
]

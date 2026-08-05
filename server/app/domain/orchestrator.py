"""编排器协议 — 两个 AI 场景的统一接口。

本模块定义了一个 ``runtime_checkable`` Protocol，由场景 1
（日记分析）和场景 2（对话）共同实现。该协议支持：

1. **跨场景一致性**：两个场景共享相同的输入/输出契约。
2. **共享子组件**：危机检测、记忆网关、实体提取通过同一接口调用。
3. **未来可扩展性**：新场景（例如卡片生成）可实现同一协议。

设计决策："共享子组件 + 独立编排"。
每个编排器封装各自场景的执行逻辑（场景 1 为 ExecutionPlanner，
场景 2 为 ConversationLoop），但对外暴露相同的接口。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SessionType(StrEnum):
    """AI 场景类型 — 决定使用哪个编排器。"""

    DIARY = "diary"
    CHAT = "chat"


@dataclass
class OrchestratorInput:
    """两个场景的统一输入。

    场景特有字段通过 ``context`` 传递，避免公共接口过于臃肿。
    必填字段为场景无关字段。

    Attributes:
        content: 用户输入（日记文本或聊天消息）。
        user_id: 用户标识符，用于多租户隔离。
        session_type: 该输入所属的场景。
        context: 场景特有参数（diary_id、conversation_id、
                 pinned_diaries、style_fragment 等）。
    """

    content: str
    user_id: str
    session_type: SessionType
    context: dict[str, Any] = field(default_factory=dict)

    # 常用 context 字段的便捷访问器
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
        val = self.context.get("pinned_diaries", [])
        return val if isinstance(val, list) else []

    @property
    def use_graph(self) -> bool:
        val = self.context.get("use_graph", True)
        return val if isinstance(val, bool) else True


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
                reply=(analysis_row.diary_entry.reply if analysis_row.diary_entry else "") or "",
                token_info={
                    "total_tokens_used": getattr(analysis_row, "tokens_used", 0) or 0,
                },
                metadata={
                    "analysis_id": analysis_row.id,
                    "diary_id": diary_id,
                    "mode": getattr(analysis_row, "agent_mode", "unknown"),
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
            result = generate_reply(
                db,
                container,
                conversation_id=conversation_id,
                content=input.content,
                diary_ids=input.pinned_diaries,
                user_id=input.user_id,
            )

            return OrchestratorOutput(
                reply=result.reply_text,
                token_info=result.token_info or {},
                metadata={
                    "retrieved_diary_ids": result.retrieved_diary_ids,
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
    "ConversationOrchestrator",
    "DiaryOrchestrator",
    "OrchestratorInput",
    "OrchestratorOutput",
    "OrchestratorProtocol",
    "SessionType",
    "get_orchestrator",
]

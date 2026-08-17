"""Unit tests for session restart recovery from DB (robustness P1-3)."""

from __future__ import annotations

from app.services import conversation_service
from app.services.ai.session_context import SessionContext, get_or_create_session


def _conversation_with_history(db_session, *, user_id: str = "user-1", turns: int = 2) -> str:
    conv = conversation_service.create_conversation(db_session, user_id=user_id)
    for i in range(turns):
        conversation_service.add_message(
            db_session,
            user_id=user_id,
            conversation_id=conv.id,
            role="user",
            content=f"用户第 {i + 1} 轮消息",
        )
        conversation_service.add_message(
            db_session,
            user_id=user_id,
            conversation_id=conv.id,
            role="assistant",
            content=f"回信第 {i + 1} 轮",
        )
    return conv.id


def test_hydrate_from_db_rebuilds_turn_history(db_session) -> None:
    """从 chat_messages 重建 _turn_messages 与 compressed_history。"""
    conv_id = _conversation_with_history(db_session, turns=2)

    ctx = SessionContext(conversation_id=conv_id)
    loaded = ctx.hydrate_from_db(db_session)

    assert loaded is True
    assert len(ctx._turn_messages) == 4  # 2 轮 × (user + assistant)
    assert ctx._turn_messages[0]["role"] == "user"
    assert ctx._turn_messages[0]["content"] == "用户第 1 轮消息"
    assert ctx._turn_messages[-1]["content"] == "回信第 2 轮"
    history = ctx.get_history()
    assert "用户第 2 轮消息" in history
    assert "回信第 2 轮" in history


def test_hydrate_from_db_empty_returns_false(db_session) -> None:
    """无历史消息时返回 False，不产生空历史噪音。"""
    ctx = SessionContext(conversation_id="no-messages-conv")
    assert ctx.hydrate_from_db(db_session) is False
    assert ctx._turn_messages == []


def test_hydrate_ignores_unknown_roles(db_session) -> None:
    """未知 role 按 assistant 处理（容错）。"""
    conv = conversation_service.create_conversation(db_session, user_id="user-1")
    conversation_service.add_message(
        db_session, user_id="user-1", conversation_id=conv.id, role="system", content="系统提示"
    )
    conversation_service.add_message(
        db_session, user_id="user-1", conversation_id=conv.id, role="user", content="你好"
    )

    ctx = SessionContext(conversation_id=conv.id)
    assert ctx.hydrate_from_db(db_session) is True
    roles = [m["role"] for m in ctx._turn_messages]
    assert roles == ["assistant", "user"]  # system 按 assistant 处理


def test_get_or_create_session_restores_from_db_on_restart(
    db_session, stub_container
) -> None:
    """L1/L2 全空时，新会话从 DB 回填历史（重启恢复）。"""
    from app.services.ai.session_context import _sessions, clear_session

    conv_id = _conversation_with_history(db_session, turns=1)

    container = stub_container
    container.session_factory = lambda: db_session  # 复用测试 session

    clear_session(conv_id)  # 清 L1/L2
    _sessions.pop(conv_id, None)

    ctx = get_or_create_session(conv_id, container=container, user_id="user-1")

    assert "用户第 1 轮消息" in ctx.get_history()
    assert "回信第 1 轮" in ctx.get_history()

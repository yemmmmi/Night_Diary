"""API 层的 FastAPI 依赖项。"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, cast

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.infrastructure.auth import decode_access_token, oauth2_scheme
from app.infrastructure.jwt_blacklist import is_blacklisted
from app.infrastructure.models.user import UserRow
from app.services.container import ServiceContainer
from app.shared.context import UserContext
from app.shared.errors import BootstrapNotReadyError, UnauthorizedError


def get_container(request: Request) -> ServiceContainer:
    if not getattr(request.app.state, "bootstrap_done", False):
        raise BootstrapNotReadyError()
    container = request.app.state.container
    if container is None:
        raise BootstrapNotReadyError()
    return cast(ServiceContainer, container)


def get_db(
    container: Annotated[ServiceContainer, Depends(get_container)],
) -> Generator[Session, None, None]:
    session = container.session()
    try:
        yield session
    finally:
        session.close()


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbDep,
) -> UserRow:
    """解码 JWT 并返回当前激活的用户行。"""
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise UnauthorizedError("无效的认证令牌")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("认证令牌已过期或无效") from exc

    # 拒绝黑名单（已吊销）的令牌 -- 支持主动登出。
    jti = payload.get("jti", "")
    if jti and is_blacklisted(jti):
        raise UnauthorizedError("认证令牌已被吊销")

    user = db.get(UserRow, int(user_id))
    if user is None or not user.is_active:
        raise UnauthorizedError("用户不存在或已禁用")
    return user


ContainerDep = Annotated[ServiceContainer, Depends(get_container)]
DbDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[UserRow, Depends(get_current_user)]


def get_user_context(db: DbDep, user: CurrentUserDep) -> UserContext:
    """将数据库会话与已认证用户打包为单一上下文。"""
    return UserContext(db=db, user_id=str(user.id), user=user)


UserContextDep = Annotated[UserContext, Depends(get_user_context)]

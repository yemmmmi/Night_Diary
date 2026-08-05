"""FastAPI dependencies for the API layer."""

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
    """Decode the JWT and return the active user row."""
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise UnauthorizedError("无效的认证令牌")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("认证令牌已过期或无效") from exc

    # Reject blacklisted (revoked) tokens -- supports active logout.
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
    """Bundle the DB session and authenticated user into a single context."""
    return UserContext(db=db, user_id=str(user.id), user=user)


UserContextDep = Annotated[UserContext, Depends(get_user_context)]

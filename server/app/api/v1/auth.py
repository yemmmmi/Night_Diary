"""认证 API 路由：register、login、me。"""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, DbDep
from app.infrastructure.auth import create_access_token, hash_password, verify_password
from app.infrastructure.models.user import UserRow
from app.shared.errors import EmailAlreadyExistsError, UnauthorizedError

router = APIRouter(prefix="/auth", tags=["auth"])

# 简单的邮箱正则 — 避免 ``email-validator`` 额外依赖。
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# ---- 数据模型 ----


class RegisterRequest(BaseModel):
    email: str = Field(pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=6, max_length=128)
    nickname: str = Field(default="", max_length=64)


class UserResponse(BaseModel):
    id: int
    email: str
    nickname: str
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---- 路由 ----


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbDep) -> UserResponse:
    existing = db.query(UserRow).filter(UserRow.email == body.email).first()
    if existing:
        raise EmailAlreadyExistsError(body.email)

    user = UserRow(
        email=body.email,
        nickname=body.nickname or body.email.split("@")[0],
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbDep,
) -> TokenResponse:
    user = db.query(UserRow).filter(UserRow.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise UnauthorizedError("邮箱或密码错误")
    if not user.is_active:
        raise UnauthorizedError("账户已禁用")

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(user: CurrentUserDep) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/logout")
def logout(user: CurrentUserDep, request: Request) -> dict[str, str]:
    """通过将当前 JWT 加入黑名单来实现登出。

    该令牌的 ``jti`` 会被加入黑名单，TTL 等于令牌的剩余有效时长，
    因此携带该令牌的后续请求会通过认证依赖
    （``app.api.deps.get_current_user``）被拒绝。
    """
    import time

    from app.infrastructure.auth import decode_access_token
    from app.infrastructure.jwt_blacklist import blacklist_token

    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "", 1) if auth.startswith("Bearer ") else ""
    payload = decode_access_token(token)
    jti = payload.get("jti", "")
    exp = payload.get("exp", 0)
    remaining = max(0, int(exp - time.time()))
    if jti:
        blacklist_token(jti, remaining)
    return {"message": "已退出登录"}

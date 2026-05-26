"""Application configuration loaded from environment variables.

All sensitive secrets MUST be provided via environment variables or a `.env`
file. No hardcoded fallback values are allowed for required fields, so the
application fails fast at startup if a required secret is missing.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "night-diary-v2"

    # ---- Database ----
    database_url: str = Field(
        ...,
        description="SQLAlchemy URL, e.g. mysql+pymysql://user:pass@host:3306/db",
    )

    # ---- Redis ----
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ---- Security (required, no fallback) ----
    jwt_secret_key: str = Field(..., min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24
    model_key_secret: str = Field(..., min_length=16)

    # ---- CORS ----
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"],
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # ---- Trusted proxies (used by Phase 1 rate limiter / lock) ----
    trusted_proxy_ips: list[str] = Field(default_factory=list)

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def _split_proxies(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # ---- RAG / Knowledge ----
    chroma_persist_dir: str = "./chroma_data"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

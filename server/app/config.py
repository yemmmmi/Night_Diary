"""Application configuration.

All sensitive secrets MUST be provided via environment variables or a ``.env``
file. The application fails fast at startup if a required secret is missing.

The database defaults to SQLite stored under ``DATA_DIR``. For production a
``DATABASE_URL`` environment variable (e.g. ``mysql+pymysql://...``) can be set
to use MySQL or another SQLAlchemy-supported backend instead. JWT-based
authentication and multi-tenant data isolation are enabled; see ``jwt_*``
settings below.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> str:
    if sys.platform == "win32":
        base = os.getenv("APPDATA", os.path.expanduser("~"))
    else:
        base = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return str(Path(base) / "night-diary")


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

    # ---- Paths ----
    data_dir: str = Field(default_factory=_default_data_dir)
    port: int = Field(default=8000, description="TCP port to listen on (--port)")

    # ---- Database ----
    database_url_env: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "database_url_env"),
        description="Explicit database URL (e.g. mysql+pymysql://user:pass@host/db). "
        "If empty, falls back to SQLite under data_dir.",
    )

    @property
    def database_url(self) -> str:
        if self.database_url_env:
            return self.database_url_env
        return f"sqlite:///{self.data_dir}/night_diary.db"

    @property
    def chroma_persist_dir(self) -> str:
        return str(Path(self.data_dir) / "chroma_data")

    @property
    def models_dir(self) -> str:
        return str(Path(self.data_dir) / "models")

    @property
    def backups_dir(self) -> str:
        return str(Path(self.data_dir) / "backups")

    @property
    def logs_dir(self) -> str:
        return str(Path(self.data_dir) / "logs")

    # ---- Redis (optional, for production caching) ----
    redis_url: str = Field(
        default="",
        description="Redis connection URL (e.g. redis://localhost:6379/0). "
        "If empty, falls back to in-memory caching.",
    )

    # ---- Neo4j (optional, for entity graph) ----
    neo4j_url: str = Field(
        default="",
        description="Neo4j connection URL (e.g. neo4j://localhost:7687). "
        "If empty, entity graph falls back to SQLite.",
    )
    neo4j_user: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="neo4j", description="Neo4j password")

    # ---- MCP (optional, for external tool integration) ----
    mcp_endpoints: str = Field(
        default="",
        description="Comma-separated MCP server endpoints (e.g. "
        "http://localhost:8081/sse,http://localhost:8082/sse). "
        "If empty, only built-in tools are available.",
    )

    # ---- Security ----
    model_key_secret: str = Field(
        default="",
        min_length=0,
        description="Fernet key for encrypting LLM API keys at rest",
    )
    jwt_secret_key: str = Field(
        default="",
        description="Secret key for JWT signing. In production, must be set via env var. "
        "In development, falls back to model_key_secret resolution (secrets.key).",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expire_minutes: int = Field(
        default=10080,
        description="JWT token expiration in minutes (default: 7 days)",
    )

    # ---- CORS ----
    cors_origins: str = Field(
        default="",
        description="Comma-separated additional CORS origins (e.g. 'https://app.example.com'). "
        "Loopback (localhost/127.0.0.1) is always allowed.",
    )

    # ---- LLM defaults (can be overridden per provider via ModelProvider table) ----
    llm_api_key: str = Field(default="", description="Default LLM API key")
    llm_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        description="Default LLM base URL",
    )
    llm_model: str = Field(default="deepseek-chat", description="Default LLM model name")

    # ---- Embedding ----
    # Chinese-first default: the diary corpus is Chinese, so a Chinese retrieval
    # model is required for meaningful vector search. Built lazily via
    # ``app.shared.embeddings.build_embedding_function`` and injected through DI;
    # never imported or read with ``os.getenv`` inside domain code.
    embedding_model_name: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        description="Sentence-transformers model name for vector embeddings.",
    )

    # ---- HuggingFace (first-run model download) ----
    hf_endpoint: str = Field(
        default="https://hf-mirror.com",
        description="HuggingFace mirror for embedding/reranker downloads (China-friendly).",
    )

    # ---- 流式输出 (V3 P0) ----
    streaming_enabled: bool = Field(
        default=False,
        description="Enable token-level streaming output for AI replies. "
        "When True, scene-2 conversation uses streaming SSE. When False, "
        "falls back to synchronous full-response (V2 behavior).",
    )

    # ---- 在线质量哨兵 (robustness P1-4) ----
    quality_sentinel_enabled: bool = Field(
        default=False,
        description="Periodically sample real AI replies and grade them with a "
        "judge LLM to detect quality drift. Disabled by default to avoid "
        "surprise LLM costs; enable in production with a configured LLM.",
    )
    quality_sentinel_interval_s: int = Field(
        default=1800,
        ge=60,
        description="Seconds between quality-sentinel sampling scans.",
    )
    quality_sentinel_sample_size: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Number of recent replies sampled per quality scan.",
    )

    # ---- User-mode judgement thresholds (V3.x mode system) ----
    # See docs/superpowers/specs/2026-08-18-v3x-mode-system-design.md sec.3.
    # Weights are "layered signal" semantics, not model-tunable params; the
    # actual judgement is implemented in MoodMonitor as deterministic rules.
    mode_live_emotion_threshold: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Live-emotion criterion C: when the in-turn mood drops "
        "below this value, switch to 'introspection' mode (low = poor).",
    )
    mode_trend_window_days: int = Field(
        default=7,
        ge=1,
        description="Criterion A: number of days in the recent mood-trend window.",
    )
    mode_followup_needs_pending_task: bool = Field(
        default=True,
        description="Criterion B switch: factor pending tasks into 'followup' lean.",
    )
    mode_enable_live_emotion_enhancement: bool = Field(
        default=False,
        description="Optional side-channel emotion enhancement for criterion C "
        "(non-blocking, applied next turn). Runtime switch only; never written "
        "into the system prompt, so the agent never observes C directly.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

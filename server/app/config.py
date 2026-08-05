"""应用配置。

所有敏感密钥必须通过环境变量或 ``.env`` 文件提供。如果缺少必需的密钥，应用会在启动时快速失败。

数据库默认使用存储在 ``DATA_DIR`` 下的 SQLite。对于生产环境，可以设置
``DATABASE_URL`` 环境变量（例如 ``mysql+pymysql://...``）来使用 MySQL 或其他受
SQLAlchemy 支持的后端。已启用基于 JWT 的认证和多租户数据隔离；参见下方的
``jwt_*`` 设置。
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

    # ---- 应用配置 ----
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "night-diary-v2"

    # ---- 路径 ----
    data_dir: str = Field(default_factory=_default_data_dir)
    port: int = Field(default=8000, description="TCP port to listen on (--port)")

    # ---- 数据库 ----
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

    # ---- Redis（可选，用于生产环境缓存）----
    redis_url: str = Field(
        default="",
        description="Redis connection URL (e.g. redis://localhost:6379/0). "
        "If empty, falls back to in-memory caching.",
    )

    # ---- Neo4j（可选，用于实体图）----
    neo4j_url: str = Field(
        default="",
        description="Neo4j connection URL (e.g. neo4j://localhost:7687). "
        "If empty, entity graph falls back to SQLite.",
    )
    neo4j_user: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="neo4j", description="Neo4j password")

    # ---- MCP（可选，用于外部工具集成）----
    mcp_endpoints: str = Field(
        default="",
        description="Comma-separated MCP server endpoints (e.g. "
        "http://localhost:8081/sse,http://localhost:8082/sse). "
        "If empty, only built-in tools are available.",
    )

    # ---- 安全配置 ----
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

    # ---- LLM 默认值（可通过 ModelProvider 表按提供商覆盖）----
    llm_api_key: str = Field(default="", description="Default LLM API key")
    llm_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        description="Default LLM base URL",
    )
    llm_model: str = Field(default="deepseek-chat", description="Default LLM model name")

    # ---- 嵌入 ----
    # 中文优先默认值：日记语料为中文，因此需要中文检索模型才能实现有意义的
    # 向量搜索。通过 ``app.shared.embeddings.build_embedding_function`` 惰性
    # 构建并通过依赖注入注入；永远不要在领域代码中导入或使用 ``os.getenv`` 读取。
    embedding_model_name: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        description="Sentence-transformers model name for vector embeddings.",
    )

    # ---- HuggingFace（首次运行时模型下载）----
    hf_endpoint: str = Field(
        default="https://hf-mirror.com",
        description="HuggingFace mirror for embedding/reranker downloads (China-friendly).",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

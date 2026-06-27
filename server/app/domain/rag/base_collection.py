"""Base class for ChromaDB collection managers.

Holds the shared lifecycle scaffolding (client resolution, collection
kwargs, get/create, count) common to every single-collection manager.
Subclasses only need to provide ``_collection_name`` and
``_collection_description`` plus their domain-specific CRUD methods.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol

from app.config import Settings, get_settings
from app.domain.knowledge.store import get_chroma_client

logger = logging.getLogger(__name__)


class EmbeddingFunction(Protocol):
    def __call__(self, input: list[str]) -> list[list[float]]: ...


class BaseCollectionManager(ABC):
    """Shared lifecycle logic for a single Chroma collection.

    Single-user desktop app: one shared collection, no per-user prefix.
    Write failures are logged and do not raise (SQLite remains source of truth).

    Subclasses must set ``_collection_name`` and ``_collection_description``
    (as class attributes or instance attributes in ``__init__``).
    """

    @property
    @abstractmethod
    def _collection_name(self) -> str: ...

    @property
    @abstractmethod
    def _collection_description(self) -> str: ...

    def __init__(
        self,
        settings: Settings | None = None,
        chroma_client: Any | None = None,
        embedding_function: EmbeddingFunction | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = chroma_client
        self._embedding_function = embedding_function
        self._collection: Any | None = None

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        return get_chroma_client(self._settings.chroma_persist_dir)

    def _collection_kwargs(self) -> dict[str, Any]:
        if self._embedding_function is not None:
            return {"embedding_function": self._embedding_function}
        return {}

    def get_collection(self, *, create: bool = False) -> Any | None:
        """Return the managed collection, optionally creating it."""
        if self._collection is not None:
            return self._collection

        client = self._resolve_client()
        kwargs = self._collection_kwargs()

        try:
            if create:
                self._collection = client.get_or_create_collection(
                    name=self._collection_name,
                    metadata={"description": self._collection_description},
                    **kwargs,
                )
            else:
                self._collection = client.get_collection(
                    name=self._collection_name, **kwargs
                )
        except Exception as exc:
            logger.warning(
                "Collection '%s' unavailable: %s", self._collection_name, exc
            )
            return None

        return self._collection

    def count(self) -> int:
        """Return total chunk count in the collection."""
        collection = self.get_collection(create=False)
        if collection is None:
            return 0
        try:
            return int(collection.count())
        except Exception:
            return 0

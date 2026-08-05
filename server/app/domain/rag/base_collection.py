"""ChromaDB 集合管理器的基类。

持有每个单集合管理器共用的生命周期脚手架（客户端解析、
collection kwargs、get/create、count）。子类只需提供
``_collection_name`` 与 ``_collection_description``，
以及各自的领域特定 CRUD 方法。
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
    """单个 Chroma 集合共享的生命周期逻辑。

    单用户桌面应用：一个共享集合，无按用户前缀。
    写入失败仅记录日志，不会抛出异常（SQLite 仍是数据真源）。

    子类必须设置 ``_collection_name`` 与 ``_collection_description``
    （作为类属性，或在 ``__init__`` 中作为实例属性）。
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
        """返回被管理的集合，可选地创建它。"""
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
                self._collection = client.get_collection(name=self._collection_name, **kwargs)
        except Exception as exc:
            logger.warning("Collection '%s' unavailable: %s", self._collection_name, exc)
            return None

        return self._collection

    def count(self) -> int:
        """返回集合中的 chunk 总数。"""
        collection = self.get_collection(create=False)
        if collection is None:
            return 0
        try:
            return int(collection.count())
        except Exception:
            return 0

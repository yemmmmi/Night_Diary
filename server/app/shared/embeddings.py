"""用于向量检索的嵌入函数工厂。

重量级的 ``chromadb`` / ``sentence-transformers`` 导入放在函数体内，因此
导入本模块永远不会拉入 ``torch`` 或触发模型下载（与
:meth:`app.domain.rag.reranker.Reranker._default_load` 的做法一致）。

调用方从 :class:`~app.config.Settings` 构建嵌入函数，并通过依赖注入将其
注入到 :class:`~app.domain.rag.collections.DiaryCollectionManager` 或
:class:`~app.domain.knowledge.store.DomainKnowledgeStore` 中。领域代码
绝不能直接导入模型，也不能用 ``os.getenv`` 读取模型名称。
"""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings


def build_embedding_function(settings: Settings | None = None) -> Any:
    """返回与 ``embedding_model_name`` 对应的 Chroma 兼容嵌入函数。

    默认使用中文优先模型（``BAAI/bge-small-zh-v1.5``）；日记语料为中文，
    因此英文模型会将向量搜索退化为噪声。返回值满足 Chroma 的
    ``EmbeddingFunction`` 协议，在单个进程内同时用于索引和查询嵌入。
    """
    resolved = settings or get_settings()
    # chromadb 通过 __getattr__ 惰性暴露此类，因此它在运行时可导入，
    # 但对 mypy 的静态分析不可见。
    from chromadb.utils.embedding_functions import (  # type: ignore[attr-defined]
        SentenceTransformerEmbeddingFunction,
    )

    return SentenceTransformerEmbeddingFunction(model_name=resolved.embedding_model_name)

"""Domain knowledge package — ChromaDB store and entity extraction."""

from app.domain.knowledge.extractor import KnowledgeExtractor
from app.domain.knowledge.types import (
    EntityRecord,
    EntityType,
    ExtractionResult,
    KnowledgeCategory,
    KnowledgeHit,
)

__all__ = [
    "DomainKnowledgeStore",
    "EntityRecord",
    "EntityType",
    "ExtractionResult",
    "KnowledgeCategory",
    "KnowledgeExtractor",
    "KnowledgeHit",
    "get_domain_store",
]


def __getattr__(name: str) -> object:
    if name == "DomainKnowledgeStore":
        from app.domain.knowledge.store import DomainKnowledgeStore

        return DomainKnowledgeStore
    if name == "get_domain_store":
        from app.domain.knowledge.store import get_domain_store

        return get_domain_store
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

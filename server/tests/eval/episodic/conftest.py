"""Fixtures for episodic memory retrieval eval (V3 P5).

Loads the fixed 36-entry corpus + 20-query dataset and builds three
:class:`EpisodicMemory` instances that exercise the production
``retrieve_relevant`` three-stage pipeline with different injectables:

* ``jaccard_memory``       — ``embedder=None, reranker=None`` → ``char_jaccard``
  fallback (V1-equivalent single-stage retrieval).
* ``vector_memory``        — ``embedder=BgeEmbedder`` (real mode) or
  ``StubEmbedder`` (stub mode, no ``sentence-transformers``), ``reranker=None``
  → two-stage vector re-ranking.
* ``vector_rerank_memory`` — same embedder + a loaded ``Reranker`` → full
  three-stage pipeline. Skipped when the cross-encoder model cannot load.

All three share the **same** corpus (session-scoped) and a **fixed** ``now`` so
``importance * decay`` is deterministic across runs (no time drift). The
``timestamp_offset_days`` field in the JSON is converted to an absolute
``timestamp`` relative to that fixed ``now``.

This module is intentionally outside CI: ``make eval-episodic`` runs it
manually. Reuses the metrics defined in :mod:`tests.eval.episodic.metrics`
(copied from the RAG suite).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import pytest

DATA_DIR = Path(__file__).parent

logger = logging.getLogger(__name__)

# Fixed "now" captured at import time. All entry timestamps are derived from it
# (``_NOW + offset_days * 86400``) and every ``retrieve_relevant`` call passes
# the same ``now``, so decay is fully deterministic — no flakiness from wall
# clock drift between fixture setup and test execution.
_NOW = time.time()


def _load_entries() -> list[dict[str, Any]]:
    """Load episodic entries, converting ``timestamp_offset_days`` to absolute.

    The dataset stores a relative day offset (negative = past) so the corpus
    ages deterministically from the fixed ``_NOW`` regardless of when the eval
    is checked out. ``timestamp`` becomes ``_NOW + offset_days * 86400``.
    """
    raw = json.loads((DATA_DIR / "episodic_entries.json").read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = []
    for item in raw:
        offset_days = item.get("timestamp_offset_days", -7)
        abs_timestamp = _NOW + offset_days * 86400
        entry = dict(item)
        entry["timestamp"] = abs_timestamp
        entries.append(entry)
    return entries


def _load_test_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases.json").read_text(encoding="utf-8"))


def _populate_memory(mem: Any, entries: list[dict[str, Any]]) -> None:
    """Populate an ``EpisodicMemory`` from raw dicts (shared by all 3 branches).

    Builds ``EpisodicEntry`` objects preserving the stable ``entry_id`` from the
    dataset (``e01``..``e36``) so retrieved ids line up with the gold sets in
    ``test_cases.json``. Entries below the importance threshold are silently
    skipped by ``store()``; far-past entries are later dropped by
    ``purge_stale`` at retrieval time (deterministic given the fixed ``now``).
    """
    from app.domain.memory.types import EpisodicEntry

    for item in entries:
        entry = EpisodicEntry(
            entry_id=item["entry_id"],
            event_summary=item["event_summary"],
            emotion=item.get("emotion", "neutral"),
            reply_insight=item.get("reply_insight", ""),
            importance=item["importance"],
            tags=item.get("tags", []),
            mood_score=item.get("mood_score", 0.5),
            timestamp=item["timestamp"],
            source=item.get("source", "diary"),
            diary_ids=item.get("diary_ids", []),
            emotions=item.get("emotions", []),
        )
        mem.store(entry)


# --------------------------------------------------------------------------- #
# Data + clock fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def episodic_entries() -> list[dict[str, Any]]:
    return _load_entries()


@pytest.fixture(scope="session")
def test_cases() -> list[dict[str, Any]]:
    return _load_test_cases()


@pytest.fixture(scope="session")
def fixed_now() -> float:
    """The fixed ``now`` used both to derive timestamps and to retrieve."""
    return _NOW


# --------------------------------------------------------------------------- #
# Injectable components: embedder (API / Bge / Stub) + reranker (or None)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def real_embed_mode() -> bool:
    """True when cloud embedding API or local sentence-transformers is available."""
    from app.config import get_settings

    if get_settings().embedding_api_key.strip():
        return True
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.fixture(scope="session")
def embedder(real_embed_mode: bool) -> Any:
    """ApiEmbedder / BgeEmbedder in real mode, StubEmbedder in stub mode.

    The stub derives a deterministic SHA-256 vector with no semantic meaning,
    so stub-mode vector numbers are wiring smoke-checks only — they are *not*
    evidence of P4 vectorization ROI. Real mode (cloud API or BGE) validates that.
    """
    from app.config import get_settings

    settings = get_settings()
    if settings.embedding_api_key.strip():
        from app.shared.embed_utils import ApiEmbedder

        logger.info(
            "Vector branch: ApiEmbedder (%s / %s)",
            settings.embedding_base_url,
            settings.embedding_model,
        )
        return ApiEmbedder(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            model=settings.embedding_model,
        )
    if real_embed_mode:
        from app.shared.embed_utils import BgeEmbedder

        logger.info("Vector branch: BgeEmbedder (real mode)")
        return BgeEmbedder()
    from app.shared.embed_utils import StubEmbedder

    logger.info("Vector branch: StubEmbedder (stub mode, no embedding API / sentence-transformers)")
    return StubEmbedder()


@pytest.fixture(scope="session")
def reranker(real_embed_mode: bool) -> Any:
    """Return a usable cloud/local ``Reranker``, or ``None`` when scoring is unavailable.

    Prefers Qwen ``qwen3-rerank`` when a DashScope key is configured; otherwise
    probes the local CrossEncoder. Stub / unavailable cases return ``None`` so
    the eval *skips* the rerank branch rather than recording fallback numbers.
    """
    from app.config import get_settings
    from app.domain.rag.reranker import build_reranker

    candidate = build_reranker(get_settings(), top_k=10, local_files_only=True)
    if candidate is None:
        if not real_embed_mode:
            return None
        logger.warning("Reranker model unavailable; rerank branch will be skipped")
        return None
    if candidate._load_model() is None:  # type: ignore[attr-defined]
        logger.warning("Reranker model unavailable; rerank branch will be skipped")
        return None
    logger.info("Rerank branch: Reranker model loaded (%s)", candidate.model_name)
    return candidate


# --------------------------------------------------------------------------- #
# The three retrieval branches (same corpus, different injectables)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def jaccard_memory(episodic_entries: list[dict[str, Any]]) -> Any:
    """EpisodicMemory with ``char_jaccard`` only (no embedder, no reranker)."""
    from app.domain.memory.episodic import EpisodicMemory

    mem = EpisodicMemory(store=None, user_id="eval", embedder=None, reranker=None)
    _populate_memory(mem, episodic_entries)
    return mem


@pytest.fixture(scope="session")
def vector_memory(
    episodic_entries: list[dict[str, Any]],
    embedder: Any,
) -> Any:
    """EpisodicMemory with an embedder (BGE real / Stub stub), no reranker."""
    from app.domain.memory.episodic import EpisodicMemory

    mem = EpisodicMemory(store=None, user_id="eval", embedder=embedder, reranker=None)
    _populate_memory(mem, episodic_entries)
    return mem


@pytest.fixture(scope="session")
def vector_rerank_memory(
    episodic_entries: list[dict[str, Any]],
    embedder: Any,
    reranker: Any,
) -> Any:
    """EpisodicMemory with embedder + loaded reranker (full 3-stage pipeline).

    Only built when ``reranker`` is not ``None``; the test skips the rerank
    branch otherwise (stub mode / model unavailable).
    """
    from app.domain.memory.episodic import EpisodicMemory

    if reranker is None:
        return None
    mem = EpisodicMemory(store=None, user_id="eval", embedder=embedder, reranker=reranker)
    _populate_memory(mem, episodic_entries)
    return mem


__all__ = [
    "DATA_DIR",
    "embedder",
    "episodic_entries",
    "fixed_now",
    "jaccard_memory",
    "real_embed_mode",
    "reranker",
    "test_cases",
    "vector_memory",
    "vector_rerank_memory",
]

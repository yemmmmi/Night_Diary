"""ContextEngine — pluggable context-management seam for the agent pipeline.

Hermes abstracts context handling behind a ``ContextEngine`` contract with a
built-in compressor as the default implementation, so alternative strategies can
be swapped in per scenario. Night Diary keeps
:class:`~app.domain.agents.context_compressor.ContextCompressor` as the default
engine and exposes this protocol + registry as the extension point:

* :class:`ContextEngine` — the minimal contract (``compress``).
* :func:`register_engine` / :func:`build_context_engine` — name-based selection.
* ``Settings.context_engine`` — picks the engine at wiring time.

Engines are registered by their owning module (see ``context_compressor``), so
``build_context_engine`` only needs to import that module lazily to guarantee the
defaults exist before lookup.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

#: Engine selected when ``Settings.context_engine`` is empty or unknown.
DEFAULT_ENGINE = "compressor"


@runtime_checkable
class ContextEngine(Protocol):
    """Minimal contract every context engine must satisfy.

    Implementations rank/filter/pack history into a token budget and return the
    joined context string. ``candidates`` are raw diary hits, ``episodic`` are
    episodic-memory entries; both are optional.
    """

    name: str

    def compress(
        self,
        current_content: str,
        *,
        candidates: list[dict[str, Any]] | None = None,
        episodic: list[dict[str, Any]] | None = None,
        boost_terms: list[str] | None = None,
    ) -> str: ...


EngineFactory = Callable[..., ContextEngine]

_ENGINES: dict[str, EngineFactory] = {}


def register_engine(name: str, factory: EngineFactory) -> None:
    """Register (or replace) an engine factory under ``name``."""
    _ENGINES[name] = factory


def available_engines() -> list[str]:
    """Return the sorted names of every registered engine."""
    return sorted(_ENGINES)


def build_context_engine(name: str = DEFAULT_ENGINE, **kwargs: Any) -> ContextEngine:
    """Instantiate the engine named ``name``, falling back to the default.

    Unknown names degrade to :data:`DEFAULT_ENGINE` rather than raising, so a
    stale ``Settings.context_engine`` value can never take the pipeline down.
    """
    # Importing the owning module registers the built-in engines.
    from app.domain.agents import context_compressor  # noqa: F401

    factory = _ENGINES.get(name) or _ENGINES.get(DEFAULT_ENGINE)
    if factory is None:  # pragma: no cover - defensive: defaults always register
        raise RuntimeError("no context engine registered")
    return factory(**kwargs)


__all__ = [
    "DEFAULT_ENGINE",
    "ContextEngine",
    "EngineFactory",
    "available_engines",
    "build_context_engine",
    "register_engine",
]
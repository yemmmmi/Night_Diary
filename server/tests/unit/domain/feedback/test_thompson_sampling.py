"""Unit tests for ThompsonSampling."""

from __future__ import annotations

from app.domain.feedback.thompson_sampling import ThompsonSampling
from app.domain.feedback.types import DEFAULT_STYLE, STYLES


def test_sample_style_returns_valid_style(memory_style_store) -> None:
    sampler = ThompsonSampling(store=memory_style_store)
    assert sampler.sample_style("u1") in STYLES


def test_sample_style_favors_high_alpha(memory_style_store) -> None:
    memory_style_store.ensure_preferences("u1", list(STYLES))
    memory_style_store.update_preference("u1", "empathetic", alpha=100.0, beta=1.0)
    for style in STYLES:
        if style != "empathetic":
            memory_style_store.update_preference("u1", style, alpha=1.0, beta=100.0)

    sampler = ThompsonSampling(store=memory_style_store)
    results = [sampler.sample_style("u1") for _ in range(50)]
    assert results.count("empathetic") >= 45


def test_sample_style_default_without_store() -> None:
    sampler = ThompsonSampling(store=None)
    assert sampler.sample_style("u1") == DEFAULT_STYLE


def test_update_reward_positive(memory_style_store) -> None:
    memory_style_store.ensure_preferences("u1", ["empathetic"])
    memory_style_store.update_preference("u1", "empathetic", alpha=3.0, beta=2.0)

    sampler = ThompsonSampling(store=memory_style_store)
    sampler.update_reward("u1", "empathetic", is_positive=True)

    params = sampler.get_style_params("u1")
    assert params["empathetic"] == {"alpha": 4.0, "beta": 2.0}


def test_update_reward_negative(memory_style_store) -> None:
    memory_style_store.ensure_preferences("u1", ["practical"])
    memory_style_store.update_preference("u1", "practical", alpha=2.0, beta=3.0)

    sampler = ThompsonSampling(store=memory_style_store)
    sampler.update_reward("u1", "practical", is_positive=False)

    params = sampler.get_style_params("u1")
    assert params["practical"] == {"alpha": 2.0, "beta": 4.0}


def test_get_style_params_initializes_all_styles(memory_style_store) -> None:
    sampler = ThompsonSampling(store=memory_style_store)
    params = sampler.get_style_params("new-user")
    assert set(params) == set(STYLES)
    assert all(value == {"alpha": 1.0, "beta": 1.0} for value in params.values())


def test_sqlite_store_roundtrip(sqlite_style_store) -> None:
    sampler = ThompsonSampling(store=sqlite_style_store)
    sampler.update_reward("default", "humorous", is_positive=True)
    params = sampler.get_style_params("default")
    assert params["humorous"]["alpha"] == 2.0
    assert params["humorous"]["beta"] == 1.0

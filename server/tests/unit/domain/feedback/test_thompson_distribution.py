"""Statistical tests for Thompson Sampling style distribution."""

from __future__ import annotations

import random
from collections import Counter

import pytest
from scipy.stats import chisquare

from app.domain.feedback.thompson_sampling import ThompsonSampling
from app.domain.feedback.types import STYLES

pytest.importorskip("scipy")


def _expected_counts(
    params: dict[str, tuple[float, float]],
    *,
    seed: int,
    trials: int,
    sample_size: int,
) -> list[float]:
    rng = random.Random(seed)
    counts = Counter({style: 0 for style in STYLES})
    for _ in range(trials):
        style = ThompsonSampling.sample_from_params(params, rng=rng)
        counts[style] += 1
    total = sum(counts.values())
    proportions = [counts[style] / total for style in STYLES]
    return [proportion * sample_size for proportion in proportions]


def test_uniform_prior_distribution_passes_chi_square() -> None:
    params = {style: (1.0, 1.0) for style in STYLES}
    expected = [250.0, 250.0, 250.0, 250.0]

    rng = random.Random(42)
    observed = Counter({style: 0 for style in STYLES})
    for _ in range(1000):
        style = ThompsonSampling.sample_from_params(params, rng=rng)
        observed[style] += 1

    chi2, p_value = chisquare([observed[style] for style in STYLES], expected)
    assert p_value > 0.05, f"chi2={chi2:.3f}, p={p_value:.3f}"


def test_skewed_prior_distribution_matches_beta_params() -> None:
    params = {
        "empathetic": (6.0, 3.0),
        "practical": (4.0, 4.0),
        "philosophical": (3.0, 5.0),
        "humorous": (3.0, 5.0),
    }
    expected = _expected_counts(params, seed=7, trials=100_000, sample_size=1000)
    assert all(count >= 5.0 for count in expected)

    rng = random.Random(42)
    observed = Counter({style: 0 for style in STYLES})
    for _ in range(1000):
        style = ThompsonSampling.sample_from_params(params, rng=rng)
        observed[style] += 1

    chi2, p_value = chisquare([observed[style] for style in STYLES], expected)
    assert p_value > 0.05, f"chi2={chi2:.3f}, p={p_value:.3f}"
    assert observed["empathetic"] > observed["humorous"]

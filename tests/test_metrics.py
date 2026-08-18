"""Tests for the primary outcome measures.

The central test is test_residual_correlation_is_uninformative: it documents,
in executable form, why the originally pre-registered metric was discarded.
"""

import numpy as np
import pytest

from neff.metrics import (
    diversification_benefit,
    effective_panel,
    headroom,
    headroom_ratio,
    variance_reduction,
)
from neff.stats import mean_pairwise_correlation, n_eff


def equicorrelated(rho: float, M: int, T: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    common = rng.normal(size=(T, 1))
    idio = rng.normal(size=(T, M))
    return np.sqrt(rho) * common + np.sqrt(1 - rho) * idio


# --- the rejected metric, documented so it cannot quietly return -------------

def test_residual_correlation_is_uninformative():
    """Correlating residuals after removing the panel mean yields exactly
    -1/(M-1) regardless of the true correlation. This is why 'excess correlation
    over the common component' was removed from the pre-registration."""
    for M in (3, 5, 7):
        values = []
        for rho in (0.0, 0.5, 0.9):
            errors = equicorrelated(rho, M, 6000, seed=M)
            residual = errors - errors.mean(axis=1, keepdims=True)
            values.append(mean_pairwise_correlation(residual))
        # identical across wildly different true correlations, and equal to -1/(M-1)
        assert max(values) - min(values) < 0.01
        assert values[0] == pytest.approx(-1.0 / (M - 1), abs=0.01)


# --- variance reduction ------------------------------------------------------

def test_variance_reduction_matches_one_over_neff():
    """The model-free measure must agree with the analytic one when the
    equicorrelation assumption actually holds."""
    for rho in (0.2, 0.6, 0.9):
        errors = equicorrelated(rho, 7, 6000, seed=3)
        assert variance_reduction(errors) == pytest.approx(1.0 / n_eff(rho, 7), rel=0.12)


def test_independent_panel_reduces_variance_by_one_over_m():
    errors = equicorrelated(0.0, 8, 6000, seed=5)
    assert variance_reduction(errors) == pytest.approx(1.0 / 8, rel=0.2)


def test_identical_forecasters_get_no_benefit():
    rng = np.random.default_rng(7)
    column = rng.normal(size=(500, 1))
    errors = np.repeat(column, 6, axis=1)
    assert variance_reduction(errors) == pytest.approx(1.0, rel=0.05)
    assert diversification_benefit(errors) == pytest.approx(0.0, abs=0.05)


def test_variance_reduction_ignores_rows_with_too_few_responses():
    errors = equicorrelated(0.5, 5, 400, seed=11)
    errors[:50, 1:] = np.nan          # only one model answered these rows
    assert np.isfinite(variance_reduction(errors))


def test_variance_reduction_rejects_bad_shape():
    with pytest.raises(ValueError):
        variance_reduction(np.zeros(10))


# --- headroom ----------------------------------------------------------------

def test_headroom_is_zero_when_panel_is_worth_one_opinion():
    assert headroom(1.0, 7) == pytest.approx(0.0, abs=1e-9)


def test_headroom_scales_with_one_minus_rho_near_saturation():
    """The property that makes the metric usable near rho=1:
    N_eff - 1 ~ ((M-1)/M) * (1 - rho)."""
    M = 7
    for rho in (0.99, 0.995, 0.999):
        expected = (M - 1) / M * (1 - rho)
        assert headroom(rho, M) == pytest.approx(expected, rel=0.02)


def test_headroom_distinguishes_saturated_correlations():
    """0.990 and 0.996 both 'round to 1' but differ threefold in real benefit."""
    a, b = headroom(0.990, 7), headroom(0.996, 7)
    assert a / b == pytest.approx(2.5, rel=0.15)


# --- panel summary and comparison -------------------------------------------

def test_effective_panel_reports_consistent_numbers():
    errors = equicorrelated(0.5, 7, 3000, seed=13)
    summary = effective_panel(errors)
    assert summary.n_forecasters == 7
    assert summary.rho_bar == pytest.approx(0.5, abs=0.05)
    assert summary.n_eff == pytest.approx(1 + summary.headroom, rel=1e-9)
    assert 0.0 < summary.diversification_benefit < 1.0
    assert "removes" in summary.describe()


def test_headroom_ratio_detects_a_more_diverse_reference_panel():
    diverse = equicorrelated(0.90, 7, 800, seed=17)   # more headroom
    tight = equicorrelated(0.99, 7, 800, seed=19)     # less headroom
    result = headroom_ratio(diverse, tight, n_boot=300)
    assert result["ratio"] > 3.0
    assert result["ci_low"] < result["ratio"] < result["ci_high"]
    assert result["n_boot_valid"] > 200


def test_headroom_ratio_near_one_for_matched_panels():
    a = equicorrelated(0.95, 7, 800, seed=21)
    b = equicorrelated(0.95, 7, 800, seed=23)
    result = headroom_ratio(a, b, n_boot=300)
    assert result["ci_low"] < 1.0 < result["ci_high"]

"""Tests for the N_eff estimator and its supporting statistics.

The strategy is to test against cases where the right answer is known
analytically, not just to check the code runs.
"""

import numpy as np
import pytest

from neff.stats import (
    benjamini_hochberg,
    block_bootstrap_ci,
    mean_pairwise_correlation,
    n_eff,
    n_eff_from_errors,
    pairwise_error_correlations,
    signal_error_decomposition,
)


# --- n_eff: the analytic identity -------------------------------------------

def test_n_eff_zero_correlation_equals_panel_size():
    """Independent forecasters: N_eff == M."""
    assert n_eff(0.0, 7) == pytest.approx(7.0)


def test_n_eff_perfect_correlation_collapses_to_one():
    """Identical forecasters are worth exactly one opinion."""
    assert n_eff(1.0, 7) == pytest.approx(1.0)


def test_n_eff_matches_hand_computed_values():
    # 7 / (1 + 6*0.5) = 7/4 = 1.75
    assert n_eff(0.5, 7) == pytest.approx(1.75)
    # 7 / (1 + 6*0.75) = 7/5.5
    assert n_eff(0.75, 7) == pytest.approx(7 / 5.5)
    # The headline arithmetic from the dossier: rho=0.85 -> ~1.15
    assert n_eff(0.85, 7) == pytest.approx(7 / 6.1, rel=1e-9)


def test_n_eff_is_monotonically_decreasing_in_correlation():
    rhos = np.linspace(0.0, 1.0, 50)
    values = [n_eff(r, 7) for r in rhos]
    assert all(a >= b for a, b in zip(values, values[1:]))


def test_n_eff_clamps_below_theoretical_floor():
    """Below rho = -1/(M-1) the equicorrelation matrix is not PSD.

    Without clamping the formula divides by ~zero and returns nonsense; we clamp
    instead of returning inf.
    """
    value = n_eff(-0.9, 3)   # floor for M=3 is -0.5
    assert np.isfinite(value)
    assert value > 0


def test_n_eff_rejects_degenerate_panel():
    with pytest.raises(ValueError):
        n_eff(0.5, 1)


def test_n_eff_nan_propagates():
    assert np.isnan(n_eff(float("nan"), 7))


# --- correlation recovery ---------------------------------------------------

def test_recovers_known_correlation_from_simulated_panel():
    """Build errors with a known equicorrelation and check we recover it."""
    rng = np.random.default_rng(42)
    n_tasks, n_models, true_rho = 4000, 6, 0.6

    common = rng.normal(size=(n_tasks, 1))
    idio = rng.normal(size=(n_tasks, n_models))
    errors = np.sqrt(true_rho) * common + np.sqrt(1 - true_rho) * idio

    estimated = mean_pairwise_correlation(errors)
    assert estimated == pytest.approx(true_rho, abs=0.03)
    assert n_eff_from_errors(errors) == pytest.approx(n_eff(true_rho, n_models), abs=0.15)


def test_independent_errors_give_neff_near_panel_size():
    rng = np.random.default_rng(7)
    errors = rng.normal(size=(3000, 5))
    assert n_eff_from_errors(errors) == pytest.approx(5.0, abs=0.4)


def test_pair_count_is_m_choose_2():
    rng = np.random.default_rng(1)
    errors = rng.normal(size=(200, 7))
    correlations, pairs = pairwise_error_correlations(errors)
    assert len(pairs) == 21          # C(7,2)
    assert correlations.shape == (21,)


# --- missing data handling --------------------------------------------------

def test_missing_data_handled_pairwise_not_by_dropping_tasks():
    """A model skipping a day must not remove that day for everyone.

    This matters scientifically: rate limits cluster on busy market days, which
    are exactly the high-volatility observations our hypothesis is about.
    Listwise deletion would preferentially discard them.
    """
    rng = np.random.default_rng(3)
    errors = rng.normal(size=(400, 4))
    errors[:200, 3] = np.nan        # model 3 missing for the first half

    correlations, pairs = pairwise_error_correlations(errors, min_overlap=3)
    assert len(pairs) == 6          # all pairs still estimable
    assert np.all(np.isfinite(correlations))


def test_pair_dropped_when_overlap_too_small():
    errors = np.full((10, 3), np.nan)
    errors[:, 0] = np.arange(10.0)
    errors[:, 1] = np.arange(10.0) * 0.5
    errors[0:2, 2] = [1.0, 2.0]     # only 2 overlapping points with others
    _, pairs = pairwise_error_correlations(errors, min_overlap=5)
    assert (0, 1) in pairs
    assert (0, 2) not in pairs


def test_zero_variance_leg_is_skipped_not_nan():
    errors = np.zeros((50, 3))
    errors[:, 0] = np.random.default_rng(0).normal(size=50)
    errors[:, 1] = np.random.default_rng(1).normal(size=50)
    # column 2 is constant -> undefined correlation
    correlations, pairs = pairwise_error_correlations(errors)
    assert (0, 1) in pairs
    assert (0, 2) not in pairs
    assert np.all(np.isfinite(correlations))


def test_no_estimable_pairs_returns_nan_not_crash():
    errors = np.zeros((20, 3))      # all constant
    assert np.isnan(mean_pairwise_correlation(errors))


def test_rejects_malformed_input():
    with pytest.raises(ValueError):
        mean_pairwise_correlation(np.zeros(10))            # 1-D
    with pytest.raises(ValueError):
        mean_pairwise_correlation(np.zeros((1, 5)))        # too few tasks
    with pytest.raises(ValueError):
        mean_pairwise_correlation(np.zeros((10, 1)))       # too few forecasters


# --- bootstrap --------------------------------------------------------------

def test_block_bootstrap_interval_brackets_point_estimate():
    rng = np.random.default_rng(11)
    common = rng.normal(size=(300, 1))
    idio = rng.normal(size=(300, 5))
    errors = np.sqrt(0.5) * common + np.sqrt(0.5) * idio

    point, lo, hi = block_bootstrap_ci(errors, n_boot=400, seed=0)
    assert lo <= point <= hi
    assert np.isfinite(lo) and np.isfinite(hi)


def test_block_bootstrap_is_reproducible_given_seed():
    rng = np.random.default_rng(5)
    errors = rng.normal(size=(200, 4))
    a = block_bootstrap_ci(errors, n_boot=200, seed=123)
    b = block_bootstrap_ci(errors, n_boot=200, seed=123)
    assert a == b


def test_block_bootstrap_wider_than_naive_under_autocorrelation():
    """The whole reason we use blocks: with serially dependent data the block
    bootstrap must not understate uncertainty the way block_size=1 does."""
    rng = np.random.default_rng(9)
    n = 400
    # AR(1) common factor -> strong serial dependence across tasks
    common = np.zeros(n)
    for t in range(1, n):
        common[t] = 0.9 * common[t - 1] + rng.normal()
    errors = common[:, None] + rng.normal(size=(n, 5))

    _, lo_blocks, hi_blocks = block_bootstrap_ci(errors, block_size=25, n_boot=400, seed=0)
    _, lo_naive, hi_naive = block_bootstrap_ci(errors, block_size=1, n_boot=400, seed=0)
    assert (hi_blocks - lo_blocks) > (hi_naive - lo_naive)


def test_block_bootstrap_supports_rho_bar_statistic():
    rng = np.random.default_rng(2)
    errors = rng.normal(size=(150, 4))
    point, lo, hi = block_bootstrap_ci(errors, statistic="rho_bar", n_boot=200, seed=1)
    assert -1.0 <= lo <= point <= hi <= 1.0


def test_block_bootstrap_rejects_unknown_statistic():
    errors = np.random.default_rng(0).normal(size=(50, 3))
    with pytest.raises(ValueError):
        block_bootstrap_ci(errors, statistic="nonsense", n_boot=10)


# --- multiple testing -------------------------------------------------------

def test_bh_rejects_nothing_when_all_null():
    p = [0.9, 0.8, 0.75, 0.6, 0.99, 0.5]
    assert not benjamini_hochberg(p, alpha=0.05).any()


def test_bh_rejects_clear_signal():
    p = [1e-8, 1e-7, 0.9, 0.8, 0.7, 0.6]
    reject = benjamini_hochberg(p, alpha=0.05)
    assert reject[0] and reject[1]
    assert not reject[2:].any()


def test_bh_is_less_conservative_than_bonferroni():
    p = [0.001, 0.008, 0.012, 0.20, 0.60]
    bh = benjamini_hochberg(p, alpha=0.05)
    bonferroni = np.asarray(p) <= 0.05 / len(p)
    assert bh.sum() >= bonferroni.sum()


def test_bh_step_up_rejects_below_largest_passing_rank():
    """BH is a step-up procedure: a large p can still be rejected if a later
    ranked one passes. Guards against the common off-by-one implementation."""
    p = [0.01, 0.04]
    reject = benjamini_hochberg(p, alpha=0.05)
    assert reject.all()


def test_bh_handles_empty_and_validates_range():
    assert benjamini_hochberg([]).shape == (0,)
    with pytest.raises(ValueError):
        benjamini_hochberg([0.5, 1.7])


# --- signal vs error decomposition ------------------------------------------

def test_shared_signal_does_not_inflate_error_correlation():
    """The core methodological claim: forecasters who agree because the question
    was answerable are NOT redundant. Raw forecast correlation should be high
    while error correlation stays near zero."""
    rng = np.random.default_rng(21)
    n = 2000
    truth = rng.normal(size=n)
    forecasts = truth[:, None] + 0.3 * rng.normal(size=(n, 5))   # independent errors

    result = signal_error_decomposition(forecasts, truth)
    assert result["forecast_corr"] > 0.85      # they look highly redundant
    assert abs(result["error_corr"]) < 0.10    # but they are not
    assert result["n_eff_error"] > 4.0         # nearly 5 independent opinions
    assert result["n_eff_forecast"] < 2.0      # the naive read would say ~1


def test_shared_error_is_detected():
    rng = np.random.default_rng(22)
    n = 2000
    truth = rng.normal(size=n)
    bias = rng.normal(size=(n, 1))             # a common mistake
    forecasts = truth[:, None] + bias + 0.1 * rng.normal(size=(n, 5))

    result = signal_error_decomposition(forecasts, truth)
    assert result["error_corr"] > 0.8
    assert result["n_eff_error"] < 1.6


def test_decomposition_validates_shapes():
    with pytest.raises(ValueError):
        signal_error_decomposition(np.zeros(10), np.zeros(10))
    with pytest.raises(ValueError):
        signal_error_decomposition(np.zeros((10, 3)), np.zeros(9))

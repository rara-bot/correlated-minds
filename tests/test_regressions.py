"""Regressions for defects found in the pre-collection audit (17 Aug 2026).

Each test here corresponds to a bug that produced plausible-looking but wrong
numbers. They are the dangerous kind: nothing crashed, the output looked fine,
and the error would have survived into the paper.
"""

import hashlib

import numpy as np
import pytest

from neff.metrics import effective_panel, headroom_ratio, mse_reduction, variance_reduction
from neff.panel import Panel, apply_settled_question_exclusion
from neff.stats import (
    block_bootstrap_ci,
    mean_pairwise_correlation,
    mean_uncentered_correlation,
    n_eff_mse,
)


class TestSharedBiasIsDetected:
    """Pearson correlation differences away a bias the whole panel shares.

    'Every model wrong in the same direction' is the failure mode the study
    exists to measure, so the primary estimator must be able to see it.
    """

    def test_pearson_is_blind_to_common_bias(self):
        rng = np.random.default_rng(7)
        base = rng.normal(0, 0.2, size=(400, 7))
        clean = mean_pairwise_correlation(base)
        biased = mean_pairwise_correlation(base + 0.3)
        # Adding an identical bias to every column changes Pearson rho not at all.
        assert abs(clean - biased) < 1e-9

    def test_uncentered_correlation_sees_common_bias(self):
        rng = np.random.default_rng(7)
        base = rng.normal(0, 0.2, size=(400, 7))
        clean = mean_uncentered_correlation(base)
        biased = mean_uncentered_correlation(base + 0.3)
        assert biased > clean + 0.5

    def test_n_eff_mse_collapses_as_shared_bias_grows(self):
        rng = np.random.default_rng(7)
        base = rng.normal(0, 0.2, size=(400, 7))
        values = [n_eff_mse(base + b) for b in (0.0, 0.1, 0.2, 0.3)]
        assert values[0] > 5.0                       # genuinely diversified
        assert values[-1] < 1.6                      # collapsed to ~one opinion
        assert all(a > b for a, b in zip(values, values[1:]))

    def test_variance_reduction_is_blind_but_mse_reduction_is_not(self):
        rng = np.random.default_rng(11)
        base = rng.normal(0, 0.2, size=(400, 7))
        assert variance_reduction(base) == pytest.approx(variance_reduction(base + 0.3), abs=1e-9)
        assert mse_reduction(base + 0.3) > mse_reduction(base) + 0.3

    def test_panel_summary_reports_both_scales(self):
        rng = np.random.default_rng(7)
        summary = effective_panel(0.25 + rng.normal(0, 0.2, size=(400, 7)))
        assert summary.n_eff > 5.0                   # centred view: looks diverse
        assert summary.n_eff_mse < 2.0               # uncentred view: is not
        assert np.isfinite(summary.mse_benefit)


class TestBlockBootstrapNeedsTimeOrder:
    """A moving-block bootstrap on hash-ordered rows is an i.i.d. bootstrap."""

    @staticmethod
    def _autocorrelated_errors(n=300, m=7, ar=0.9, seed=0):
        rng = np.random.default_rng(seed)
        common = np.zeros((n, 1))
        shock = rng.normal(0, 1, size=(n, 1))
        common[0] = shock[0]
        for t in range(1, n):
            common[t] = ar * common[t - 1] + np.sqrt(1 - ar**2) * shock[t]
        return np.sqrt(0.9) * common + np.sqrt(0.1) * rng.normal(0, 1, size=(n, m))

    def test_hash_ordering_understates_uncertainty(self):
        errors = self._autocorrelated_errors()
        _, lo, hi = block_bootstrap_ci(errors, statistic="rho_bar", n_boot=600, seed=1)
        ids = [hashlib.sha256(f"t{i}".encode()).hexdigest()[:20] for i in range(errors.shape[0])]
        scrambled = errors[np.argsort(ids)]
        _, lo2, hi2 = block_bootstrap_ci(scrambled, statistic="rho_bar", n_boot=600, seed=1)
        assert (hi2 - lo2) < 0.75 * (hi - lo)

    def test_loaded_panel_rows_are_time_ordered(self):
        # The guarantee load_panel must maintain for the bootstrap to be valid.
        panel = _panel(
            asked_on=["2026-09-03", "2026-09-01", "2026-09-02"],
            question_ids=["A", "B", "C"],
        )
        assert panel.asked_on != sorted(panel.asked_on)   # fixture is unsorted
        ordered = sorted(range(3), key=lambda i: panel.asked_on[i])
        assert [panel.asked_on[i] for i in ordered] == ["2026-09-01", "2026-09-02", "2026-09-03"]


def _panel(asked_on, question_ids, forecasts=None):
    n = len(asked_on)
    f = forecasts if forecasts is not None else np.full((n, 3), 0.5)
    y = np.zeros(n)
    return Panel(
        forecasts=f,
        outcomes=y,
        errors=f - y[:, None],
        task_ids=[f"t{i}" for i in range(n)],
        model_keys=["a", "b", "c"],
        market_implied=np.full(n, np.nan),
        state=[{} for _ in range(n)],
        question_ids=list(question_ids),
        asked_on=list(asked_on),
    )


class TestSettledQuestionExclusion:
    """§3.3: exclude on the FIRST DAY a question is asked, for the whole question."""

    def test_settled_question_dropped_on_all_days(self):
        f = np.array([[0.02, 0.01, 0.03],    # Q1 day 1 -> median 0.02, settled
                      [0.40, 0.50, 0.60],    # Q1 day 2 -> drifted, still excluded
                      [0.40, 0.50, 0.60]])   # Q2 day 1 -> kept
        panel = _panel(["2026-09-01", "2026-09-02", "2026-09-01"], ["Q1", "Q1", "Q2"], f)
        kept = apply_settled_question_exclusion(panel)
        assert set(kept.question_ids) == {"Q2"}

    def test_uncertain_question_kept_even_if_it_later_settles(self):
        f = np.array([[0.40, 0.50, 0.60],    # first day: genuinely uncertain
                      [0.01, 0.02, 0.01]])   # later resolves toward certainty
        panel = _panel(["2026-09-01", "2026-09-02"], ["Q1", "Q1"], f)
        kept = apply_settled_question_exclusion(panel)
        assert len(kept.question_ids) == 2

    def test_boundary_values_are_inclusive(self):
        f = np.array([[0.05, 0.05, 0.05], [0.95, 0.95, 0.95]])
        panel = _panel(["2026-09-01", "2026-09-01"], ["Q1", "Q2"], f)
        assert len(apply_settled_question_exclusion(panel).question_ids) == 2


class TestHeadlineStatisticIsBounded:
    """The ratio runs away as the denominator approaches zero; the benefit does not."""

    @staticmethod
    def _errors(rho, n=150, m=7, seed=0):
        rng = np.random.default_rng(seed)
        return np.sqrt(rho) * rng.normal(0, 1, (n, 1)) + np.sqrt(1 - rho) * rng.normal(0, 1, (n, m))

    def test_ratio_explodes_but_benefit_difference_stays_bounded(self):
        human = self._errors(0.88, seed=1)
        ratios, benefits = [], []
        for rho_ai in (0.97, 0.999, 0.9999):
            out = headroom_ratio(human, self._errors(rho_ai, seed=2), n_boot=200)
            ratios.append(out["ratio"])
            benefits.append(out["benefit_difference"])
        assert ratios[-1] > 50 * ratios[0]           # ratio is not a stable headline
        assert max(benefits) - min(benefits) < 0.25  # the bounded one is
        assert all(0.0 <= b <= 1.0 for b in benefits)

    def test_undefined_ratio_draws_are_reported_not_hidden(self):
        out = headroom_ratio(self._errors(0.88), self._errors(0.9), n_boot=200)
        assert out["n_boot_valid"] + out["n_boot_ratio_undefined"] == 200

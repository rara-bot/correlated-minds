"""The quantities the plan promises to report ALWAYS had no code (deviation 17).

§4.1 promises `variance_reduction` beside every headroom, §4.2 makes `n_eff_mse`
the primary for the systemic-risk claim, §5.4(a) promises the exact-tie rate and a
tie-free re-estimate, §5.4(b) every estimate by horizon band, §5.4(d) `rho_bar`
raw and disattenuated. `analysis.estimate` produced none of them. These tests hold
that the report composes the registered estimators rather than new ones, and that
each stratum is cut on the variable the plan names.
"""

import numpy as np
import pytest

from neff import report
from neff.metrics import variance_reduction
from neff.panel import Panel
from neff.stats import mean_pairwise_correlation, n_eff_mse

FAST = 30


def _panel(n=60, m=5, seed=0, states=None, days=None, keys=None):
    rng = np.random.default_rng(seed)
    f = rng.uniform(0.05, 0.95, size=(n, m))
    y = rng.integers(0, 2, size=n).astype(float)
    return Panel(
        forecasts=f, outcomes=y, errors=f - y[:, None],
        task_ids=[f"t{i}" for i in range(n)],
        model_keys=keys or [f"m{j}" for j in range(m)],
        market_implied=np.full(n, np.nan),
        state=states or [{"days_out": 5 + (i % 100)} for i in range(n)],
        question_ids=[f"KXS{i % 12}-26OCT-T{i}" for i in range(n)],
        asked_on=days or [f"2026-09-{1 + i % 20:02d}" for i in range(n)],
    )


class TestTheCoPrimaryScales:
    def test_are_the_registered_estimators(self):
        p = _panel()
        out = report.co_primary(p, n_boot=FAST)
        assert out["n_eff_mse"] == pytest.approx(n_eff_mse(p.errors))
        assert out["variance_reduction"] == pytest.approx(variance_reduction(p.errors))
        assert out["rho_bar"] == pytest.approx(round(mean_pairwise_correlation(p.errors), 4))

    def test_carry_both_registered_intervals(self):
        out = report.co_primary(_panel(), n_boot=FAST)
        for key in ("n_eff_mse_intervals", "variance_reduction_intervals"):
            assert {"day_blocked", "event_clustered_registered"} <= set(out[key])

    def test_a_shared_bias_opens_the_gap_the_plan_calls_a_finding(self):
        """§4.2's simulation: Pearson is blind to a bias every model shares."""
        rng = np.random.default_rng(1)
        n, m = 400, 7
        e = rng.normal(0, 0.1, size=(n, m)) + 0.3
        p = Panel(forecasts=e, outcomes=np.zeros(n), errors=e, task_ids=[str(i) for i in range(n)],
                  model_keys=[str(j) for j in range(m)], market_implied=np.full(n, np.nan),
                  state=[{} for _ in range(n)], question_ids=[f"Q{i}-X-1" for i in range(n)],
                  asked_on=["2026-09-01"] * n)
        out = report.co_primary(p, n_boot=0)
        assert out["headroom_pearson"] > 4.0 and out["headroom_mse"] < 0.5
        assert out["gap_headroom_pearson_minus_mse"] > 3.5


class TestTies:
    def test_a_tie_needs_every_responder_and_at_least_two(self):
        f = np.array([[0.7, 0.7, 0.7], [0.7, 0.7, np.nan], [0.7, np.nan, np.nan], [0.7, 0.6, 0.7]])
        p = _panel(n=4, m=3)
        p = Panel(**{**p.__dict__, "forecasts": f, "errors": f - p.outcomes[:, None]})
        assert report.exact_tie_rows(p).tolist() == [True, True, False, False]

    def test_the_rate_is_reported_with_the_distribution(self):
        out = report.emitted_values(_panel())
        assert {"exact_tie_rate", "most_common", "distinct_values"} <= set(out)


class TestDisattenuation:
    def test_perfect_reliability_changes_nothing(self):
        p = _panel()
        rel = {k: {"reliability": 1.0} for k in p.model_keys}
        out = report.disattenuated_rho(p, rel)
        assert out["rho_bar_disattenuated"] == pytest.approx(out["rho_bar_raw"])

    def test_it_is_reported_beside_the_raw_value_never_instead(self):
        p = _panel()
        out = report.disattenuated_rho(p, {k: {"reliability": 0.8} for k in p.model_keys})
        assert "rho_bar_raw" in out and "rho_bar_disattenuated" in out

    def test_a_model_without_replicates_is_left_out_not_guessed(self):
        p = _panel()
        out = report.disattenuated_rho(p, {p.model_keys[0]: {"reliability": 0.9}})
        assert out["pairs_corrected"] == 0


class TestStrata:
    def test_type_b_is_cut_on_the_filing_fields(self):
        states = [({"last_reported_end": "2026-06-30"} if i % 4 == 0 else {"days_out": 20}) for i in range(80)]
        out = report.strata(_panel(n=80, states=states), n_boot=FAST)
        assert out["by_task_type"]["filing"]["n_tasks"] == 20
        assert out["by_task_type"]["event"]["n_tasks"] == 60

    def test_horizon_bands_hold_only_macro_tasks(self):
        states = [({"last_reported_end": "2026-06-30"} if i % 2 else {"days_out": 10}) for i in range(60)]
        out = report.strata(_panel(n=60, states=states), n_boot=FAST)
        assert out["by_horizon_band"]["3-14"]["n_tasks"] == 30

    def test_the_owed_sensitivities_are_present(self):
        keys = ["claude_sonnet", "a", "b", "c", "d"]
        out = report.strata(_panel(keys=keys), n_boot=FAST)
        assert {"without_exact_ties", "without_max_tokens_400_days", "without_claude_sonnet"} \
            <= set(out["sensitivity"])
        assert out["sensitivity"]["without_claude_sonnet"]["n_models"] == 4

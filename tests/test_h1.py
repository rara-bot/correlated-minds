"""H1, the registered primary hypothesis, had no implementation until 2026-09-13.

PREREGISTRATION.md 4 names both of its tests -- a regression of pairwise error
products on the seven standardised state variables, Benjamini-Hochberg across
the seven, each coefficient judged against a registered direction; and headroom
contrasts between terciles of `vix_level` and of `ambiguity` -- and nothing in
the code computed either. The operational details are fixed in deviation 17,
while the driver has only ever run on permuted outcomes. These tests pin those
details and check that each part recovers structure planted in synthetic data.
"""

import math
import re
from pathlib import Path

import numpy as np
import pytest

from neff import h1
from neff.config import STATE_VARIABLES
from neff.panel import Panel

ROOT = Path(__file__).resolve().parent.parent
FAST = 60


def _panel(errors, days=None, refs=None, states=None):
    errors = np.asarray(errors, dtype=float)
    n, m = errors.shape
    outcomes = np.zeros(n)
    return Panel(
        forecasts=errors + outcomes[:, None], outcomes=outcomes, errors=errors,
        task_ids=[f"t{i}" for i in range(n)], model_keys=[f"m{j}" for j in range(m)],
        market_implied=np.full(n, np.nan),
        state=states or [{} for _ in range(n)],
        question_ids=refs or [f"KXS{i % 40}-26OCT-T{i}" for i in range(n)],
        asked_on=days or [f"2026-09-{1 + i % 28:02d}" for i in range(n)],
    )


class TestPairProducts:
    def test_one_product_per_pair_that_both_answered(self):
        e = np.array([[0.1, 0.2, np.nan], [0.3, -0.1, 0.5]])
        y, row = h1.pair_products(e)
        got = sorted(zip(row.tolist(), np.round(y, 6).tolist()))
        assert got == sorted([(0, 0.02), (1, -0.03), (1, 0.15), (1, -0.05)])

    def test_products_are_raw_so_a_shared_bias_counts(self):
        """Centring would difference away the failure §4.2 exists to see."""
        y, _ = h1.pair_products(np.full((4, 3), 0.3))
        assert np.allclose(y, 0.09)


class TestClusterOls:
    def _data(self, seed=1, n=200, groups=25):
        rng = np.random.default_rng(seed)
        X = np.column_stack([np.ones(n), rng.normal(size=n), rng.normal(size=n)])
        clusters = rng.integers(0, groups, size=n)
        shock = rng.normal(size=groups)[clusters]
        y = X @ np.array([0.5, 1.0, -0.3]) + shock + rng.normal(size=n)
        return X, y, clusters

    def test_coefficients_are_ordinary_least_squares(self):
        X, y, cl = self._data()
        fit = h1.cluster_ols(X, y, cl)
        assert np.allclose(fit["beta"], np.linalg.lstsq(X, y, rcond=None)[0])

    def test_standard_errors_are_the_cr1_sandwich(self):
        X, y, cl = self._data()
        fit = h1.cluster_ols(X, y, cl)
        n, k = X.shape
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        resid = y - X @ beta
        bread = np.linalg.inv(X.T @ X)
        meat = np.zeros((k, k))
        for g in np.unique(cl):
            s = X[cl == g].T @ resid[cl == g]
            meat += np.outer(s, s)
        G = len(np.unique(cl))
        cov = (G / (G - 1)) * ((n - 1) / (n - k)) * bread @ meat @ bread
        assert np.allclose(fit["se"], np.sqrt(np.diag(cov)))
        assert fit["df"] == G - 1

    def test_duplicating_rows_inside_their_clusters_does_not_shrink_the_error(self):
        """Re-asking a question daily adds rows, not independent evidence."""
        X, y, cl = self._data()
        once = h1.cluster_ols(X, y, cl)
        twice = h1.cluster_ols(np.vstack([X, X]), np.concatenate([y, y]), np.concatenate([cl, cl]))
        assert np.allclose(twice["se"], once["se"], rtol=0.05)


def _planted(n=300, m=6, slope=1.0, seed=3):
    """Task-days whose shared error component grows with a state variable."""
    rng = np.random.default_rng(seed)
    s = rng.normal(size=n)
    common = rng.normal(size=n) * np.exp(0.5 * slope * s) * 0.2
    errors = common[:, None] + 0.1 * rng.normal(size=(n, m))
    cols = {v: rng.normal(size=n) for v in STATE_VARIABLES}
    cols["vix_level"] = s
    return _panel(errors), cols


class TestTheRegression:
    def test_a_planted_positive_effect_is_found_positive(self):
        panel, cols = _planted(slope=1.0)
        reg = h1.regression(panel, cols, h1.ALWAYS_JOINT, panel.question_ids)
        coef = reg["coefficients"]["vix_level"]
        assert reg["estimable"] and coef["beta"] > 0 and coef["p"] < 0.01

    def test_no_planted_effect_is_not_found(self):
        panel, cols = _planted(slope=0.0, seed=4)
        reg = h1.regression(panel, cols, h1.ALWAYS_JOINT, panel.question_ids)
        assert reg["coefficients"]["vix_level"]["p"] > 0.01

    def test_a_variable_with_no_variation_is_not_estimable(self):
        panel, cols = _planted()
        cols["days_out"] = np.full(panel.n_tasks, 30.0)
        reg = h1.regression(panel, cols, h1.ALWAYS_JOINT, panel.question_ids)
        assert reg["coefficients"]["days_out"] == {"estimable": False, "why_not": "no variation"}

    def test_undefined_rows_are_dropped_not_imputed(self):
        panel, cols = _planted()
        cols["ladder_distance"][: panel.n_tasks // 2] = np.nan
        reg = h1.regression(panel, cols, h1.ALWAYS_JOINT, panel.question_ids)
        assert reg["task_days"] == panel.n_tasks - panel.n_tasks // 2

    def test_too_few_task_days_is_reported_not_fitted(self):
        panel, cols = _planted(n=8)
        assert h1.regression(panel, cols, h1.ALWAYS_JOINT, panel.question_ids)["estimable"] is False


class TestTheSevenStayInTheDenominator:
    @staticmethod
    def _joint(p_by_var):
        return {"coefficients": {
            v: ({"estimable": True, "p": p, "beta": h1.REGISTERED_DIRECTION[v] * 1.0}
                if p is not None else {"estimable": False})
            for v, p in p_by_var.items()}}

    def test_an_untested_variable_still_counts(self):
        """p = 0.0075 survives BH among six (threshold 0.0083) but not among seven
        (0.0071). abs_surprise untested must leave the denominator at seven."""
        p = {v: 1.0 for v in h1.ALWAYS_JOINT}
        p["vix_level"] = 0.0075
        verdicts = h1.judge(self._joint(p), separate=None)
        assert verdicts["abs_surprise"]["verdict"] == "untested"
        assert verdicts["vix_level"]["bh_reject"] is False

    def test_significant_in_the_registered_direction_supports(self):
        p = {v: 1.0 for v in h1.ALWAYS_JOINT}
        p["vix_level"] = 1e-6
        assert h1.judge(self._joint(p), None)["vix_level"]["verdict"] == "supports H1"

    def test_significant_against_the_registered_direction_counts_against(self):
        joint = self._joint({v: 1.0 for v in h1.ALWAYS_JOINT})
        joint["coefficients"]["ladder_distance"] = {"estimable": True, "p": 1e-6, "beta": +2.0}
        assert h1.judge(joint, None)["ladder_distance"]["verdict"] == "against H1"


class TestTheTercileContrast:
    def test_coinciding_cut_points_are_untested_not_estimated(self):
        panel = _panel(np.random.default_rng(0).normal(size=(60, 5)))
        out = h1.tercile_contrast(panel, np.full(60, 14.32), n_boot=FAST)
        assert out["estimable"] is False and "coincide" in out["why_not"]

    def test_lower_headroom_in_the_top_tercile_is_detected(self):
        rng = np.random.default_rng(7)
        n, m = 240, 6
        level = np.arange(n) % 30 / 30.0
        common = rng.normal(size=n)
        weight = np.where(level >= 2 / 3, 0.95, 0.05)        # top tercile: one shared error
        errors = weight[:, None] * common[:, None] + (1 - weight[:, None]) * rng.normal(size=(n, m))
        days = [f"2026-09-{1 + i % 24:02d}" for i in range(n)]
        refs = [f"KXS{i}-26OCT-T1" for i in range(n)]
        out = h1.tercile_contrast(_panel(errors, days=days, refs=refs), level, n_boot=200)
        assert out["estimable"] and out["difference"] < 0
        assert out["lower_headroom_in_top_tercile"] is True

    def test_every_registered_interval_is_reported(self):
        rng = np.random.default_rng(1)
        out = h1.tercile_contrast(_panel(rng.normal(size=(90, 5))), rng.normal(size=90), n_boot=FAST)
        for key in ("day_blocked", "event_clustered_registered", "event_clustered_settlement"):
            assert key in out


class TestLadderValue:
    def test_a_new_row_judges_itself(self):
        assert math.isnan(h1.ladder_value({"event_ladder_size": 0, "event_ladder_distance": None,
                                           "ladder_distance": 0.5}, "X", {}))
        assert h1.ladder_value({"event_ladder_size": 9, "event_ladder_distance": 0.25,
                                "ladder_distance": 0.5}, "X", {}) == 0.5

    def test_an_old_row_is_judged_by_the_snapshot(self):
        snap = {"FED": {"ladder_defined": False}, "CPI": {"ladder_defined": True}}
        assert math.isnan(h1.ladder_value({"ladder_distance": 0.5}, "FED", snap))
        assert h1.ladder_value({"ladder_distance": 0.5}, "CPI", snap) == 0.5

    def test_a_row_nothing_can_judge_is_undefined(self):
        assert math.isnan(h1.ladder_value({"ladder_distance": 0.0}, "UNKNOWN", {}))

    def test_the_per_event_sensitivity_uses_the_events_own_rungs(self):
        snap = {"CPI": {"ladder_defined": True, "strike": 3.0,
                        "event_numeric_rungs": [2.0, 2.5, 3.0, 3.5, 4.0]}}
        assert h1.ladder_value({"ladder_distance": 0.9}, "CPI", snap, per_event=True) == 0.0


class TestAgainstThePlan:
    def test_the_registered_directions_are_the_documents(self):
        doc = (ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8")
        # The table sits inside a bulleted list, so its rows are indented.
        found = dict(re.findall(
            r"^\s*\| `(\w+)` \| [^|]+ \| \**(positive|negative)\** \|\s*$", doc, re.M))
        assert len(found) == 7, f"parsed {len(found)} registered direction(s)"
        assert {k: (+1 if v == "positive" else -1) for k, v in found.items()} \
            == h1.REGISTERED_DIRECTION

    def test_the_driver_runs_blind_on_the_record(self):
        result = h1.run(n_boot=10)
        assert result["blind"] is True
        assert {"regression", "terciles", "h1"} <= set(result) or "why_not" in result


class TestWhatMayBeClaimed:
    """On permuted outcomes and 14 question clusters, the registered regression
    called three variables significant. The claim is therefore the weaker of the
    question- and settlement-clustered verdicts, and small samples say provisional."""

    def test_a_small_sample_is_provisional(self):
        result = h1.run(n_boot=10)
        if "h1" in result and result["h1"]["settlements"] < h1.PROVISIONAL_BELOW_SETTLEMENTS:
            assert result["h1"]["provisional"] is True

    def test_the_claim_is_never_stronger_than_the_registered_verdict(self):
        result = h1.run(n_boot=10)
        if "h1" not in result:
            pytest.skip("no resolved task-days")
        claimed = set(result["h1"]["claim"]["variables_supporting"])
        registered = set(result["h1"]["registered"]["variables_supporting"])
        assert claimed <= registered

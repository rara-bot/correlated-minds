"""The estimator was counting a forecaster that had not forecast anything.

PREREGISTRATION.md §5.6 is one sentence: "If usable coverage falls below 80% for
any model, that model is reported separately and excluded from the primary
panel." It was registered before collection, and it was not in the code.

`analysis.apply_registered_exclusions` held the two ROW rules -- §3.3 settled
questions and deviation 3's stale sources -- under a docstring claiming to hold
"every exclusion that governs the primary estimate". The COLUMN rule was absent,
so the claim was false in the one place built to make it true.

What that cost, measured blind on 2026-09-09: `qwen` lost 2026-09-01 and
2026-09-07 entirely to an upstream host (deviation 4). Every task resolved by
then traced to the 2026-09-07 settlement. So qwen sat at **0.0% coverage inside
a nine-column panel** -- and M is inside the estimator:

    N_eff = M / (1 + (M - 1) * rho_bar)

`stats.n_eff_from_errors` reads M off the column count, while `rho_bar` averages
pairs that clear `min_overlap`. A column of pure NaN contributes nothing to
rho_bar and still raises M, with no NaN, no error and nothing in the log --
overstating the panel's independence, which is the direction that flatters the
headline.

The rule is registered, mechanical, and reads only WHICH cells are filled, never
what is in them. It decides identically on permuted and unpermuted outcomes,
which is what lets `neff.analysis` keep running blind. It cannot be fitted to a
result and there is no model key written anywhere in it.
"""

import numpy as np
import pytest

from neff import analysis
from neff.panel import (
    COVERAGE_FLOOR,
    Panel,
    apply_coverage_exclusion,
    model_coverage,
)

FAST = 40


def _panel(n=20, n_models=4, seed=0, blank=None, cover=None):
    """A panel with controllable per-model missingness.

    `blank`: {model_index: fraction of tasks left NaN}.
    """
    rng = np.random.default_rng(seed)
    f = rng.uniform(0.1, 0.9, size=(n, n_models))
    for j, frac in (blank or {}).items():
        f[: int(round(n * frac)), j] = np.nan
    y = rng.integers(0, 2, size=n).astype(float)
    return Panel(
        forecasts=f,
        outcomes=y,
        errors=f - y[:, None],
        task_ids=[f"t{i}" for i in range(n)],
        model_keys=[f"m{j}" for j in range(n_models)],
        market_implied=np.full(n, np.nan),
        state=[{} for _ in range(n)],
        question_ids=[f"KXSER{i % 4}-26SEP-T{i}" for i in range(n)],
        asked_on=[f"2026-09-{1 + (i % 8):02d}" for i in range(n)],
    )


class TestTheFloorIsTheRegisteredOne:
    def test_the_constant_is_what_section_five_six_says(self):
        assert COVERAGE_FLOOR == 0.80

    def test_coverage_is_the_filled_fraction_of_each_column(self):
        cov = model_coverage(_panel(n=20, blank={0: 0.5}))
        assert cov["m0"] == pytest.approx(0.5)
        assert cov["m1"] == pytest.approx(1.0)

    def test_a_model_below_the_floor_is_dropped(self):
        kept, dropped = apply_coverage_exclusion(_panel(n=20, blank={0: 0.5}))
        assert "m0" not in kept.model_keys
        assert kept.n_models == 3
        assert dropped == {"m0": pytest.approx(0.5)}

    def test_a_model_exactly_at_the_floor_survives(self):
        """"falls below 80%" -- 80% itself is not below it."""
        kept, dropped = apply_coverage_exclusion(_panel(n=20, blank={0: 0.2}))
        assert model_coverage(_panel(n=20, blank={0: 0.2}))["m0"] == pytest.approx(0.8)
        assert "m0" in kept.model_keys
        assert dropped == {}

    def test_a_healthy_panel_is_returned_untouched(self):
        p = _panel(n=20)
        kept, dropped = apply_coverage_exclusion(p)
        assert kept.model_keys == p.model_keys
        assert dropped == {}

    def test_the_columns_that_stay_keep_their_data(self):
        """Dropping a column must not disturb the others -- these are the
        forecasts the primary estimate is computed from."""
        p = _panel(n=20, blank={0: 0.5})
        kept, _ = apply_coverage_exclusion(p)
        np.testing.assert_array_equal(kept.forecasts[:, 0], p.forecasts[:, 1])
        assert kept.n_tasks == p.n_tasks


class TestItCannotProduceAnAbsentPanel:
    def test_a_panel_where_every_model_is_below_the_floor_is_left_alone(self):
        """A panel with no forecasters is not a more conservative estimate, it
        is an absent one. Reported, not silently emptied."""
        p = _panel(n=20, blank={0: 0.9, 1: 0.9, 2: 0.9, 3: 0.9})
        kept, dropped = apply_coverage_exclusion(p)
        assert kept.n_models == 4
        assert set(dropped) == {"m0", "m1", "m2", "m3"}

    def test_an_empty_panel_is_a_no_op(self):
        p = _panel(n=0)
        kept, dropped = apply_coverage_exclusion(p)
        assert kept.n_models == p.n_models
        assert dropped == {}


class TestItCannotUnblindTheAnalysis:
    """`neff.analysis` runs blind by default by permuting outcomes. An exclusion
    that read outcomes would make that blinding a fiction."""

    def test_the_verdict_does_not_depend_on_the_outcomes(self):
        p = _panel(n=20, blank={0: 0.5})
        flipped = Panel(**{**p.__dict__, "outcomes": 1.0 - p.outcomes})
        flipped = Panel(**{**flipped.__dict__,
                           "errors": flipped.forecasts - flipped.outcomes[:, None]})
        assert apply_coverage_exclusion(p)[1] == apply_coverage_exclusion(flipped)[1]

    def test_the_verdict_survives_permutation(self):
        p = _panel(n=20, blank={0: 0.5})
        permuted = analysis._permute_outcomes(p, seed=7)
        assert apply_coverage_exclusion(p)[1].keys() == \
               apply_coverage_exclusion(permuted)[1].keys()


class TestItIsWiredIntoTheOnePlaceThatHoldsThemAll:
    def test_registered_exclusions_apply_the_floor(self):
        p = _panel(n=20, blank={0: 0.5})
        kept, report = analysis.apply_registered_exclusions(p)
        assert "m0" not in kept.model_keys
        assert report["models_below_coverage_floor"] == {"m0": pytest.approx(0.5)}

    def test_coverage_is_measured_after_the_row_rules_not_before(self):
        """A model can be at 100% across everything collected and near zero on
        the tasks that survive. The denominator has to be the surviving panel."""
        p = _panel(n=20, n_models=4, blank={0: 0.5})
        # Every task the first ten -- the ones m0 skipped -- is a dead source.
        for i in range(10):
            p.state[i] = {"asked_on": "2026-09-08", "last_reported_end": "2014-12-31"}
        kept, report = analysis.apply_registered_exclusions(p)
        assert kept.n_tasks == 10
        assert "m0" in kept.model_keys, (
            "m0 answered every surviving task; measuring coverage before the row "
            "rules would have excluded a model that is at 100% of what counts"
        )
        assert report["models_below_coverage_floor"] == {}


class TestTheDriverReportsRatherThanQuietlyDrops:
    """5.6 says "reported separately AND excluded". Half of that is a data loss
    nobody is told about."""

    def test_run_names_the_models_it_removed(self):
        r = analysis.run(blind=True, seed=0, n_boot=FAST)
        assert "models_excluded" in r and "models_before_exclusions" in r

    def test_run_warns_loudly_when_m_changes(self):
        r = analysis.run(blind=True, seed=0, n_boot=FAST)
        if r["models_excluded"]:
            joined = " ".join(r["warnings"])
            assert "5.6 coverage floor" in joined
            assert "M is inside the estimator" in joined
            assert r["n_models"] == len(r["models_before_exclusions"]) - len(
                r["models_excluded"])

    def test_a_provisional_verdict_says_it_is_provisional(self):
        """Excluding a registered panel member off five resolved tasks is
        registered and is applied -- but it is not yet a measurement."""
        r = analysis.run(blind=True, seed=0, n_boot=FAST)
        if r["models_excluded"] and r["n_tasks"] < analysis.COVERAGE_JUDGEMENT_MIN_TASKS:
            assert any("provisional" in w or "not yet a stable" in w
                       for w in r["warnings"])


class TestMAndRhoBarMustDescribeTheSamePanel:
    """The floor catches the ordinary case. This catches the one it cannot: a
    model ABOVE 80% coverage whose answered tasks still overlap nobody else's."""

    def test_a_column_forming_no_estimable_pair_is_named(self):
        p = _panel(n=20, n_models=4)
        # m0 answers only tasks nobody else answers.
        p.forecasts[2:, 0] = np.nan
        p.forecasts[:2, 1:] = np.nan
        p = Panel(**{**p.__dict__,
                     "errors": p.forecasts - p.outcomes[:, None]})
        out = analysis.estimate(p, n_boot=FAST)
        assert "m0" in out["models_without_an_estimable_pair"]
        assert any("contribute nothing to rho_bar" in w for w in out["warnings"])

    def test_a_healthy_panel_names_nobody(self):
        out = analysis.estimate(_panel(n=20), n_boot=FAST)
        assert out["models_without_an_estimable_pair"] == []
        assert not any("estimable pair" in w for w in out["warnings"])

    def test_the_real_panel_is_checked_not_just_synthetic_ones(self):
        """The field this exists for. It must run on the committed record."""
        r = analysis.run(blind=True, seed=0, n_boot=FAST)
        assert "models_without_an_estimable_pair" in r

"""The analysis had never been run end to end, so this runs it.

`stats.py` implemented every registered estimator and `panel.py` implemented
every registered exclusion, but nothing called them together. Both exclusions
were reachable only from tests. On 11 Dec the study would have been assembling
its headline number for the first time, under time pressure, against data that
could no longer be changed -- which is the failure the Week 0 calibration phase
exists to prevent, arriving at the other end of the study.

The first blind run, on the five resolved task-days available on 2026-09-09,
returned N_eff = 17.6 against M = 9 and an interval whose upper bound was
1.1e12. Neither is a bug in the estimator: rho_bar can be negative at this
sample size, and `stats.n_eff` clamps at the -1/(M-1) floor exactly as
documented. Both are values that would have printed.
"""

import numpy as np
import pytest

from neff import analysis
from neff.panel import Panel

FAST = 40          # tests check composition, not resample precision


def _panel(n=20, n_models=9, days=8, events=4, seed=0):
    rng = np.random.default_rng(seed)
    f = rng.uniform(0.1, 0.9, size=(n, n_models))
    y = rng.integers(0, 2, size=n).astype(float)
    return Panel(
        forecasts=f,
        outcomes=y,
        errors=f - y[:, None],
        task_ids=[f"t{i}" for i in range(n)],
        model_keys=[f"m{j}" for j in range(n_models)],
        market_implied=np.full(n, np.nan),
        state=[{} for _ in range(n)],
        question_ids=[f"KXSER{i % events}-26SEP-T{i}" for i in range(n)],
        asked_on=[f"2026-09-{1 + (i % days):02d}" for i in range(n)],
    )


class TestSettlementIdentity:
    """A ladder is one surprise observed many times."""

    def test_ladder_strikes_collapse_to_one_settlement(self):
        rungs = [f"KXAAAGASWNJ-26SEP07-4.1{d}00" for d in range(5, 10)]
        assert len({analysis.resolution_event(r) for r in rungs}) == 1

    def test_a_negative_strike_does_not_split_the_ladder(self):
        """KXPAYROLLS strikes are negative, so the ticker carries an extra
        hyphen. Splitting on the last one would shard the ladder."""
        a = analysis.resolution_event("KXPAYROLLS-26AUG-T-25000")
        b = analysis.resolution_event("KXPAYROLLS-26AUG-T-50000")
        assert a == b == "KXPAYROLLS-26AUG"

    def test_different_expiries_stay_separate(self):
        """August CPI and November CPI are different prints."""
        assert analysis.resolution_event("KXCPIYOY-26AUG-T3.9") != \
               analysis.resolution_event("KXCPIYOY-26NOV-T3.9")

    def test_edgar_refs_are_left_alone(self):
        """One company's next filing is already one event; it has no strike."""
        ref = "edgar:320193:2026-06-27"
        assert analysis.resolution_event(ref) == ref


class TestBothExclusionsAreWired:
    """The December risk this driver exists to remove.

    Each exclusion is registered, each was previously called only from tests,
    and an analysis that forgets one silently readmits exactly what it excluded.
    """

    def test_a_dead_source_task_does_not_survive(self):
        p = _panel(n=6)
        p.state[0] = {"asked_on": "2026-09-08", "last_reported_end": "2014-12-31"}
        kept, _ = analysis.apply_registered_exclusions(p)
        assert kept.n_tasks == 5
        assert "t0" not in kept.task_ids

    def test_a_settled_question_does_not_survive(self):
        p = _panel(n=6, events=6)
        p.forecasts[0, :] = 0.01           # decided on its first (only) day
        p = Panel(**{**p.__dict__, "errors": p.forecasts - p.outcomes[:, None]})
        kept, _ = analysis.apply_registered_exclusions(p)
        assert "t0" not in kept.task_ids

    def test_run_applies_them_and_says_how_many_it_dropped(self):
        r = analysis.run(blind=True, seed=0, n_boot=FAST)
        assert "tasks_excluded" in r and "tasks_before_exclusions" in r


class TestBlindByDefault:
    def test_run_is_blind_unless_asked_otherwise(self):
        assert analysis.run(n_boot=FAST)["blind"] is True

    def test_permutation_keeps_every_shape_that_can_break_the_pipeline(self):
        p = _panel(n=12)
        q = analysis._permute_outcomes(p, seed=1)
        assert q.forecasts.shape == p.forecasts.shape
        assert q.errors.shape == p.errors.shape
        assert q.question_ids == p.question_ids
        assert q.asked_on == p.asked_on
        assert sorted(q.outcomes.tolist()) == sorted(p.outcomes.tolist())

    def test_permutation_recomputes_errors_rather_than_shuffling_them(self):
        """Shuffling the error matrix would carry each row's missingness with
        it and could not produce the structure the real pipeline sees."""
        p = _panel(n=12)
        p.forecasts[3, 2] = np.nan
        p = Panel(**{**p.__dict__, "errors": p.forecasts - p.outcomes[:, None]})
        q = analysis._permute_outcomes(p, seed=1)
        assert np.isnan(q.errors[3, 2]), "NaN moved off the cell that actually failed"
        assert np.allclose(q.errors, q.forecasts - q.outcomes[:, None], equal_nan=True)


class TestNonsenseIsSurfacedNotPrinted:
    def test_the_clamp_floor_is_detected(self):
        assert analysis.clamp_binds(-1.0 / 8, 9) is True
        assert analysis.clamp_binds(0.3, 9) is False

    def test_n_eff_above_m_is_flagged(self):
        """'More independent opinions than forecasters' is not a claim."""
        p = _panel(n=8, seed=3)
        out = analysis.estimate(p, n_boot=FAST)
        if out["point_n_eff"] > p.n_models:
            assert out["n_eff_exceeds_m"] is True
            assert any("exceeds M" in w for w in out["warnings"])

    def test_a_single_settlement_is_called_out(self):
        p = _panel(n=5, events=1, days=1)
        out = analysis.estimate(p, n_boot=FAST)
        assert out["distinct_events"] == 1
        assert any("independent observation" in w for w in out["warnings"])

    def test_too_few_days_for_a_five_day_block_is_called_out(self):
        p = _panel(n=6, days=2, events=6)
        out = analysis.estimate(p, n_boot=FAST)
        assert any("degenerate" in w for w in out["warnings"])


class TestBothRegisteredIntervalsAreProduced:
    def test_5_2_requires_them_together_and_never_alone(self):
        out = analysis.estimate(_panel(n=40, days=8, events=6), n_boot=FAST)
        assert "day_blocked" in out
        assert "event_clustered_registered" in out

    def test_the_registered_interval_clusters_on_source_ref_as_written(self):
        """5.2 operationalises the clustered interval on source_ref. 9 gives up
        the right to revise it, so it is computed as registered even though
        deviation 5 records that source_ref splits the ladders it names."""
        p = _panel(n=20, events=4)
        out = analysis.estimate(p, n_boot=FAST)
        assert out["distinct_questions"] == 20      # source_ref: one per strike
        assert out["distinct_events"] == 4          # settlements: one per ladder
        assert "event_clustered_settlement" in out

    def test_headroom_is_n_eff_minus_one_on_every_bound(self):
        out = analysis.estimate(_panel(n=40, days=8, events=6), n_boot=FAST)
        for key in ["day_blocked", "event_clustered_registered"]:
            v = out[key]
            assert v["headroom"] == pytest.approx(v["n_eff"] - 1.0)
            assert v["headroom_lo"] == pytest.approx(v["n_eff_lo"] - 1.0)
            assert v["headroom_hi"] == pytest.approx(v["n_eff_hi"] - 1.0)


def test_the_registered_resample_count_is_still_2000():
    """n_boot is injectable so the suite stays fast. The registered value is
    2000 (§5.2) and it is what production uses -- pinned here so a convenience
    default can never quietly become the study's."""
    assert analysis.N_BOOT == 2000
    assert analysis.BLOCK_DAYS == 5
    assert analysis.ALPHA == 0.05

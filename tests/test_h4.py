"""H4 had no implementation until 2026-09-14.

Deviation 20 fixes the benefit, the human draws, the horizons, the accuracy strata and
the verdict. These tests check that the human draws are the ones behind the registered
table, pin the strata and the verdict rule, and check that a panel sharing its error
comes out behind independent humans.
"""

import numpy as np
import pytest

from neff import h4
from neff.panel import Panel
from neff.sources import spf

FAST = 40
POINT = {"benefit": 0.0, "headroom": 0.1}
AI = {"event_clustered_registered": np.zeros((4, 2))}


def _rows(signs, overlaps=None, uninformative=None):
    return {h: {"matched_accuracy": {"claimed_sign": s,
                                     "accuracy_overlaps": (overlaps or {}).get(h, True),
                                     "uninformative": (uninformative or {}).get(h, False)}}
            for h, s in zip(h4.HORIZONS, signs)}


class TestTheHumanDraws:
    def test_with_every_forecaster_eligible_they_are_the_draws_behind_section_2_3(self):
        human = spf.human_errors(spf.RECESS_SHEET, 1)
        draws = h4.human_draws(human.errors, np.arange(human.errors.shape[1]), 9)
        room = draws["headroom"][np.isfinite(draws["headroom"])]
        assert np.mean(room) == pytest.approx(0.1710, abs=5e-5)
        assert np.percentile(room, 2.5) == pytest.approx(0.076, abs=5e-4)
        assert np.percentile(room, 97.5) == pytest.approx(0.356, abs=5e-4)
        assert not h4.comparison(POINT, AI, draws)["uninformative"]

    def test_a_saturated_human_panel_is_uninformative(self):
        rng = np.random.default_rng(0)
        saturated = rng.normal(size=(60, 1)) + 0.001 * rng.normal(size=(60, 12))
        draws = h4.human_draws(saturated, np.arange(12), 9, n_draws=20)
        assert h4.comparison(POINT, AI, draws)["uninformative"]

    def test_a_stratum_smaller_than_the_panel_cannot_be_drawn(self):
        assert h4.human_draws(np.zeros((10, 5)), [0, 1], 3) is None


class TestTheStrata:
    def test_three_groups_of_equal_count_least_skilled_first(self):
        skill = np.array([0.5, np.nan, 0.1, 0.9, 0.3, 0.7, 0.2])
        assert [sorted(skill[g].tolist()) for g in h4.strata(skill)] == [[0.1, 0.2], [0.3, 0.5], [0.7, 0.9]]

    def test_the_nearest_mean_is_matched_and_overlap_is_its_range(self):
        skill = np.array([0.0, 0.1, 0.4, 0.5, 0.8, 0.9])
        inside = h4.matched_stratum(skill, 0.43)
        assert inside["stratum"] == 1 and inside["accuracy_overlaps"]
        outside = h4.matched_stratum(skill, 0.6)
        assert outside["stratum"] == 1 and not outside["accuracy_overlaps"]


class TestTheVerdict:
    def test_smaller_only_when_smaller_at_every_horizon(self):
        assert h4.verdict(_rows([1, 1, 1, 1, 1]))["verdict"].startswith("supports H4")
        assert h4.verdict(_rows([1, 1, 0, 1, 1]))["verdict"] == "not established"

    def test_the_reverse_is_reported_with_the_same_standing(self):
        assert h4.verdict(_rows([-1] * 5))["verdict"].startswith("reverse of H4")

    def test_a_confounded_or_uninformative_horizon_blocks_the_claim_and_is_named(self):
        out = h4.verdict(_rows([1] * 5, overlaps={2: False}, uninformative={4: True}))
        assert out["verdict"] == "not established"
        assert out["reasons_by_horizon"][2].startswith("confounded")
        assert out["reasons_by_horizon"][4].startswith("uninformative")


class TestTheComparison:
    def test_a_panel_sharing_its_error_gains_less_than_independent_humans(self):
        rng = np.random.default_rng(5)
        n, m = 90, 4
        y = (rng.uniform(size=n) < 0.5).astype(float)
        f = np.clip(0.5 + 0.3 * (y - 0.5)[:, None] + rng.normal(0, 0.2, n)[:, None]
                    + rng.normal(0, 0.02, (n, m)), 0, 1)
        ai = Panel(forecasts=f, outcomes=y, errors=f - y[:, None], task_ids=[f"t{i}" for i in range(n)],
                   model_keys=[f"m{j}" for j in range(m)], market_implied=np.full(n, np.nan),
                   state=[{} for _ in range(n)],
                   question_ids=[f"KXS{i % 25}-26OCT{i % 12:02d}-T{i}" for i in range(n)],
                   asked_on=[f"2026-09-{1 + i % 28:02d}" for i in range(n)])
        rounds, people = 80, 30
        yh = (rng.uniform(size=rounds) < 0.3).astype(float)
        fh = np.clip(0.3 + 0.4 * (yh - 0.3)[:, None] + rng.normal(0, 0.2, (rounds, people)), 0, 1)
        human = spf.HumanErrors(variable="RECESS", horizon=1, errors=fh - yh[:, None], forecasts=fh,
                                outcomes=yh, rounds=[(2000 + r // 4, r % 4 + 1) for r in range(rounds)],
                                ids=list(range(people)))
        out = h4.evaluate(ai, {1: human}, n_boot=FAST, n_draws=40)
        everyone = out["horizons"][1]["all_forecasters"]
        assert everyone["difference"] > 0 and everyone["claimed_sign"] == 1
        assert out["ai"]["brier_mean"] > 0 and out["horizons"][1]["brier_mean"] > 0

    def test_the_driver_runs_blind_on_the_committed_store(self):
        out = h4.run(n_boot=5, horizons=(1,), n_draws=20)
        assert out["blind"] is True and "verdict" in out

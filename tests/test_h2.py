"""H2's confirmatory test, base-rate convergence, had no implementation until 2026-09-14.

PREREGISTRATION.md 4 names the statistic and leaves open the category and where its
base rate comes from. Deviation 20 fixes both, and how the tercile contrast is formed
and claimed, before the test has run on anything but shuffled inputs. These tests pin
those choices and check the contrast recovers convergence planted in synthetic data.
"""

import json
import math

import numpy as np
import pytest

from neff import h1, h2, surprise
from neff.analysis import apply_registered_exclusions
from neff.config import PRIMARY_ARM, TASKS_PATH
from neff.panel import Panel, load_panel
from neff.store import JsonlStore

FAST = 40


def _panel(forecasts, refs):
    f = np.asarray(forecasts, dtype=float)
    n = f.shape[0]
    y = np.zeros(n)
    return Panel(forecasts=f, outcomes=y, errors=f - y[:, None], task_ids=[f"t{i}" for i in range(n)],
                 model_keys=[f"m{j}" for j in range(f.shape[1])], market_implied=np.full(n, np.nan),
                 state=[{} for _ in range(n)], question_ids=list(refs),
                 asked_on=[f"2026-09-{1 + i % 28:02d}" for i in range(n)])


def _planted(converge: bool, n: int = 150, seed: int = 3):
    rng = np.random.default_rng(seed)
    ambiguity = rng.uniform(0.0, 1.0, n)
    base = 0.45
    spread = (1.0 - ambiguity) * 0.4 if converge else rng.uniform(0.0, 0.4, n)
    median = base + spread * rng.choice([-1.0, 1.0], n)
    forecasts = np.column_stack([median - 0.01, median, median + 0.01])
    refs = [f"KXS-26OCT{i % 20:02d}-T{i}" for i in range(n)]
    return _panel(forecasts, refs), ambiguity, {"KXS": base}


class TestTheBaseRate:
    def test_only_markets_that_settled_count(self):
        out = h2.reference_base_rate({"E1": ["yes", "no", "no", "", None, "void"],
                                      "E2": ["yes"] * 3 + ["no"] * 5})
        assert (out["events"], out["markets"], out["yes"]) == (2, 11, 4)
        assert out["base_rate"] == pytest.approx(4 / 11)

    def test_undefined_with_one_event_or_fewer_than_ten_markets(self):
        assert h2.reference_base_rate({"E1": ["yes", "no"] * 10})["base_rate"] is None
        assert h2.reference_base_rate({"E1": ["yes"] * 4, "E2": ["no"] * 5})["base_rate"] is None

    def test_the_category_is_the_kalshi_series(self):
        assert h2.category_of("KXCPIYOY-26AUG-T2.9") == "KXCPIYOY"
        assert h2.category_of("KXAAAGASWNJ-26SEP07-4.15") == "KXAAAGASWNJ"

    def test_the_first_pinned_row_per_series_wins(self, tmp_path):
        path = tmp_path / "rates.jsonl"
        rows = [{"series": "KXA", "base_rate": 0.4}, {"series": "KXA", "base_rate": 0.9},
                {"series": "KXB", "base_rate": None}]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        rates = h2.load_base_rates(path)
        assert rates["KXA"] == 0.4 and math.isnan(rates["KXB"])


class TestThePin:
    def test_every_kalshi_series_asked_by_2026_09_13_is_pinned_exactly_once(self):
        pinned = [row["series"] for row in JsonlStore(h2.BASE_RATES_PATH).read()]
        assert len(pinned) == len(set(pinned))
        asked = {h2.category_of(t["source_ref"]) for t in JsonlStore(TASKS_PATH).read()
                 if t.get("arm") == PRIMARY_ARM and t.get("source") == "kalshi"
                 and str((t.get("state") or {}).get("asked_on") or "") <= "2026-09-13"}
        assert asked and asked <= set(pinned)

    def test_every_row_reads_the_reference_window_and_adds_up(self):
        for row in JsonlStore(h2.BASE_RATES_PATH).read():
            assert row["window"] == list(surprise.REFERENCE_WINDOW)
            if row["base_rate"] is not None:
                assert row["base_rate"] == pytest.approx(row["yes"] / row["markets"])
                assert row["events"] >= h2.MIN_REFERENCE_EVENTS
                assert row["markets"] >= h2.MIN_REFERENCE_MARKETS


class TestTheContrast:
    def test_planted_convergence_is_found_and_supports_h2(self):
        panel, ambiguity, rates = _planted(converge=True)
        out = h2.evaluate(panel, ambiguity, rates, n_boot=FAST)
        assert out["registered"]["difference"] < 0
        assert out["registered"]["claimed_sign"] == -1
        assert out["verdict"] == "supports H2"

    def test_no_convergence_falsifies_it(self):
        panel, ambiguity, rates = _planted(converge=False)
        out = h2.evaluate(panel, ambiguity, rates, n_boot=FAST)
        assert out["verdict"].startswith("falsified")

    def test_no_variation_leaves_it_untested_not_null(self):
        panel, _, rates = _planted(converge=True)
        out = h2.evaluate(panel, np.full(panel.n_tasks, 0.5), rates, n_boot=FAST)
        assert out["verdict"] == "untested" and "coincide" in out["registered"]["why_not"]

    def test_a_series_without_a_pinned_rate_is_named_and_left_out(self):
        panel, ambiguity, _ = _planted(converge=True)
        out = h2.evaluate(panel, ambiguity, {}, n_boot=FAST)
        assert out["series_not_pinned"] == ["KXS"] and out["task_days_with_a_base_rate"] == 0

    def test_the_market_sensitivity_never_moves_the_registered_verdict(self):
        panel, ambiguity, rates = _planted(converge=True)
        panel.market_implied = np.median(panel.forecasts, axis=1)
        out = h2.evaluate(panel, ambiguity, rates, n_boot=FAST)
        sensitivity = out["sensitivity_panel_minus_market"]
        assert sensitivity["unregistered"] and sensitivity["difference"] == pytest.approx(0.0)
        assert out["verdict"] == "supports H2"


class TestTheDriver:
    def test_a_blind_run_shuffles_ambiguity_only_where_it_exists(self, monkeypatch):
        seen = {}
        real = h2.evaluate

        def spy(panel, ambiguity, rates, n_boot, seed):
            seen["ambiguity"] = np.array(ambiguity, copy=True)
            return real(panel, ambiguity, rates, n_boot, seed)

        monkeypatch.setattr(h2, "evaluate", spy)
        out = h2.run(n_boot=5)
        panel, _ = apply_registered_exclusions(load_panel())
        truth = h2.ambiguity_column(panel, h1.load_ladder_snapshot())
        shuffled = seen["ambiguity"]
        assert out["blind"] is True and "verdict" in out
        assert np.array_equal(np.isnan(shuffled), np.isnan(truth))
        assert np.allclose(np.sort(shuffled[~np.isnan(shuffled)]), np.sort(truth[~np.isnan(truth)]))

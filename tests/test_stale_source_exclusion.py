"""The 9 JPM task-days already in the append-only record must not be analysed.

`edgar.build_filing_task` now refuses to construct a task on a dead reporting
series, but the store is append-only and nine were collected before the guard
existed (2026-08-17 through 2026-09-08). They ask for the quarter following
2014-12-31. That quarter was filed in 2015 and sits in every model's
pretraining, so the panel would be scoring recall rather than forecasting -- and
models that recall the same fact agree, which pushes `rho_bar` up, toward the
hypothesis. A contaminated task may push in any direction but that one.

These tests hold two properties:

  1. The rule is MECHANICAL -- the generator's own precondition applied on read,
     not a list of tickers we decided to drop.
  2. It was fixed BEFORE any affected task resolved. An exclusion chosen after
     seeing the scores is worth nothing no matter how good the reason sounds,
     so the record that none of them had an outcome on 2026-09-08 is itself
     part of the evidence and is asserted here against the real store.
"""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from neff.panel import Panel, apply_stale_source_exclusion
from neff.sources.edgar import MAX_REPORTING_GAP_DAYS

ROOT = Path(__file__).resolve().parent.parent


def _panel(states, asked_on=None):
    n = len(states)
    f = np.full((n, 3), 0.5)
    y = np.zeros(n)
    return Panel(
        forecasts=f,
        outcomes=y,
        errors=f - y[:, None],
        task_ids=[f"t{i}" for i in range(n)],
        model_keys=["a", "b", "c"],
        market_implied=np.full(n, np.nan),
        state=list(states),
        question_ids=[f"q{i}" for i in range(n)],
        asked_on=list(asked_on) if asked_on else [s.get("asked_on", "") for s in states],
    )


class TestTheRuleItself:
    def test_a_dead_series_task_is_dropped(self):
        panel = _panel([{"asked_on": "2026-09-08", "last_reported_end": "2014-12-31"}])
        assert apply_stale_source_exclusion(panel).n_tasks == 0

    def test_an_ordinary_filer_is_kept(self):
        # XOM on 2026-09-08: 161 days, the widest real gap in the battery.
        panel = _panel([{"asked_on": "2026-09-08", "last_reported_end": "2026-03-31"}])
        assert apply_stale_source_exclusion(panel).n_tasks == 1

    def test_macro_tasks_are_never_touched(self):
        """Macro tasks carry no last_reported_end. A rule that dropped rows it
        could not evaluate would silently delete 60% of the study."""
        panel = _panel([{"asked_on": "2026-09-08", "vix_level": 15.3}] * 4)
        assert apply_stale_source_exclusion(panel).n_tasks == 4

    def test_an_unparseable_date_is_kept_not_guessed(self):
        panel = _panel([{"asked_on": "2026-09-08", "last_reported_end": "not-a-date"}])
        assert apply_stale_source_exclusion(panel).n_tasks == 1

    def test_the_threshold_is_the_generators_own(self):
        """Stated once. If the two ever drift, tasks get built that the analysis
        then throws away -- paid for, registered, and unusable."""
        last = date(2026, 1, 31)
        ok = date.fromordinal(last.toordinal() + MAX_REPORTING_GAP_DAYS)
        bad = date.fromordinal(last.toordinal() + MAX_REPORTING_GAP_DAYS + 1)
        keep = _panel([{"asked_on": ok.isoformat(), "last_reported_end": last.isoformat()}])
        drop = _panel([{"asked_on": bad.isoformat(), "last_reported_end": last.isoformat()}])
        assert apply_stale_source_exclusion(keep).n_tasks == 1
        assert apply_stale_source_exclusion(drop).n_tasks == 0

    def test_the_surviving_rows_stay_aligned(self):
        """Every parallel array is cut with the same index or the panel silently
        pairs one task's forecasts with another's outcome."""
        states = [
            {"asked_on": "2026-09-08", "last_reported_end": "2026-06-30"},
            {"asked_on": "2026-09-08", "last_reported_end": "2014-12-31"},
            {"asked_on": "2026-09-08", "last_reported_end": "2026-03-31"},
        ]
        kept = apply_stale_source_exclusion(_panel(states))
        assert kept.n_tasks == 2
        assert kept.task_ids == ["t0", "t2"]
        assert kept.question_ids == ["q0", "q2"]
        assert [s["last_reported_end"] for s in kept.state] == ["2026-06-30", "2026-03-31"]
        assert kept.forecasts.shape[0] == kept.outcomes.shape[0] == kept.errors.shape[0] == 2


class TestAgainstTheRealRecord:
    """Asserted on the committed store, not a fixture."""

    @pytest.fixture
    def tasks(self):
        path = ROOT / "data" / "tasks.jsonl"
        if not path.exists():
            pytest.skip("no collected store")
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    def test_the_affected_tasks_are_exactly_the_jpm_ones(self, tasks):
        stale = [
            t for t in tasks
            if (t.get("state") or {}).get("last_reported_end")
            and (date.fromisoformat(t["state"]["asked_on"])
                 - date.fromisoformat(t["state"]["last_reported_end"])).days
                > MAX_REPORTING_GAP_DAYS
        ]
        assert {t["state"]["ticker"] for t in stale} == {"JPM"}

    def test_no_affected_task_had_resolved_when_the_rule_was_written(self, tasks):
        """The claim the exclusion rests on. If this ever fails, the rule stopped
        being outcome-blind at the moment it was written, and saying so in
        PREREGISTRATION.md 11 would no longer be true."""
        res_path = ROOT / "data" / "resolutions.jsonl"
        resolved = {
            json.loads(l)["task_id"]
            for l in res_path.read_text().splitlines() if l.strip()
        }
        jpm = {t["task_id"] for t in tasks if (t.get("state") or {}).get("ticker") == "JPM"}
        assert jpm, "no JPM tasks in the store"
        assert not (jpm & resolved), (
            "a JPM task has an outcome -- the deviation-3 exclusion can no "
            "longer be described as decided before the scores existed"
        )

    def test_the_guard_stops_new_ones_being_built(self, tasks):
        """A row dated after the fix means collection is still generating them."""
        jpm_days = sorted(
            t["state"]["asked_on"] for t in tasks
            if (t.get("state") or {}).get("ticker") == "JPM"
        )
        assert max(jpm_days) <= "2026-09-08", (
            f"JPM task built on {max(jpm_days)}, after the guard landed"
        )

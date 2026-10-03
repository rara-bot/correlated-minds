"""H1's state variables must survive the trip from source to task record.

`ladder_distance` was computed in kalshi.select_tasks, carried on the candidate
dict, and then silently dropped when tasks.py assembled `state`. Nothing failed.
The panel would have collected for 15 weeks and H1 -- the PRIMARY hypothesis --
would have arrived at analysis missing the one leg that does not depend on
markets supplying a stress event (PREREGISTRATION.md 10.5).

It is also irrecoverable: it needs the live strike ladder as it stood on the day
the question was asked. Unlike a derived variable, a missed day is gone.
"""

from datetime import date

import pytest

from neff import tasks as tasks_mod
from neff.config import STATE_COLLECTED_AT_ASK, STATE_VARIABLES

CANDIDATE = {
    "ticker": "KXCPIYOY-26DEC-T2.6",
    "title": "Will CPI YoY be above 2.6%?",
    "rules": "Resolves YES if...",
    "close_time": "2026-11-30T00:00:00Z",
    "days_out": 23.5,
    "series_ticker": "KXCPIYOY",
    "strike": 2.6,
    "market_implied": 0.41,
    "ladder_distance": 0.52,
}
SNAPSHOT = {"vix_level": 15.19, "realized_vol_20d": 0.0667}


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(
        tasks_mod.kalshi, "select_tasks", lambda **kw: [dict(CANDIDATE)]
    )
    monkeypatch.setattr(
        tasks_mod.fred, "state_snapshot", lambda _today: dict(SNAPSHOT)
    )
    monkeypatch.setattr(
        tasks_mod.edgar, "build_universe_tasks", lambda *a, **kw: []
    )


class TestAskTimeStateSurvives:
    def test_every_ask_time_variable_reaches_the_task(self, offline):
        built = tasks_mod.build_daily_tasks(date(2026, 8, 18), max_tasks=1,
                                            filing_fraction=0.0)
        assert built, "fixture produced no tasks"
        state = dict(built[0].state or {})
        missing = [v for v in STATE_COLLECTED_AT_ASK if state.get(v) is None]
        assert not missing, (
            f"{missing} computed upstream but absent from task state -- "
            "irrecoverable once collection starts"
        )

    def test_ladder_distance_carries_its_value_not_a_default(self, offline):
        """A `setdefault(0.0)` elsewhere could make this present but constant,
        which would zero out the experimental leg just as effectively."""
        built = tasks_mod.build_daily_tasks(date(2026, 8, 18), max_tasks=1,
                                            filing_fraction=0.0)
        assert built[0].state["ladder_distance"] == pytest.approx(0.52)


class TestRegisteredListIntegrity:
    """STATE_VARIABLES sets the Benjamini-Hochberg denominator, so an extra or
    missing entry moves H1's falsification threshold."""

    def test_unregistered_variables_are_absent(self):
        assert "news_volume" not in STATE_VARIABLES, (
            "news_volume was never registered in PREREGISTRATION.md 4, which "
            "states 'fixed, no additions permitted'"
        )

    def test_days_to_resolution_is_registered(self):
        assert "days_out" in STATE_VARIABLES, (
            "PREREGISTRATION.md 4 registers days-to-resolution, and 5.4(b) names "
            "it as the pre-committed handling for horizon drift"
        )

    def test_count_matches_the_registration(self):
        assert len(STATE_VARIABLES) == 7
        assert len(set(STATE_VARIABLES)) == 7, "duplicate inflates the BH denominator"

    def test_ask_time_subset_is_actually_a_subset(self):
        assert set(STATE_COLLECTED_AT_ASK) <= set(STATE_VARIABLES)

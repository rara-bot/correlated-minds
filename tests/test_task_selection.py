"""`ladder_distance` must be populated by EVERY path that produces a market.

H1 is the primary hypothesis and `ladder_distance` is its experimentally varied
leg -- the one state variable populated on every collection day regardless of
whether markets supply a stress event. §10.5 of the pre-registration leans on
exactly that when it argues H1 survives a calm 15 weeks.

AUDIT.md finding 12 fixed the *propagation* of this value: `tasks.py` computed it
and dropped it before persisting. The fix was real, and `tests/test_state_
variables.py` covers it -- but that test stubs out `kalshi.select_tasks` with a
hand-written candidate that already carries `ladder_distance`, so it verifies the
second half of the pipeline using a fixture that assumes the first half worked.

The first half did not work. `select_tasks` computed ladder positions only in the
curated-series branch. Markets picked up by the broaden-if-short path -- which
fires "on many days" by its own comment -- were appended with no ladder position
at all and persisted as None. Measured against the live API on a 25-task day:
**5 of 15 event tasks, a third of the sample, carrying nothing for the primary
hypothesis's experimental leg.** It is irrecoverable, because it needs the live
strike ladder as it stood on the ask date.

So these tests exercise the real selector with stubbed HTTP, rather than stubbing
the selector.
"""

from datetime import datetime, timedelta, timezone

import pytest

from neff.sources import kalshi


def _market(ticker, event, strike, days_out=30):
    close = datetime.now(timezone.utc) + timedelta(days=days_out)
    return {
        "ticker": ticker,
        "event_ticker": event,
        "status": "open",
        "close_time": close.isoformat().replace("+00:00", "Z"),
        "title": f"Will {ticker} settle above {strike}?",
        "rules_primary": "Resolves YES if ...",
        "cap_strike": strike,
    }


def _ladder(event, strikes, days_out=30):
    return [_market(f"{event}-T{s}", event, s, days_out) for s in strikes]


@pytest.fixture
def stub(monkeypatch):
    """Wire the two fetch points. `curated` is served for PRIORITY_SERIES,
    `extra` for anything the broadening path asks for."""

    def install(curated, extra=None, extra_series=("KXJOBLESSCLAIMS",)):
        curated = curated or {}
        extra = extra or {}

        def fetch_markets(series_ticker, limit=100):
            return list(curated.get(series_ticker, extra.get(series_ticker, [])))

        monkeypatch.setattr(kalshi, "fetch_open_markets_for_series", fetch_markets)
        monkeypatch.setattr(kalshi, "fetch_series_tickers", lambda *a, **kw: list(extra_series))

    return install


class TestEveryPathPopulatesLadderDistance:
    def test_curated_ladder(self, stub):
        stub({kalshi.PRIORITY_SERIES[0]: _ladder("EV", [1.0, 2.0, 3.0, 4.0, 5.0])})
        sel = kalshi.select_tasks(max_tasks=5, min_days_out=1, max_days_out=90)
        assert sel
        assert all(m["ladder_distance"] is not None for m in sel)

    def test_broadened_markets_carry_it_too(self, stub):
        """The defect: curated series supply too few, the selector widens, and
        every widened market arrived with nothing."""
        stub(
            curated={kalshi.PRIORITY_SERIES[0]: _ladder("EV", [1.0, 2.0, 3.0])},
            extra={"KXJOBLESSCLAIMS": _ladder("JC", [210, 215, 220, 225, 230])},
        )
        sel = kalshi.select_tasks(
            max_tasks=15, min_days_out=1, max_days_out=90, broaden_if_short=True
        )
        broadened = [m for m in sel if m["series_ticker"] == "KXJOBLESSCLAIMS"]
        assert broadened, "broadening did not fire -- test is not exercising the path"
        missing = [m["ticker"] for m in broadened if m.get("ladder_distance") is None]
        assert not missing, f"broadened markets with no ladder position: {missing}"

    def test_broadened_ladder_is_graded_not_constant(self, stub):
        """Present-but-constant would zero the experimental leg just as
        effectively as absent. A five-strike ladder must yield five positions."""
        stub(
            curated={kalshi.PRIORITY_SERIES[0]: _ladder("EV", [1.0, 2.0, 3.0])},
            extra={"KXJOBLESSCLAIMS": _ladder("JC", [210, 215, 220, 225, 230])},
        )
        sel = kalshi.select_tasks(
            max_tasks=15, min_days_out=1, max_days_out=90, broaden_if_short=True
        )
        broadened = [m for m in sel if m["series_ticker"] == "KXJOBLESSCLAIMS"]
        assert len({m["ladder_distance"] for m in broadened}) >= 3

    def test_event_without_a_usable_ladder_gets_the_registered_default(self, stub):
        """Fewer than three strikes is not a ladder; the registered convention
        is 0.0 rather than missing."""
        stub({kalshi.PRIORITY_SERIES[0]: _ladder("EV", [1.0, 2.0])})
        sel = kalshi.select_tasks(max_tasks=5, min_days_out=1, max_days_out=90)
        assert sel
        assert all(m["ladder_distance"] == 0.0 for m in sel)

    def test_strikeless_market_is_not_left_unset(self, stub):
        m = _market("NOSTRIKE-1", "NS", 0)
        m.pop("cap_strike")
        stub({kalshi.PRIORITY_SERIES[0]: [m]})
        sel = kalshi.select_tasks(max_tasks=5, min_days_out=1, max_days_out=90)
        assert all(x.get("ladder_distance") is not None for x in sel)


class TestTheInvariantIsEnforced:
    """A registered variable recorded at ask time and irrecoverable afterwards
    must not be able to leave the selector unset. Two audits reached this
    function; the third defence is an assertion, not a fourth audit."""

    def test_selector_raises_rather_than_returning_a_none(self, stub, monkeypatch):
        stub({kalshi.PRIORITY_SERIES[0]: _ladder("EV", [1.0, 2.0, 3.0, 4.0])})
        # Simulate any future path that forgets to assign the value.
        monkeypatch.setattr(kalshi, "assign_ladder_distance", lambda markets: False)
        with pytest.raises(kalshi.FetchError, match="ladder_distance missing"):
            kalshi.select_tasks(max_tasks=5, min_days_out=1, max_days_out=90)


class TestAssignLadderDistance:
    def test_normalised_to_unit_interval(self):
        markets = [{"strike": s} for s in (1.0, 2.0, 3.0, 4.0, 5.0)]
        assert kalshi.assign_ladder_distance(markets)
        vals = [m["ladder_distance"] for m in markets]
        assert min(vals) == 0.0
        assert max(vals) == pytest.approx(0.5)
        assert all(0.0 <= v <= 1.0 for v in vals)

    def test_median_strike_is_zero_distance(self):
        markets = [{"strike": s} for s in (10.0, 20.0, 30.0)]
        kalshi.assign_ladder_distance(markets)
        assert markets[1]["ladder_distance"] == 0.0

    def test_degenerate_span_does_not_divide_by_zero(self):
        markets = [{"strike": 5.0} for _ in range(4)]
        assert kalshi.assign_ladder_distance(markets)
        assert all(m["ladder_distance"] == 0.0 for m in markets)

    def test_reports_whether_a_usable_ladder_existed(self):
        assert kalshi.assign_ladder_distance([{"strike": s} for s in (1.0, 2.0, 3.0)])
        assert not kalshi.assign_ladder_distance([{"strike": 1.0}, {"strike": 2.0}])

    def test_does_not_overwrite_an_existing_default(self):
        markets = [{"strike": 1.0, "ladder_distance": 0.9}, {"strike": 2.0}]
        kalshi.assign_ladder_distance(markets)
        assert markets[0]["ladder_distance"] == 0.9

"""The market's own price, recorded when the panel is asked.

PREREGISTRATION.md 10 limitation 1 says Kalshi quotes are not public, and the
Kalshi module said the same: `yes_bid`, `yes_ask` and `last_price` came back
null on every economics series on 17 Aug. Checked again on 2026-09-13 they are
absent altogether, because Kalshi renamed them. Prices are dollar strings
(`yes_bid_dollars: "0.4100"`), sizes are fixed-point strings (`volume_fp`), and
every market fetched carried them. Thirteen collection days of market benchmark
were lost to a field name (deviation 15).

Recorded, never shown to a model: the prompt is built before the quote is
attached, and a price in the prompt would hand every model the same anchor.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from neff import tasks as tasks_mod
from neff.sources import kalshi

# KXCPIYOY-26NOV-T4.9 as Kalshi served it on 2026-09-13.
LIVE_SHAPE = {
    "ticker": "KXCPIYOY-26NOV-T4.9", "event_ticker": "KXCPIYOY-26NOV",
    "status": "active", "strike_type": "greater", "floor_strike": 4.9,
    "yes_bid_dollars": "0.0000", "yes_ask_dollars": "0.3000",
    "last_price_dollars": "0.0500", "previous_price_dollars": "0.0500",
    "volume_fp": "157.00", "volume_24h_fp": "0.00", "open_interest_fp": "58.00",
    "liquidity_dollars": "0.0000",
}


class TestTheQuoteIsReadFromTheFieldsKalshiServes:
    def test_dollar_strings_become_numbers(self):
        q = kalshi.market_quote(LIVE_SHAPE)
        assert q["yes_bid"] == 0.0
        assert q["yes_ask"] == pytest.approx(0.30)
        assert q["last_price"] == pytest.approx(0.05)
        assert q["volume"] == pytest.approx(157.0)
        assert q["open_interest"] == pytest.approx(58.0)

    def test_the_retired_field_names_are_not_what_is_read(self):
        """The 17 Aug reading: an absent field is not an unpublished price."""
        assert kalshi.market_quote({"yes_bid": 41, "yes_ask": 45})["yes_bid"] is None

    def test_missing_or_malformed_fields_are_none_never_zero(self):
        q = kalshi.market_quote({"yes_bid_dollars": "n/a", "yes_ask_dollars": None})
        assert q["yes_bid"] is None and q["yes_ask"] is None and q["volume"] is None

    def test_the_observation_time_is_kept(self):
        stamp = "2026-09-14T16:00:00+00:00"
        assert kalshi.market_quote(LIVE_SHAPE, observed_at=stamp)["observed_at"] == stamp


class TestTheImpliedProbability:
    def test_is_the_midpoint_of_the_standing_quote(self):
        assert kalshi.implied_probability({"yes_bid": 0.40, "yes_ask": 0.46}) == pytest.approx(0.43)

    def test_a_wide_quote_is_recorded_as_wide_not_filtered(self):
        """Whether a 0-30 cent quote is informative is the analysis's call, stated there."""
        assert kalshi.implied_probability(kalshi.market_quote(LIVE_SHAPE)) == pytest.approx(0.15)

    @pytest.mark.parametrize("quote", [
        None, {}, {"yes_bid": 0.4}, {"yes_ask": 0.5},
        {"yes_bid": 0.6, "yes_ask": 0.5}, {"yes_bid": 0.0, "yes_ask": 0.0},
    ])
    def test_no_standing_quote_is_no_probability(self, quote):
        assert kalshi.implied_probability(quote) is None


def _market(ticker, event, strike, **extra):
    close = datetime.now(timezone.utc) + timedelta(days=30)
    market = {
        "ticker": ticker, "event_ticker": event, "status": "open",
        "close_time": close.isoformat().replace("+00:00", "Z"),
        "title": f"Will {ticker} settle above {strike}?",
        "rules_primary": "Resolves YES if ...",
        "floor_strike": strike, "strike_type": "greater",
        "yes_bid_dollars": "0.4000", "yes_ask_dollars": "0.4600",
    }
    market.update(extra)
    return market


@pytest.fixture
def stub(monkeypatch):
    def install(curated, extra=None, extra_series=("KXJOBLESSCLAIMS",)):
        def fetch_markets(series_ticker, limit=100):
            return list(curated.get(series_ticker, (extra or {}).get(series_ticker, [])))

        monkeypatch.setattr(kalshi, "fetch_open_markets_for_series", fetch_markets)
        monkeypatch.setattr(kalshi, "fetch_series_tickers", lambda *a, **kw: list(extra_series))

    return install


class TestEveryPathCarriesTheQuote:
    def test_curated(self, stub):
        stub({kalshi.PRIORITY_SERIES[0]: [
            _market(f"EV-26NOV-T{s}", "EV-26NOV", s) for s in (1.0, 2.0, 3.0)
        ]})
        sel = kalshi.select_tasks(max_tasks=3, min_days_out=1, max_days_out=90)
        assert sel
        assert all(m["market_implied"] == pytest.approx(0.43) for m in sel)
        assert all(m["quote"]["yes_ask"] == pytest.approx(0.46) for m in sel)

    def test_broadened(self, stub):
        stub(
            curated={kalshi.PRIORITY_SERIES[0]: [_market("EV-26NOV-T1.0", "EV-26NOV", 1.0)]},
            extra={"KXJOBLESSCLAIMS": [
                _market(f"JC-26OCT-T{s}", "JC-26OCT", s) for s in (210, 215, 220)
            ]},
        )
        sel = kalshi.select_tasks(max_tasks=15, min_days_out=1, max_days_out=90,
                                  broaden_if_short=True)
        broadened = [m for m in sel if m["series_ticker"] == "KXJOBLESSCLAIMS"]
        assert broadened, "broadening did not fire -- test is not exercising the path"
        assert all(m["quote"] is not None for m in broadened)
        assert all(m["market_implied"] == pytest.approx(0.43) for m in broadened)


class TestTheLadderIsDescribedPerRealEvent:
    """The curated path positions strikes against a whole SERIES, so two expiries
    of one series share a median. These fields describe a question's own ladder."""

    def test_two_expiries_are_two_ladders(self, stub):
        aug = [_market(f"EV-26AUG-T{s}", "EV-26AUG", s) for s in (2.0, 2.1, 2.2)]
        nov = [_market(f"EV-26NOV-T{s}", "EV-26NOV", s) for s in (4.0, 4.5, 5.0, 5.5, 6.0)]
        stub({kalshi.PRIORITY_SERIES[0]: aug + nov})
        sel = kalshi.select_tasks(max_tasks=5, min_days_out=1, max_days_out=90)
        assert sel
        for m in sel:
            assert m["event_ladder_size"] == (3 if m["kalshi_event"] == "EV-26AUG" else 5)
            assert 0.0 <= m["event_ladder_distance"] <= 0.5

    def test_a_categorical_event_has_no_ladder(self, stub):
        """Fed decisions: `C26` parses as a number, and is not a strike."""
        def decision(suffix, custom):
            return _market(f"FD-26SEP-{suffix}", "FD-26SEP", None, floor_strike=None,
                           strike_type="custom", custom_strike=custom)

        stub({kalshi.PRIORITY_SERIES[0]: [
            decision("C26", {"Cut": ">25"}), decision("C25", {"Cut": "25"}),
            decision("H0", {"Hike": "0"}), decision("C50", {"Cut": "50"}),
        ]})
        sel = kalshi.select_tasks(max_tasks=5, min_days_out=1, max_days_out=90)
        assert sel
        assert all(m["event_ladder_size"] == 0 for m in sel)
        assert all(m["event_ladder_distance"] is None for m in sel)

    def test_numeric_custom_strikes_are_a_ladder(self):
        """`Exactly 3.3%` buckets are served as custom strikes, and are ordered."""
        group = [{"kalshi_event": "U3-26NOV", "strike": s, "strike_type": "custom",
                  "custom_strike": {"Value": str(s)}} for s in (3.3, 3.4, 3.5, 3.6)]
        kalshi.annotate_event_ladders(group)
        assert all(m["event_ladder_size"] == 4 for m in group)
        assert all(m["event_ladder_distance"] is not None for m in group)

    def test_an_event_under_three_rungs_is_undefined_not_zero(self):
        group = [{"kalshi_event": "E", "strike": s} for s in (1.0, 2.0)]
        kalshi.annotate_event_ladders(group)
        assert all(m["event_ladder_distance"] is None for m in group)

    def test_the_registered_pooled_value_is_unchanged(self, stub):
        """`ladder_distance` must still be computed exactly as it was at
        registration; a recorded variable does not change meaning mid-panel."""
        strikes = (2.0, 2.1, 2.2, 4.0, 4.5, 5.0, 5.5, 6.0)
        markets = [{"strike": s} for s in strikes]
        kalshi.assign_ladder_distance(markets)
        expected = [abs(s - 4.25) / 4.0 for s in strikes]
        assert [m["ladder_distance"] for m in markets] == pytest.approx(expected)


class TestTheQuoteNeverReachesThePrompt:
    def test_prompt_is_identical_with_and_without_a_quote(self, monkeypatch):
        candidate = {
            "ticker": "KXCPIYOY-26DEC-T2.6", "title": "Will CPI YoY be above 2.6%?",
            "rules": "Resolves YES if...", "close_time": "2026-11-30T00:00:00Z",
            "days_out": 23.5, "series_ticker": "KXCPIYOY", "strike": 2.6,
            "ladder_distance": 0.52,
        }
        monkeypatch.setattr(tasks_mod.fred, "state_snapshot", lambda _d: {"vix_level": 15.19})
        monkeypatch.setattr(tasks_mod.edgar, "build_universe_tasks", lambda *a, **kw: [])

        def build(cand):
            monkeypatch.setattr(tasks_mod.kalshi, "select_tasks", lambda **kw: [dict(cand)])
            return tasks_mod.build_daily_tasks(date(2026, 9, 14), max_tasks=1,
                                               filing_fraction=0.0)[0]

        bare = build(candidate)
        quoted = build(dict(candidate, quote={"yes_bid": 0.40, "yes_ask": 0.46},
                            market_implied=0.43))
        assert quoted.prompt == bare.prompt
        assert "0.46" not in quoted.prompt and "0.43" not in quoted.prompt
        assert quoted.state["quote"]["yes_ask"] == 0.46
        assert quoted.market_implied == 0.43

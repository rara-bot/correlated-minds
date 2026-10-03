"""The market's surprise at a release, the consensus the study can observe.

`abs_surprise` is a registered H1 state variable and the trigger of the
registered Week-5 prediction, and deviation 8's definition needed a consensus
source that was never wired: the variable is NaN on every row. Deviation 18
measures it as the Brier score of the Kalshi market a day before the print,
over the rungs the market was genuinely unsure about.

Two candle shapes appear in the wild -- live candles quote `close_dollars`,
historical ones `close` -- and both are copied here from what the API served on
2026-09-13.
"""

import pytest

from neff import surprise

HISTORICAL = {"end_period_ts": 100, "yes_bid": {"close": "0.3400"},
              "yes_ask": {"close": "0.3700"}}
LIVE = {"end_period_ts": 200, "yes_bid": {"close_dollars": "0.4000"},
        "yes_ask": {"close_dollars": "0.4600"}}


class TestTheSnapshotQuote:
    def test_reads_both_candle_shapes(self):
        assert surprise.snapshot_quote([HISTORICAL], 100) == pytest.approx(0.355)
        assert surprise.snapshot_quote([LIVE], 250) == pytest.approx(0.43)

    def test_takes_the_last_candle_at_or_before_the_snapshot(self):
        assert surprise.snapshot_quote([HISTORICAL, LIVE], 150) == pytest.approx(0.355)
        assert surprise.snapshot_quote([LIVE, HISTORICAL], 200) == pytest.approx(0.43)

    def test_never_looks_past_the_snapshot(self):
        assert surprise.snapshot_quote([LIVE], 199) is None

    def test_a_wide_last_quote_means_no_consensus_not_an_older_substitute(self):
        wide = {"end_period_ts": 300, "yes_bid": {"close_dollars": "0.10"},
                "yes_ask": {"close_dollars": "0.60"}}
        assert surprise.snapshot_quote([LIVE, wide], 300) is None

    def test_a_one_sided_candle_is_passed_over(self):
        one_sided = {"end_period_ts": 300, "yes_bid": {"close_dollars": None},
                     "yes_ask": {"close_dollars": "0.50"}}
        assert surprise.snapshot_quote([LIVE, one_sided], 300) == pytest.approx(0.43)


class TestTheBrierSurprise:
    def test_is_the_markets_mean_squared_error(self):
        value, n = surprise.brier_surprise([(1.0, 0.8), (0.0, 0.4)])
        assert n == 2 and value == pytest.approx((0.04 + 0.16) / 2)

    def test_rungs_the_market_was_sure_about_carry_no_weight(self):
        """Averaging in far strikes would make a long ladder look calm for being long."""
        value, n = surprise.brier_surprise([(1.0, 0.99), (0.0, 0.01), (1.0, 0.8), (0.0, 0.4)])
        assert n == 2 and value == pytest.approx(0.1)

    def test_too_few_informative_rungs_is_undefined_never_zero(self):
        assert surprise.brier_surprise([(1.0, 0.99), (1.0, 0.7)]) == (None, 1)

    def test_a_rung_without_a_quote_is_skipped(self):
        assert surprise.brier_surprise([(1.0, None), (0.0, None)]) == (None, 0)

    def test_a_bigger_miss_is_a_bigger_surprise(self):
        calm, _ = surprise.brier_surprise([(1.0, 0.7), (0.0, 0.3)])
        shock, _ = surprise.brier_surprise([(0.0, 0.7), (1.0, 0.3)])
        assert shock > calm


class TestWhatCountsAsAMacroRelease:
    @pytest.mark.parametrize("event", ["KXCPIYOY-26AUG", "KXPAYROLLS-26SEP", "KXECONSTATU3-26NOV",
                                       "KXGDP-26OCT30", "KXHOUSINGSTART-26SEP17", "KXUSPPI-26SEP10"])
    def test_listed(self, event):
        assert surprise.is_release_event(event)

    @pytest.mark.parametrize("event", ["KXFEDDECISION-26SEP", "KXAAAGASWNJ-26SEP07", "KXEGGS-AUG26",
                                       "KXCBDCZECH-26SEP17", "KXKSWHEAT-26SEP30"])
    def test_not_listed(self, event):
        assert not surprise.is_release_event(event)

    def test_the_reference_window_ends_where_collection_began(self):
        assert surprise.REFERENCE_WINDOW[1].startswith("2026-09-01")

    def test_the_year_is_read_from_the_ticker(self):
        assert surprise.ticker_year("KXCPIYOY-25DEC") == 2025
        assert surprise.ticker_year("KXGDP-26OCT30") == 2026
        assert surprise.ticker_year("CPIYOY") is None


class TestOneEvent:
    CLOSE = "2026-09-11T12:29:00Z"

    def _market(self, strike, result):
        return {"ticker": f"KXCPIYOY-26AUG-T{strike}", "result": result, "close_time": self.CLOSE,
                "strike_type": "greater", "floor_strike": strike}

    def test_composes_markets_candles_and_settlements(self, monkeypatch):
        markets = [self._market(2.5, "yes"), self._market(2.6, "no"), self._market(2.7, "no")]
        quotes = {"KXCPIYOY-26AUG-T2.5": (0.70, 0.74), "KXCPIYOY-26AUG-T2.6": (0.50, 0.54),
                  "KXCPIYOY-26AUG-T2.7": (0.98, 0.99)}

        def candles(ticker, namespace, start, end):
            bid, ask = quotes[ticker]
            return [{"end_period_ts": end - 3600, "yes_bid": {"close_dollars": str(bid)},
                     "yes_ask": {"close_dollars": str(ask)}}]

        monkeypatch.setattr(surprise, "fetch_candles", candles)
        record = surprise.event_surprise("KXCPIYOY-26AUG", pause_s=0, fetched=(markets, "live"))
        assert record["rungs"] == 3 and record["informative"] == 2      # T2.7 at 0.985 is sure
        assert record["surprise"] == pytest.approx(((1 - 0.72) ** 2 + (0 - 0.52) ** 2) / 2)
        assert record["snapshot"].startswith("2026-09-10T12:29")

    def test_unsettled_and_categorical_markets_are_not_rungs(self, monkeypatch):
        markets = [
            {"ticker": "KXFEDDECISION-26SEP-C26", "result": "yes", "close_time": self.CLOSE,
             "strike_type": "custom", "custom_strike": {"Cut": ">25"}},
            dict(self._market(2.5, ""), result=""),
        ]
        monkeypatch.setattr(surprise, "fetch_candles",
                            lambda *a: pytest.fail("no rung here should need a quote"))
        record = surprise.event_surprise("X", pause_s=0, fetched=(markets, "live"))
        assert record["surprise"] is None and record["rungs"] == 0

    def test_it_never_asks_for_a_forecast(self):
        """Reads market prices and settlements only, so it cannot unblind the panel."""
        source = (surprise.__file__)
        text = open(source, encoding="utf-8").read()
        assert "observations" not in text and "load_panel" not in text

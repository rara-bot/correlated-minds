"""An arm cap is a hard stop, so it must not be set near the expected spend.

`Ledger.check` raises `BudgetExceeded`. It does not warn. Reaching the
`ws1_prospective` sub-cap therefore ENDS the prospective panel wherever it
happens to be -- and it would happen at the far end, in November, on days that
cannot be recollected because every question is registered before its outcome
exists.

That cap was $70, set against a documented cost of $25 for the full panel. The
documented figure was for a NINE-model panel and predated the tenth; priced
against the real battery and the real roster it is $0.4442 a day, about $47 for
the 105-day window. Two thirds of the cap, on a number nobody had re-measured.

These tests hold three things: the margin between the cap and the projection,
the global cap as the real safety property, and the reserve.
"""

import pytest

from neff import config
from neff.ledger import BudgetExceeded, Ledger

WS1 = "ws1_prospective"


class TestProjection:
    def test_collection_window_is_the_registered_one(self):
        assert config.COLLECTION_START == "2026-08-24"
        assert config.DATA_FREEZE == "2026-12-06"
        assert config.collection_days() == 105

    def test_projection_includes_the_replicate_arm(self):
        """The test-retest replicates of PREREGISTRATION.md 5.4(d) are real calls
        on this arm. Excluding them from the projection is how the previous
        figure went stale and left a hard stop two thirds of the way up the real
        spend."""
        bare = config.MEASURED_DAILY_USD * config.collection_days()
        assert config.projected_ws1_usd() > bare
        expected = bare * (1 + config.REPLICATES_PER_DAY / config.TASKS_PER_DAY)
        assert config.projected_ws1_usd() == pytest.approx(expected)

    def test_daily_cost_is_a_measured_figure_not_a_placeholder(self):
        """A round number here would mean nobody priced a real day. The value
        comes from `neff.collect --dry-run --tasks 25` against the live task
        battery, so it should carry sub-cent precision."""
        assert 0.2 < config.MEASURED_DAILY_USD < 2.0
        assert round(config.MEASURED_DAILY_USD, 2) != config.MEASURED_DAILY_USD


class TestHeadroom:
    def test_ws1_cap_carries_at_least_double_the_projection(self):
        """Prompts lengthen as filings accumulate and more open questions are
        re-asked daily, so the projection is a floor, not a ceiling."""
        cap = config.ARM_CAPS_USD[WS1]
        assert cap >= 2 * config.projected_ws1_usd(), (
            f"ws1 cap ${cap:.0f} is under 2x the ${config.projected_ws1_usd():.2f} "
            f"projection -- collection can halt mid-panel"
        )

    def test_every_arm_has_a_cap(self):
        """An uncapped arm can consume the global budget on its own."""
        assert set(config.ARM_CAPS_USD) >= {"pilot", WS1, "h2_reasoning"}
        assert all(v > 0 for v in config.ARM_CAPS_USD.values())

    def test_arm_caps_fit_inside_the_global_cap(self):
        assert sum(config.ARM_CAPS_USD.values()) <= config.BUDGET_USD

    def test_a_reserve_survives(self):
        """Released only against the Week-5 interim read."""
        reserve = config.BUDGET_USD - sum(config.ARM_CAPS_USD.values())
        assert reserve >= 10.0

    def test_global_cap_is_unchanged(self):
        """Reallocating between arms must never raise total exposure."""
        assert config.BUDGET_USD == 200.0


class TestTheCapReallyStops:
    """If this ever became a warning the tests above would be measuring nothing."""

    def test_arm_cap_raises_rather_than_warning(self, tmp_path):
        led = Ledger(tmp_path / "l.jsonl", cap_usd=1000.0, arm_caps={WS1: 1.0})
        led.record(model="m", arm=WS1, input_tokens=0, output_tokens=0, usd=0.9)
        with pytest.raises(BudgetExceeded):
            led.check(usd=0.5, arm=WS1)

    def test_global_cap_raises_too(self, tmp_path):
        led = Ledger(tmp_path / "l.jsonl", cap_usd=1.0, arm_caps={WS1: 100.0})
        led.record(model="m", arm=WS1, input_tokens=0, output_tokens=0, usd=0.9)
        with pytest.raises(BudgetExceeded):
            led.check(usd=0.5, arm=WS1)

    def test_the_full_panel_fits_under_the_cap(self, tmp_path):
        """Simulate the whole 105-day run at the measured rate."""
        led = Ledger(
            tmp_path / "l.jsonl",
            cap_usd=config.BUDGET_USD,
            arm_caps=dict(config.ARM_CAPS_USD),
        )
        per_day = config.projected_ws1_usd() / config.collection_days()
        for day in range(config.collection_days()):
            led.record(model="panel", arm=WS1, input_tokens=0, output_tokens=0,
                       usd=per_day)
        assert led.spent == pytest.approx(config.projected_ws1_usd())
        led.check(usd=per_day, arm=WS1)  # must not raise

    def test_a_fifty_percent_cost_overrun_still_completes(self, tmp_path):
        """The margin exists for this case, so it is worth asserting directly."""
        led = Ledger(
            tmp_path / "l.jsonl",
            cap_usd=config.BUDGET_USD,
            arm_caps=dict(config.ARM_CAPS_USD),
        )
        for day in range(config.collection_days()):
            led.record(model="panel", arm=WS1, input_tokens=0, output_tokens=0,
                       usd=(config.projected_ws1_usd() / config.collection_days()) * 1.5)
        assert led.spent < config.ARM_CAPS_USD[WS1]

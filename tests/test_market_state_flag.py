"""A stress day that nobody noticed is a stress day nobody checked collected.

The stress leg of H1 is a tercile contrast on `vix_level`, and PREREGISTRATION.md
§10 limitation 5 says plainly that 15 calm weeks would leave it untestable. If a
genuine shock does land it will be a handful of days, and those days ARE the
stress leg -- one lost to a collection failure costs incomparably more than an
ordinary Tuesday. Nothing in this repo can summon a shock. What it can remove is
the silence.

THE BINDING CONSTRAINT IS THAT THIS MUST NEVER COST A DAY. The daily workflow
runs check_days.py, `neff.collect` exposes no --as-of, and a day that does not
collect can never be filled. A reporting feature that can halt collection is
strictly worse than no reporting feature, so most of this file is about the ways
it must refuse to fail.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_days.py"


@pytest.fixture
def cd():
    spec = importlib.util.spec_from_file_location("check_days_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _task(day, vix, arm="ws1_prospective"):
    return {"task_id": f"t{day}{vix}", "arm": arm,
            "state": {"asked_on": day, "vix_level": vix}}


class TestItCannotCostADay:
    def test_malformed_state_reports_instead_of_raising(self, cd, capsys):
        junk = [{"task_id": "x", "arm": "ws1_prospective", "state": "not-a-dict"}]
        cd._print_market_state(junk, "2026-09-09")          # must not raise

    def test_missing_state_key_is_survivable(self, cd):
        cd._print_market_state([{"task_id": "x", "arm": "ws1_prospective"}], "2026-09-09")

    def test_no_tasks_at_all_is_survivable(self, cd):
        assert cd._print_market_state([], "2026-09-09") == {}

    def test_a_non_numeric_vix_is_skipped_not_fatal(self, cd):
        out = cd._print_market_state(
            [_task("2026-09-01", "high"), _task("2026-09-02", 15.0)], "2026-09-02")
        assert out["vix_latest"] == 15.0


class TestNoticingWhatMatters:
    def test_a_new_high_is_called_out(self, cd, capsys):
        tasks = [_task("2026-09-01", 14.0), _task("2026-09-02", 15.0),
                 _task("2026-09-03", 28.4)]
        out = cd._print_market_state(tasks, "2026-09-03")
        assert out["vix_new_high"] is True and out["vix_notable"] is True
        assert "NEW HIGH" in capsys.readouterr().out

    def test_a_new_low_widens_the_bottom_tercile_and_is_said_so(self, cd, capsys):
        tasks = [_task("2026-09-01", 16.0), _task("2026-09-02", 15.0),
                 _task("2026-09-03", 11.2)]
        out = cd._print_market_state(tasks, "2026-09-03")
        assert out["vix_notable"] is True
        assert "NEW LOW" in capsys.readouterr().out

    def test_an_ordinary_day_says_nothing_special(self, cd, capsys):
        tasks = [_task("2026-09-01", 14.0), _task("2026-09-02", 18.0),
                 _task("2026-09-03", 15.5)]
        out = cd._print_market_state(tasks, "2026-09-03")
        assert out["vix_notable"] is False
        text = capsys.readouterr().out
        assert "NEW HIGH" not in text and "NEW LOW" not in text

    def test_absolute_stress_is_flagged_even_without_a_new_high(self, cd, capsys):
        """A reader who does not know this study's own range still needs to be
        told that VIX 27 is a stress regime."""
        tasks = [_task("2026-09-01", 31.0), _task("2026-09-02", 27.0)]
        out = cd._print_market_state(tasks, "2026-09-02")
        assert out["vix_new_high"] is False        # 27 < 31
        assert out["vix_notable"] is True          # but still stressed
        assert "VIX >= 25" in capsys.readouterr().out

    @pytest.mark.parametrize("vix,band", [
        (12.0, "calm"), (17.0, "normal"), (22.0, "elevated"),
        (27.0, "stressed"), (35.0, "SEVERE")])
    def test_bands(self, cd, vix, band):
        assert cd._vix_band(vix) == band


class TestItReadsTheRightRows:
    def test_pilot_rows_are_excluded(self, cd):
        """The 36 unlabelled task rows are pre-registration pilot. Admitting
        them reports a VIX range the stress leg will never see -- the same
        fail-closed rule panel.load_panel applies."""
        tasks = [_task("2026-08-17", 40.0, arm=None),
                 _task("2026-09-01", 14.0), _task("2026-09-02", 15.0)]
        out = cd._print_market_state(tasks, "2026-09-02")
        assert out["vix_max"] == 15.0
        assert out["vix_new_high"] is True     # 15 > 14, pilot's 40 not counted

    def test_repeated_states_are_counted_and_named(self, cd, capsys):
        """Weekends and holidays carry the prior close (§11, deviation 6). The
        count of distinct states is what the stress leg actually has."""
        tasks = [_task("2026-09-04", 14.32), _task("2026-09-05", 14.32),
                 _task("2026-09-06", 14.32), _task("2026-09-07", 14.32),
                 _task("2026-09-08", 15.30)]
        out = cd._print_market_state(tasks, "2026-09-08")
        assert out["vix_distinct"] == 2
        assert "3 day(s) repeat" in capsys.readouterr().out


class TestTheJumpSizeIsAvailableToConsumers:
    """The workflow notice fires on a >=20% jump over every earlier day. That
    needs the maximum EXCLUDING today -- `vix_max` includes it, so comparing
    against it would compare a value with itself and never fire."""

    def test_prior_max_excludes_today(self, cd):
        tasks = [_task("2026-09-01", 14.0), _task("2026-09-02", 18.0),
                 _task("2026-09-03", 30.0)]
        out = cd._print_market_state(tasks, "2026-09-03")
        assert out["vix_max"] == 30.0
        assert out["vix_max_prior"] == 18.0
        assert out["vix_latest"] / out["vix_max_prior"] >= 1.20   # notice fires

    def test_prior_max_is_none_on_the_very_first_day(self, cd):
        out = cd._print_market_state([_task("2026-09-01", 14.0)], "2026-09-01")
        assert out["vix_max_prior"] is None

    def test_a_slow_drift_to_a_new_high_does_not_trip_the_jump_rule(self, cd):
        """Early in collection almost every day sets a new high. Firing on that
        would make the notice wallpaper within a week."""
        tasks = [_task("2026-09-01", 14.0), _task("2026-09-02", 14.6)]
        out = cd._print_market_state(tasks, "2026-09-02")
        assert out["vix_new_high"] is True
        assert out["vix_latest"] / out["vix_max_prior"] < 1.20    # notice silent

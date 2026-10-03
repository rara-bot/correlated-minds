"""The human benchmark: its pinned inputs, and the numbers the plan registered from them.

H4 compares the AI panel with the SPF RECESS headroom registered in
PREREGISTRATION.md 2.3, and the plan recomputes that benchmark -- at the surviving
panel size (deviation 17), on the squared-error scale and at matched accuracy.
Deviation 19 pins its inputs so that every recomputation rests on the data the
registered numbers came from. These tests hold that line: the pinned files are
the ones recorded, nothing reaches for the network, and the pin reproduces the
registered table to every printed digit. Until 13 Sep 2026 no test touched this
module.
"""

import re
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from neff import config
from neff.sources import fred, spf

PREREG = Path(__file__).resolve().parent.parent / "PREREGISTRATION.md"


def registered_recess_table():
    """Section 2.3's table: horizon -> (rho_bar, headroom, (lo, hi))."""
    rows = re.findall(
        r"^\| (\d)[^|]*\| (0\.\d{4}) \| \**(0\.\d{4})\** \| \[(0\.\d{3}), (0\.\d{3})\] \|$",
        PREREG.read_text(encoding="utf-8"),
        flags=re.M,
    )
    return {int(h): (float(r), float(hr), (float(lo), float(hi))) for h, r, hr, lo, hi in rows}


class TestThePinnedInputs:
    def test_every_pinned_file_is_the_one_recorded(self):
        assert spf.pinned_problems() == []

    def test_a_changed_file_is_caught(self, tmp_path, monkeypatch):
        copy = tmp_path / "spf"
        shutil.copytree(spf.PINNED_DIR, copy)
        monkeypatch.setattr(spf, "PINNED_DIR", copy)
        monkeypatch.setattr(spf, "PROVENANCE_PATH", copy / "PROVENANCE.json")
        with (copy / "RECESS.csv").open("a", encoding="utf-8") as fh:
            fh.write("2026,4,999,50,50,50,50,50\n")
        assert spf.pinned_problems() == ["RECESS.csv does not match its recorded SHA-256"]

    def test_the_benchmark_never_reaches_for_the_network(self, monkeypatch):
        def refuse(*args, **kwargs):
            raise AssertionError("the registered benchmark must be computed from the pin")

        monkeypatch.setattr(spf, "download_microdata", refuse)
        monkeypatch.setattr(fred, "fetch_series", refuse)
        assert spf.human_errors("RECESS", horizon=1).errors.shape == (106, 79)

    def test_the_pin_cannot_answer_for_years_it_does_not_hold(self):
        with pytest.raises(ValueError):
            spf.human_errors("RECESS", horizon=1, min_year=1990)

    def test_a_workbook_path_is_live_data_and_must_say_so(self):
        with pytest.raises(ValueError):
            spf.load_variable("RECESS", path=Path("SPFmicrodata.xlsx"))
        with pytest.raises(ValueError):
            spf.series_history("GDPC1", source="cache")


class TestTheRegisteredBenchmark:
    def test_the_registered_table_has_all_five_horizons(self):
        assert sorted(registered_recess_table()) == [1, 2, 3, 4, 5]

    @pytest.mark.parametrize("horizon", [1, 2, 3, 4, 5])
    def test_section_2_3_reproduces_to_every_printed_digit(self, horizon):
        rho, headroom, (lo, hi) = registered_recess_table()[horizon]
        baseline = spf.measure_binary(horizon=horizon)
        assert round(baseline.rho_bar, 4) == rho
        assert round(baseline.n_eff_matched - 1, 4) == headroom
        assert (round(baseline.n_eff_matched_ci[0] - 1, 3),
                round(baseline.n_eff_matched_ci[1] - 1, 3)) == (lo, hi)

    def test_the_default_panel_is_the_registered_one(self):
        """The default was 7, the size of the original seven-model panel, so a call
        with defaults silently unmatched the comparison H4 says is matched."""
        baseline = spf.measure_binary(horizon=1, n_subsamples=5)
        assert baseline.matched_panel_size == len(config.primary_panel()) == 9


class TestWhatEachRoundIsScoredAgainst:
    @pytest.mark.parametrize("survey, horizon, target", [
        ((2025, 4), 1, (2025, 4)),
        ((2025, 4), 2, (2026, 1)),
        ((2025, 3), 5, (2026, 3)),
        ((2026, 1), 4, (2026, 4)),
    ])
    def test_horizon_one_is_the_survey_quarter(self, survey, horizon, target):
        assert spf.target_quarter(*survey, horizon) == target

    def test_a_decline_is_judged_against_the_quarter_before_across_a_year_end(self):
        gdp = [(date(2025, 10, 1), 100.0), (date(2026, 1, 1), 99.0), (date(2026, 4, 1), 99.5)]
        assert spf._gdp_declined(gdp, 2026, 1) == 1.0
        assert spf._gdp_declined(gdp, 2026, 2) == 0.0
        assert spf._gdp_declined(gdp, 2025, 4) is None

    def test_recess_errors_are_probability_minus_outcome(self):
        human = spf.human_errors("RECESS", horizon=1)
        assert np.nanmin(human.forecasts) >= 0.0 and np.nanmax(human.forecasts) <= 1.0
        assert set(np.unique(human.outcomes)) <= {0.0, 1.0}
        np.testing.assert_array_equal(human.errors, human.forecasts - human.outcomes[:, None])
        assert (len(human.rounds), len(human.ids)) == human.errors.shape


class TestQuarterlyAverage:
    PUBLISHING = [(date(2026, 7, 1), 4.2), (date(2026, 8, 1), 4.1)]

    def test_a_quarter_still_being_published_has_no_average(self):
        assert fred.quarterly_average("UNRATE", 2026, 3, series=self.PUBLISHING) is None

    def test_a_complete_quarter_averages_its_three_months(self):
        complete = self.PUBLISHING + [(date(2026, 9, 1), 4.3)]
        assert fred.quarterly_average("UNRATE", 2026, 3, series=complete) == pytest.approx(4.2)

    def test_a_month_published_as_missing_is_skipped_not_awaited(self):
        shutdown = [(date(2025, 10, 1), None), (date(2025, 11, 1), 4.5), (date(2025, 12, 1), 4.4)]
        assert fred.quarterly_average("UNRATE", 2025, 4, series=shutdown) == pytest.approx(4.45)

    def test_fred_really_lists_october_2025_without_a_value(self):
        """The federal shutdown: no household survey and no CPI for October 2025."""
        for series_id in ("UNRATE", "CPIAUCSL"):
            assert (date(2025, 10, 1), None) in spf.series_history(series_id)

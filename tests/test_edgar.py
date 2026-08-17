"""Tests for document-grounded filing tasks.

These target the failure modes that actually occurred while building this
module -- each one produced plausible-looking but wrong numbers, which is the
dangerous kind of bug in a study like this.
"""

from datetime import date

import pytest

from neff.sources import edgar
from neff.sources.edgar import QuarterlyFact


def q(end: str, value: float, filed: str = None, fp: str = "Q1", start: str = None) -> QuarterlyFact:
    end_d = date.fromisoformat(end)
    start_d = date.fromisoformat(start) if start else date.fromordinal(end_d.toordinal() - 91)
    return QuarterlyFact(
        fy=end_d.year,
        fp=fp,
        start=start_d,
        end=end_d,
        filed=date.fromisoformat(filed) if filed else date.fromordinal(end_d.toordinal() + 30),
        value=value,
    )


def quarterly_series(n: int = 12, base: float = 100.0, growth: float = 0.0) -> list:
    """n quarters, 91 days apart, with optional per-year growth."""
    out = []
    start = date(2022, 3, 31)
    for i in range(n):
        end = date.fromordinal(start.toordinal() + 91 * i)
        value = base * ((1 + growth) ** (i / 4.0))
        out.append(q(end.isoformat(), value))
    return out


# --- point-in-time discipline ------------------------------------------------

def test_visible_history_filters_on_filing_date_not_period_end():
    """The lookahead guard. A quarter that has ENDED but not been FILED is not
    yet knowable, and treating it as visible is exactly the bias that has
    invalidated published LLM-finance work."""
    facts = [
        q("2026-03-31", 100.0, filed="2026-04-30"),
        q("2026-06-30", 110.0, filed="2026-07-31"),
    ]
    # 15 July: Q2 has ended but has NOT been filed
    visible = edgar.visible_history(facts, date(2026, 7, 15))
    assert len(visible) == 1
    assert visible[0].end == date(2026, 3, 31)

    visible = edgar.visible_history(facts, date(2026, 8, 1))
    assert len(visible) == 2


def test_visible_history_empty_before_any_filing():
    facts = [q("2026-03-31", 100.0, filed="2026-04-30")]
    assert edgar.visible_history(facts, date(2026, 1, 1)) == []


# --- Q4 derivation -----------------------------------------------------------

def test_derives_missing_q4_from_annual_identity():
    """Filers like Apple never publish a standalone Q4; it exists only inside
    the 10-K annual total. Without reconstruction those companies drop out of
    the study entirely."""
    quarterly = {
        date(2025, 12, 31): q("2025-12-31", 25.0, start="2025-10-01"),
        date(2026, 3, 31): q("2026-03-31", 30.0, start="2026-01-01"),
        date(2026, 6, 30): q("2026-06-30", 20.0, start="2026-04-01"),
    }
    annual = {
        date(2026, 9, 30): QuarterlyFact(
            fy=2026, fp="FY",
            start=date(2025, 10, 1), end=date(2026, 9, 30),
            filed=date(2026, 11, 1), value=100.0,
        )
    }
    n = edgar._derive_missing_q4(quarterly, annual)
    assert n == 1
    derived = quarterly[date(2026, 9, 30)]
    assert derived.value == pytest.approx(25.0)      # 100 - (25+30+20)
    assert derived.fp == "Q4D"                        # flagged as reconstructed


def test_q4_not_derived_when_a_quarter_is_missing():
    """Only derive when the identity is exact -- never guess."""
    quarterly = {
        date(2026, 3, 31): q("2026-03-31", 30.0, start="2026-01-01"),
        date(2026, 6, 30): q("2026-06-30", 20.0, start="2026-04-01"),
    }
    annual = {
        date(2026, 9, 30): QuarterlyFact(
            fy=2026, fp="FY", start=date(2025, 10, 1), end=date(2026, 9, 30),
            filed=date(2026, 11, 1), value=100.0,
        )
    }
    assert edgar._derive_missing_q4(quarterly, annual) == 0


def test_q4_not_derived_when_residual_is_negative():
    quarterly = {
        date(2025, 12, 31): q("2025-12-31", 50.0, start="2025-10-01"),
        date(2026, 3, 31): q("2026-03-31", 50.0, start="2026-01-01"),
        date(2026, 6, 30): q("2026-06-30", 50.0, start="2026-04-01"),
    }
    annual = {
        date(2026, 9, 30): QuarterlyFact(
            fy=2026, fp="FY", start=date(2025, 10, 1), end=date(2026, 9, 30),
            filed=date(2026, 11, 1), value=100.0,
        )
    }
    assert edgar._derive_missing_q4(quarterly, annual) == 0


def test_existing_q4_is_never_overwritten():
    reported = q("2026-09-30", 40.0, start="2026-07-01")
    quarterly = {
        date(2025, 12, 31): q("2025-12-31", 25.0, start="2025-10-01"),
        date(2026, 3, 31): q("2026-03-31", 30.0, start="2026-01-01"),
        date(2026, 6, 30): q("2026-06-30", 20.0, start="2026-04-01"),
        date(2026, 9, 30): reported,
    }
    annual = {
        date(2026, 9, 30): QuarterlyFact(
            fy=2026, fp="FY", start=date(2025, 10, 1), end=date(2026, 9, 30),
            filed=date(2026, 11, 1), value=999.0,
        )
    }
    edgar._derive_missing_q4(quarterly, annual)
    assert quarterly[date(2026, 9, 30)].value == pytest.approx(40.0)


# --- comparator lookup -------------------------------------------------------

def test_same_quarter_last_year_matches_by_date_not_position():
    """Position-based lookup breaks whenever the series has a gap, which is
    exactly when a filer's Q4 is missing."""
    facts = quarterly_series(9)
    reference = facts[-1]
    match = edgar.same_quarter_last_year(facts, reference)
    assert match is not None
    gap = (reference.end - match.end).days
    assert 340 <= gap <= 390


def test_same_quarter_last_year_returns_none_when_absent():
    facts = quarterly_series(3)
    assert edgar.same_quarter_last_year(facts, facts[-1]) is None


# --- threshold design --------------------------------------------------------

def test_threshold_is_none_without_enough_history():
    assert edgar.next_period_threshold(quarterly_series(4)) is None


def test_threshold_tracks_company_growth_trend():
    """A flat company and a growing one must get different thresholds --
    otherwise the growing company's question is a foregone YES."""
    flat = edgar.next_period_threshold(quarterly_series(12, base=100.0, growth=0.0))
    grow = edgar.next_period_threshold(quarterly_series(12, base=100.0, growth=0.40))
    assert flat is not None and grow is not None
    # the growing company's threshold must be a bigger multiple of its own base
    assert grow[0] > flat[0]


def test_threshold_growth_is_clamped():
    """An extreme trailing growth rate (a one-off acquisition) must not push the
    threshold somewhere absurd and re-saturate the question."""
    picked = edgar.next_period_threshold(quarterly_series(12, base=100.0, growth=5.0))
    assert picked is not None
    threshold, label = picked
    comparator = [f for f in quarterly_series(12, base=100.0, growth=5.0)][-4].value
    assert threshold < comparator * 2.0          # clamp held
    assert "trend" in label


def test_threshold_label_explains_itself():
    picked = edgar.next_period_threshold(quarterly_series(12, growth=0.10))
    assert picked is not None
    _, label = picked
    assert "quarter ending" in label and "%" in label


# --- resolution --------------------------------------------------------------

def test_build_filing_task_rejects_thin_history():
    assert edgar.build_filing_task("TEST", 1, date(2026, 8, 17), facts=quarterly_series(3)) is None


def test_build_filing_task_produces_a_well_formed_question():
    task = edgar.build_filing_task("TEST", 1, date(2030, 1, 1), facts=quarterly_series(12, growth=0.1))
    assert task is not None
    assert "TEST" in task["title"]
    assert task["threshold"] > 0
    assert task["source_ref"].startswith("edgar:1:")
    assert "quarterly revenue as reported" in task["context"]
    # the question must state its own resolution rule
    assert "Resolves YES" in task["rules"]

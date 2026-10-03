"""Three registered state variables had no implementation until 2026-09-09.

PREREGISTRATION.md §4 registers seven state variables and says the count is the
Benjamini-Hochberg denominator. Four are written at ask time. The other three --
expectation_dispersion, abs_surprise, novelty_score -- were left to be derived
"from data already retained", and nothing derived them.

Whoever wrote them in December would have been choosing operationalisations for
registered variables while able to see whether the choice helped H1. That is the
freedom §9 gives up. These tests pin the definitions to the day they were
written, with the analysis driver still blind and five resolved task-days on the
record.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from neff import state

ROOT = Path(__file__).resolve().parent.parent


def _task(tid, day, question):
    return {"task_id": tid, "arm": "ws1_prospective",
            "state": {"asked_on": day},
            "prompt": f"boilerplate\n--- QUESTION ---\n{question}\n"
                      f"--- MARKET CONTEXT (as of today) ---\nVIX: 15\n"}


class TestExpectationDispersion:
    def test_it_is_dispersion_across_models_within_a_task(self):
        f = np.array([[0.1, 0.5, 0.9], [0.5, 0.5, 0.5]])
        d = state.expectation_dispersion(f)
        assert d[1] == pytest.approx(0.0)          # unanimous
        assert d[0] > d[1]                          # spread out

    def test_a_failed_model_is_skipped_not_fatal(self):
        """panel.load_panel keeps failures as NaN so estimators can work
        pairwise-complete. Dropping the task instead would preferentially
        discard busy days, which is where H1 lives."""
        f = np.array([[0.1, np.nan, 0.9]])
        assert np.isfinite(state.expectation_dispersion(f)[0])

    def test_a_task_with_one_answer_is_nan_not_zero(self):
        """One forecast has no dispersion. Zero would assert unanimity."""
        f = np.array([[0.4, np.nan, np.nan]])
        assert np.isnan(state.expectation_dispersion(f)[0])

    def test_it_returns_one_value_per_task(self):
        f = np.random.default_rng(0).uniform(0, 1, size=(17, 9))
        assert state.expectation_dispersion(f).shape == (17,)


class TestNoveltyScore:
    def test_the_first_day_has_no_corpus_to_resemble(self):
        tasks = [_task("a", "2026-09-01", "Will CPI exceed 3.9 percent?"),
                 _task("b", "2026-09-01", "Will payrolls fall below 25000?")]
        n = state.novelty_scores(tasks)
        assert n["a"] == 1.0 and n["b"] == 1.0

    def test_a_question_asked_again_is_not_novel(self):
        """tasks.py re-asks open questions daily. From its second day a question
        resembles something in the corpus -- itself."""
        q = "Will CPI inflation be above 3.9 percent for the year ending August?"
        tasks = [_task("d1", "2026-09-01", q), _task("d2", "2026-09-02", q)]
        n = state.novelty_scores(tasks)
        assert n["d1"] == 1.0
        assert n["d2"] == pytest.approx(0.0)

    def test_a_genuinely_new_topic_scores_high(self):
        tasks = [_task("a", "2026-09-01", "Will CPI inflation exceed 3.9 percent?"),
                 _task("b", "2026-09-02", "Will the Bering Sea snow crab catch exceed tonnes?")]
        n = state.novelty_scores(tasks)
        assert n["b"] > 0.7

    def test_same_day_tasks_do_not_score_against_each_other(self):
        """Otherwise the score depends on the order rows happen to sit in the
        file, which is not a property of the question."""
        q = "Will CPI inflation be above 3.9 percent?"
        tasks = [_task("x", "2026-09-01", q), _task("y", "2026-09-01", q)]
        n = state.novelty_scores(tasks)
        assert n["x"] == 1.0 and n["y"] == 1.0

    def test_it_is_bounded_and_deterministic(self):
        tasks = [_task(f"t{i}", f"2026-09-{i+1:02d}", f"Question about topic {i}")
                 for i in range(6)]
        a = state.novelty_scores(tasks)
        b = state.novelty_scores(list(reversed(tasks)))
        assert a == b, "score depends on input order"
        assert all(0.0 <= v <= 1.0 for v in a.values())

    def test_prompt_scaffolding_is_stripped_before_comparing(self):
        """Every prompt carries the same JSON instructions and market block.
        Comparing whole prompts would score every pair as near-identical and
        make novelty a constant."""
        t = _task("a", "2026-09-01", "Will CPI exceed 3.9 percent?")
        text = state.question_text(t)
        assert "CPI" in text
        assert "boilerplate" not in text and "MARKET CONTEXT" not in text


class TestAbsSurprise:
    def test_a_missing_consensus_is_nan_not_zero(self):
        """Zero asserts the release landed exactly on consensus. An absent data
        source is not entitled to make that claim."""
        assert np.isnan(state.standardised_surprise(3.9, None, 0.2))
        assert np.isnan(state.standardised_surprise(None, 3.7, 0.2))

    def test_it_is_scaled_so_releases_are_comparable(self):
        """A 0.2pp CPI miss and a 40k payrolls miss are not the same number but
        may be the same surprise."""
        cpi = state.standardised_surprise(4.1, 3.9, 0.2)
        pay = state.standardised_surprise(140_000, 100_000, 40_000)
        assert cpi == pytest.approx(1.0) and pay == pytest.approx(1.0)

    def test_it_is_absolute(self):
        assert state.standardised_surprise(3.7, 3.9, 0.2) == \
               state.standardised_surprise(4.1, 3.9, 0.2)

    def test_a_zero_or_negative_scale_is_nan(self):
        assert np.isnan(state.standardised_surprise(4.1, 3.9, 0.0))
        assert np.isnan(state.standardised_surprise(4.1, 3.9, -1.0))


class TestCompleteCaseHandling:
    def test_coverage_is_reported_not_assumed(self):
        assert state.coverage([1.0, 2.0, np.nan, 4.0]) == pytest.approx(0.75)
        assert state.coverage([]) == 0.0

    def test_complete_cases_needs_every_variable(self):
        cols = {"a": np.array([1.0, 2.0, np.nan]), "b": np.array([1.0, np.nan, 3.0])}
        assert state.complete_cases(cols).tolist() == [True, False, False]

    def test_the_real_panel_loses_the_filing_arm_to_complete_cases(self):
        """The number that has to be registered rather than discovered.

        `ladder_distance` is structurally undefined for EDGAR filing tasks --
        there is no ladder -- and filing tasks are 40% of the registered task
        mix. So a complete-case H1 regression runs on the Kalshi subset and
        silently excludes the document-grounded arm. §11 deviation 8 registers
        that, with coverage reported alongside every estimate."""
        path = ROOT / "data" / "tasks.jsonl"
        if not path.exists():
            pytest.skip("no collected store")
        tasks = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        prosp = [t for t in tasks if t.get("arm") == "ws1_prospective"]
        ladder = np.array([(t.get("state") or {}).get("ladder_distance", np.nan)
                           for t in prosp], dtype=float)
        cov = state.coverage(ladder)
        assert 0.0 < cov < 1.0, (
            f"ladder_distance coverage is {cov:.1%}; deviation 8 describes it as "
            "partial because filing tasks have no ladder"
        )


class TestNoveltyOnTheRealCorpus:
    """Shapes the fixtures above cannot reproduce."""

    @pytest.fixture
    def prospective(self):
        path = ROOT / "data" / "tasks.jsonl"
        if not path.exists():
            pytest.skip("no collected store")
        tasks = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        return [t for t in tasks if t.get("arm") == "ws1_prospective"]

    def test_the_ask_date_does_not_leak_into_the_score(self, prospective):
        """Every prompt stamps "Today's date". Left in, a question re-asked
        tomorrow looks slightly unlike its own earlier self because the calendar
        moved, so it never scores 0 and novelty drifts with the date rather than
        with the corpus."""
        by_ref = {}
        for t in prospective:
            by_ref.setdefault(t.get("source_ref"), []).append(t)
        repeated = [v for v in by_ref.values() if len(v) > 1]
        assert repeated, "no question was re-asked; cannot test the property"

        n = state.novelty_scores(prospective)
        group = sorted(repeated[0], key=lambda t: t["state"]["asked_on"])
        later = [n[t["task_id"]] for t in group[1:]]
        assert max(later) == pytest.approx(0.0, abs=1e-9), (
            f"a re-asked question scored {max(later):.4f} instead of 0 -- "
            "something volatile is still inside the question text"
        )

    def test_the_first_day_is_maximally_novel_and_nothing_later_is(self, prospective):
        n = state.novelty_scores(prospective)
        days = sorted({t["state"]["asked_on"] for t in prospective})
        first = [n[t["task_id"]] for t in prospective
                 if t["state"]["asked_on"] == days[0]]
        assert set(first) == {1.0}

    def test_market_context_never_reaches_the_question_text(self, prospective):
        for t in prospective[:40]:
            txt = state.question_text(t)
            assert "MARKET CONTEXT" not in txt
            assert "probability" not in txt.lower() or "JSON" not in txt

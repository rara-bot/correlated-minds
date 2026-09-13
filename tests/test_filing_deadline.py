"""A filing question must not ask about a quarter already past its SEC deadline.

ExxonMobil filed its Q2 2026 10-Q on 2026-08-03. No three-month revenue fact in
its company facts ends 2026-06-30, so the freshest XOM quarter the generator
could see stayed 2026-03-31, and every XOM task from 2026-09-01 asked the panel
about the quarter following it -- one whose figure had already been filed.
Deviation 3's 200-day staleness guard was sized for a series ten years dead and
would not have tripped until 2026-10-17. And the resolver took "the earliest
later quarter", so in November it would have scored those questions against Q3
(deviation 16).
"""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from neff import analysis, collect
from neff.panel import Panel, _state_with_reported_fp, apply_filing_deadline_exclusion
from neff.sources import edgar, kalshi

ROOT = Path(__file__).resolve().parent.parent
RULE_WRITTEN = "2026-09-13"


def _panel(states):
    n = len(states)
    f = np.full((n, 3), 0.5)
    y = np.zeros(n)
    return Panel(
        forecasts=f, outcomes=y, errors=f - y[:, None],
        task_ids=[f"t{i}" for i in range(n)], model_keys=["a", "b", "c"],
        market_implied=np.full(n, np.nan), state=[dict(s) for s in states],
        question_ids=[f"q{i}" for i in range(n)],
        asked_on=[s.get("asked_on", "") for s in states],
    )


XOM_ROW = {"asked_on": "2026-09-01", "last_reported_end": "2026-03-31", "last_reported_fp": "Q1"}


class TestTheReadSideRule:
    def test_a_quarter_past_its_10q_deadline_is_dropped(self):
        p = _panel([
            XOM_ROW,                                                      # 154 days
            {"asked_on": "2026-09-01", "last_reported_end": "2026-06-30",
             "last_reported_fp": "Q2"},                                   # 63 days
            {"asked_on": "2026-09-01"},                                   # a macro task
        ])
        assert apply_filing_deadline_exclusion(p).task_ids == ["t1", "t2"]

    def test_the_10k_quarter_gets_its_longer_allowance(self):
        p = _panel([{"asked_on": "2026-12-01", "last_reported_end": "2026-06-30",
                     "last_reported_fp": "Q3"}])                          # 154 <= 158
        assert apply_filing_deadline_exclusion(p).n_tasks == 1

    def test_it_never_reads_an_outcome(self):
        settled_yes, settled_no = _panel([XOM_ROW]), _panel([XOM_ROW])
        settled_yes.outcomes[:] = 1.0
        settled_no.outcomes[:] = 0.0
        assert apply_filing_deadline_exclusion(settled_yes).n_tasks == 0
        assert apply_filing_deadline_exclusion(settled_no).n_tasks == 0

    def test_unreadable_dates_are_kept(self):
        p = _panel([{"asked_on": "not-a-date", "last_reported_end": "2026-03-31"}])
        assert apply_filing_deadline_exclusion(p).n_tasks == 1

    def test_the_analysis_driver_applies_it(self):
        p = _panel([XOM_ROW, XOM_ROW] + [{"asked_on": "2026-09-02"}] * 4)
        kept, _ = analysis.apply_registered_exclusions(p)
        assert "t0" not in kept.task_ids and "t1" not in kept.task_ids
        assert kept.n_tasks == 4


class TestTheFiscalLabelIsRecoveredFromOldRows:
    PROMPT = (
        "...\n"
        "  2025 Q4D  quarter ending 2025-12-31  revenue $83.18B (reported 2026-02-18)\n"
        "  2026 Q1  quarter ending 2026-03-31  revenue $85.14B (reported 2026-05-04)\n"
        "..."
    )

    def test_read_from_the_table_the_panel_was_shown(self):
        record = {"prompt": self.PROMPT, "state": {"last_reported_end": "2026-03-31"}}
        assert _state_with_reported_fp(record)["last_reported_fp"] == "Q1"

    def test_a_recorded_label_wins(self):
        record = {"prompt": self.PROMPT,
                  "state": {"last_reported_end": "2026-03-31", "last_reported_fp": "Q3"}}
        assert _state_with_reported_fp(record)["last_reported_fp"] == "Q3"

    def test_the_stored_row_is_never_modified(self):
        record = {"prompt": self.PROMPT, "state": {"last_reported_end": "2026-03-31"}}
        _state_with_reported_fp(record)
        assert "last_reported_fp" not in record["state"]

    def test_a_macro_task_is_left_alone(self):
        record = {"prompt": self.PROMPT, "state": {"vix_level": 15.0}}
        assert _state_with_reported_fp(record) == {"vix_level": 15.0}


class TestEdgarResolutionsSayWhereTheyCameFrom:
    def test_labelled_by_their_own_ref_with_the_filed_figure(self, tmp_path, monkeypatch):
        tasks = tmp_path / "tasks.jsonl"
        resolutions = tmp_path / "resolutions.jsonl"
        tasks.write_text(json.dumps({
            "task_id": "f1", "kind": "filing", "prompt": "", "source": "edgar",
            "source_ref": "edgar:1:2026-06-30",
            "state": {"threshold": 50.0, "asked_on": "2026-09-14"},
        }) + "\n")
        monkeypatch.setattr(collect, "TASKS_PATH", tasks)
        monkeypatch.setattr(collect, "RESOLUTIONS_PATH", resolutions)
        monkeypatch.setattr(edgar, "resolve_filing_task_details", lambda cik, end, thr: {
            "outcome": 1.0, "period_end": "2026-09-30", "value": 60.0, "threshold": thr,
            "filed": "2026-10-30", "fp": "Q4D", "derived": True, "accession": "0000-00",
        })
        monkeypatch.setattr(kalshi, "fetch_settlement",
                            lambda ref: pytest.fail(f"EDGAR ref {ref} sent to Kalshi"))

        assert collect.resolve_outcomes()["resolved"] == 1
        row = json.loads(resolutions.read_text().splitlines()[0])
        assert row["source"] == "edgar:1:2026-06-30"
        assert not row["source"].startswith("kalshi:")
        assert '"derived": true' in row["note"] and '"period_end": "2026-09-30"' in row["note"]


class TestAgainstTheRealRecord:
    """Asserted on the committed store, up to the date the rule was written.

    Later rows are held by the generator's own guard. An assertion about rows
    that do not exist yet could fail on tomorrow's data, and the daily workflow
    runs this suite before it collects -- so it would halt tomorrow's collection.
    """

    @pytest.fixture
    def filing(self):
        path = ROOT / "data" / "tasks.jsonl"
        if not path.exists():
            pytest.skip("no collected store")
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        return [r for r in rows
                if r.get("kind") == "filing" and r.get("arm") == "ws1_prospective"
                and (r.get("state") or {}).get("asked_on", "") <= RULE_WRITTEN]

    def test_every_collected_filing_prompt_yields_its_label(self, filing):
        assert filing, "no filing tasks in the store"
        missing = [r["task_id"] for r in filing
                   if not _state_with_reported_fp(r).get("last_reported_fp")]
        assert not missing, f"{len(missing)} filing task(s) with no recoverable fiscal label"

    def test_the_rows_it_removes_are_exactly_jpm_and_xom(self, filing):
        dropped = {}
        for r in filing:
            st = _state_with_reported_fp(r)
            gap = (date.fromisoformat(st["asked_on"])
                   - date.fromisoformat(st["last_reported_end"])).days
            if gap > edgar.filing_deadline_gap(st.get("last_reported_fp")):
                dropped[st["ticker"]] = dropped.get(st["ticker"], 0) + 1
        assert set(dropped) == {"JPM", "XOM"}
        assert dropped["XOM"] == 13

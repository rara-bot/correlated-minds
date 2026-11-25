"""The daily alarm speaks on a model's first bad day, not only once its week is bad.

On 2026-11-24 deepseek answered 0 of its 27 questions and nothing was raised: the
alarm fired only when a model was under the 80% floor across the last seven
collected days AND on the latest one, and deepseek's window still read 162/189 =
85.7%. By the time the window crossed the floor, 2026-11-25 was lost too
(PREREGISTRATION.md 11, deviation 29). `scripts/check_days.py` now also names a
model under 80% on the latest collected day alone, in its report and in
continuity.json, which the workflow's alarm step reads.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from neff import config
from scripts import check_days

START = date(2026, 9, 1)
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily.yml"


def _run(tmp_path, monkeypatch, capsys, *, fail_on=(), fail_model="deepseek", days=12,
         answered_on_bad_day=0, retired_after=None):
    """Three questions a day for `days` days, two models; `fail_model` fails on `fail_on`."""
    obs, tasks = tmp_path / "o.jsonl", tmp_path / "t.jsonl"
    rows, trows = [], []
    for d in range(days):
        day = (START + timedelta(days=d)).isoformat()
        for n in range(3):
            tid = f"t{d}-{n}"
            trows.append({"task_id": tid, "arm": config.PRIMARY_ARM, "state": {"asked_on": day}})
            created = f"{day}T17:00:00+00:00"
            rows.append({"obs_id": f"{tid}-h", "task_id": tid, "model_key": "claude_haiku",
                         "prompt_variant": 0, "forecast": 0.4, "created_at": created})
            if retired_after is not None and d > retired_after:
                continue
            bad = d in fail_on and n >= answered_on_bad_day
            rows.append({"obs_id": f"{tid}-x", "task_id": tid, "model_key": fail_model,
                         "prompt_variant": 0, "forecast": None if bad else 0.4,
                         "error": "openrouter HTTP 404: No endpoints found" if bad else None,
                         "created_at": created})
    obs.write_text("".join(json.dumps(r) + "\n" for r in rows))
    tasks.write_text("".join(json.dumps(r) + "\n" for r in trows))
    monkeypatch.setattr(check_days, "OBSERVATIONS", obs)
    monkeypatch.setattr(check_days, "TASKS", tasks)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_days.py", "--json"])
    check_days.main()
    out = capsys.readouterr().out
    return out, json.loads((tmp_path / "continuity.json").read_text())


class TestTheFirstBadDayIsNamed:
    def test_a_total_loss_on_the_latest_day_alone(self, tmp_path, monkeypatch, capsys):
        """The 24 Nov shape: window still above 80% (20/21 here), latest day 0/3."""
        out, c = _run(tmp_path, monkeypatch, capsys, fail_on={11})
        assert c["coverage_window"]["deepseek"] >= check_days.COVERAGE_FLOOR
        assert c["below_floor"] == []
        assert c["latest_day"] == (START + timedelta(days=11)).isoformat()
        assert c["latest_day_below"] == {"deepseek": {"answered": 0, "asked": 3}}
        assert "LOST ON THE LATEST DAY" in out and "deepseek: 0/3 answered" in out
        assert "every model above the floor" not in out

    def test_a_partial_loss_under_80_percent(self, tmp_path, monkeypatch, capsys):
        _, c = _run(tmp_path, monkeypatch, capsys, fail_on={11}, answered_on_bad_day=2)
        assert c["latest_day_below"] == {"deepseek": {"answered": 2, "asked": 3}}


class TestItStaysQuietWhenItShould:
    def test_a_clean_latest_day(self, tmp_path, monkeypatch, capsys):
        out, c = _run(tmp_path, monkeypatch, capsys)
        assert c["latest_day_below"] == {}
        assert "LOST ON THE LATEST DAY" not in out

    def test_an_old_bad_day_does_not_repeat(self, tmp_path, monkeypatch, capsys):
        """A fault that fixed itself is the window rule's business, not this one's."""
        _, c = _run(tmp_path, monkeypatch, capsys, fail_on={9})
        assert c["latest_day_below"] == {}

    def test_a_retired_model_is_not_asked_so_not_named(self, tmp_path, monkeypatch, capsys):
        _, c = _run(tmp_path, monkeypatch, capsys, retired_after=3)
        assert "deepseek" not in c["latest_day_below"]

    def test_a_model_already_below_the_floor_is_named_once(self, tmp_path, monkeypatch, capsys):
        """Under the floor across the window and on the latest day: the existing alarm."""
        _, c = _run(tmp_path, monkeypatch, capsys, fail_on={9, 10, 11})
        assert c["below_floor"] == ["deepseek"]
        assert c["latest_day_below"] == {}


class TestTheWorkflowRaisesIt:
    def test_the_alarm_step_reads_the_new_key(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert 'c.get("latest_day_below")' in text
        assert "c.get('latest_day')" in text

    def test_the_issue_says_a_rerun_does_not_retry_a_failed_answer(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "an answer that failed stays failed" in text

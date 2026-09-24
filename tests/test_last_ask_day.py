"""The last four days of the window ask nothing, and that is not a gap.

`neff.tasks.build_daily_tasks` returns no questions once the days left before
the 11 Dec freeze are no more than its 3-day minimum horizon: a question asked
then could not resolve inside the study. That rule has been in the instrument
since 17 Aug, before registration, so from 8 Dec the daily job runs and
correctly collects nothing.

`scripts/check_days.py` did not know this. It expected a collected day on every
date through the freeze, so on 9, 10, 11 and 12 Dec the daily alarm would have
filed "collection at risk" for a day that could never have had a question, and
the continuity report would have closed the study on four missing days that
were never missing.

Pinned here in both directions: the checker's LAST_ASK_DAY is exactly the
collector's last open day, the days after it are reported as closed rather than
missing, and a real gap or a late last day is still reported as before.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from neff import tasks
from neff.config import DATA_FREEZE
from neff.sources import edgar, fred, kalshi
from scripts import check_days

LAST = check_days.LAST_ASK_DAY
FREEZE = date.fromisoformat(DATA_FREEZE)


def _no_network(*args, **kwargs):
    raise AssertionError("a closed day must not consult any source")


class TestTheCheckerAgreesWithTheCollector:
    def test_the_checker_uses_the_registered_freeze(self):
        assert check_days.WINDOW_END == FREEZE

    @pytest.mark.parametrize("offset", range(1, 8))
    def test_every_day_after_the_last_asks_nothing(self, offset, monkeypatch):
        for source, name in ((kalshi, "select_tasks"), (fred, "state_snapshot"),
                             (edgar, "build_universe_tasks")):
            monkeypatch.setattr(source, name, _no_network)
        # Exactly the call `neff.collect.run_day` makes.
        assert tasks.build_daily_tasks(as_of=LAST + timedelta(days=offset), max_tasks=25) == []

    def test_the_last_day_is_still_open(self, monkeypatch):
        asked = []
        monkeypatch.setattr(fred, "state_snapshot", lambda today: {})
        monkeypatch.setattr(kalshi, "select_tasks", lambda **kw: asked.append(kw) or [])
        monkeypatch.setattr(edgar, "build_universe_tasks", lambda today, max_tasks: [])
        tasks.build_daily_tasks(as_of=LAST, max_tasks=25)
        assert len(asked) == 1, "the collector no longer asks on LAST_ASK_DAY"


def _store(tmp_path, days):
    obs, trows = [], []
    for day in days:
        tid = f"t-{day}"
        trows.append({"task_id": tid, "arm": check_days.PRIMARY_ARM, "state": {"asked_on": day}})
        for model in ("claude_haiku", "gpt_mid"):
            obs.append({"task_id": tid, "model_key": model, "prompt_variant": 0,
                        "forecast": 0.4, "error": None, "created_at": f"{day}T17:30:00+00:00"})
    o, t = tmp_path / "o.jsonl", tmp_path / "t.jsonl"
    o.write_text("".join(json.dumps(r) + "\n" for r in obs))
    t.write_text("".join(json.dumps(r) + "\n" for r in trows))
    return o, t


def _check(tmp_path, monkeypatch, days, now):
    """Run check_days.py --json as of `now` against a store holding `days`."""
    o, t = _store(tmp_path, [d.isoformat() for d in days])

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    monkeypatch.setattr(check_days, "OBSERVATIONS", o)
    monkeypatch.setattr(check_days, "TASKS", t)
    monkeypatch.setattr(check_days, "datetime", Clock)
    monkeypatch.setattr(check_days.sys, "argv", ["check_days.py", "--json"])
    monkeypatch.chdir(tmp_path)
    code = check_days.main()
    return code, json.loads((tmp_path / "continuity.json").read_text())


def _late(day):
    return datetime(day.year, day.month, day.day, 23, 30, tzinfo=timezone.utc)


def _span(first, last):
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


class TestTheClosedDaysAreNotGaps:
    @pytest.mark.parametrize("offset", range(1, 6))
    def test_no_alarm_after_the_last_ask_day(self, offset, tmp_path, monkeypatch, capsys):
        day = LAST + timedelta(days=offset)
        code, c = _check(tmp_path, monkeypatch, _span(LAST - timedelta(days=5), LAST), _late(day))
        assert code == 0
        assert c["today_state"] == "closed"
        assert c["missing_days"] == []
        assert c["today_collected"] is True
        out = capsys.readouterr().out
        assert "Not a gap." in out and "MISSING" not in out

    def test_a_real_gap_before_it_is_still_reported(self, tmp_path, monkeypatch):
        hole = LAST - timedelta(days=1)
        days = [d for d in _span(LAST - timedelta(days=5), LAST) if d != hole]
        code, c = _check(tmp_path, monkeypatch, days, _late(LAST + timedelta(days=1)))
        assert c["missing_days"] == [hole.isoformat()]

    def test_the_last_day_itself_still_alarms_when_late(self, tmp_path, monkeypatch):
        days = _span(LAST - timedelta(days=5), LAST - timedelta(days=1))
        code, c = _check(tmp_path, monkeypatch, days, _late(LAST))
        assert code == 1
        assert c["today_state"] == "late"
        assert c["missing_days"] == [LAST.isoformat()]

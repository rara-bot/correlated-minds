"""The dated-commitment reminder must fire on the right days, and only then.

A reminder that is wrong is worse than none: one that never fires loses the
Week-5 prediction, and one that fires every morning becomes wallpaper and loses
it just as surely. So the transitions are pinned here against the dates the
pre-registration actually fixes, read from the modules that enforce them.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neff import prediction  # noqa: E402
from neff.config import DATA_FREEZE  # noqa: E402
from scripts import milestones  # noqa: E402

OPENS = datetime.fromisoformat(prediction.PUBLISH_NOT_BEFORE)


def _state(when: datetime, key: str) -> str:
    return next(m for m in milestones.collect(when) if m.key == key).state


def _at(*, days: float) -> datetime:
    return OPENS + timedelta(days=days)


class TestTheDatesComeFromTheRules:
    def test_week5_window_is_the_one_the_publisher_enforces(self):
        # Not re-typed in the reminder: a reminder that can disagree with the
        # rule would tell you the date has not arrived on the morning after it
        # has.
        m = next(m for m in milestones.collect(_at(days=-30)) if m.key == "week5_prediction")
        assert m.opens == datetime.fromisoformat(prediction.PUBLISH_NOT_BEFORE)

    def test_freeze_is_the_registered_freeze(self):
        m = next(m for m in milestones.collect(_at(days=-30)) if m.key == "data_freeze")
        assert m.opens.date().isoformat() == DATA_FREEZE


class TestWeek5Transitions:
    @pytest.mark.parametrize("days,expected", [
        (-60, "pending"),
        (-milestones.LEAD_DAYS - 1, "pending"),
        (-milestones.LEAD_DAYS + 0.5, "due_soon"),
        (-0.5, "due_soon"),
        (0.5, "due"),
        (milestones.GRACE_DAYS - 0.5, "due"),
        (milestones.GRACE_DAYS + 1, "overdue"),
        (60, "overdue"),
    ])
    def test_pending_then_due_then_overdue(self, days, expected, monkeypatch):
        # The artefact does not exist, which is the whole point of the reminder.
        monkeypatch.setattr(milestones, "PREDICTION_FILE", ROOT / "predictions" / "does-not-exist.json")
        assert _state(_at(days=days), "week5_prediction") == expected

    def test_publishing_silences_it_forever(self, monkeypatch, tmp_path):
        published = tmp_path / "week5-prediction.json"
        published.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(milestones, "PREDICTION_FILE", published)
        # Including long after the window closed: the file is the evidence, and
        # once it exists there is nothing left for a person to do.
        for days in (-60, 0.5, 60):
            assert _state(_at(days=days), "week5_prediction") == "done"

    def test_it_is_quiet_today(self, monkeypatch):
        """Today is well before the window, so the daily run says nothing."""
        monkeypatch.setattr(milestones, "PREDICTION_FILE", ROOT / "predictions" / "does-not-exist.json")
        today = datetime(2026, 9, 16, tzinfo=timezone.utc)
        flagged = [m for m in milestones.collect(today) if m.state in milestones.NEEDS_ATTENTION]
        assert flagged == []


class TestFreeze:
    def test_a_freeze_is_never_overdue(self):
        """'You are 40 days late to stop collecting' is nonsense, so it reads done."""
        after = datetime.fromisoformat(f"{DATA_FREEZE}T00:00:00+00:00") + timedelta(days=40)
        assert _state(after, "data_freeze") == "done"

    def test_it_warns_before_the_last_day(self):
        before = datetime.fromisoformat(f"{DATA_FREEZE}T00:00:00+00:00") - timedelta(days=3)
        assert _state(before, "data_freeze") == "due_soon"


class TestItCannotBreakTheDailyRun:
    def test_exit_status_is_always_zero(self, capsys):
        # It runs inside always(), next to the steps that commit the day. A
        # non-zero exit would paint the run red on a morning when nothing is
        # wrong, and teach us to skim the alarm that means something.
        assert milestones.main() == 0
        assert "today (UTC)" in capsys.readouterr().out

    def test_json_is_written_next_to_continuity(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["milestones.py", "--json"])
        assert milestones.main() == 0
        capsys.readouterr()
        import json
        payload = json.loads((tmp_path / "milestones.json").read_text(encoding="utf-8"))
        assert {m["key"] for m in payload["milestones"]} == {"week5_prediction", "data_freeze"}
        assert "flagged" in payload

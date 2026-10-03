#!/usr/bin/env python
"""Are the study's one-shot, dated commitments still ahead of us -- or overdue?

Most of what this study promises, it keeps automatically: the daily job collects,
resolves, prices and commits without anyone watching, and `check_days.py` raises
an alarm when that record develops a hole.

Two registered commitments are not like that. Each happens exactly once, on a
date fixed in the pre-registration, by a human running a command:

    1. The Week-5 prediction (PREREGISTRATION.md 5.3, deviation 18).
       `scripts/week5_prediction.py --publish` unblinds weeks 1-5, fits H1 on
       them, and writes a prediction about a release that has not happened. It
       REFUSES before 2026-10-02 20:00 UTC and REFUSES to run twice, which is
       what makes the published file evidence rather than a claim.

    2. The data freeze (PREREGISTRATION.md 9), 2026-12-11.

Both are unrecoverable in the same way a missed collection day is. A prediction
published on 3 October is not the registered prediction: the plan says it is made
from weeks 1-5 and before the target release, and every day of drift makes "we
committed to this in advance" weaker precisely where the study's whole claim
lives. Nothing in the repository mentioned either date. The daily run alarms
loudly about a missing day and said nothing at all about the one calendar entry
that cannot be re-run.

So this reports, for each milestone, one of:

    pending    it is not time yet
    due        the window is open and the thing has not been done
    done       the artefact it produces exists
    overdue    the window opened and closed and it was never done

Exit status is always 0. This is a notice, not a fault: a milestone that is due
is the study working as planned, not a failure, and a step that exits non-zero
inside `always()` would paint the daily run red on a day when nothing is wrong.
The workflow decides what to escalate; this script only reports.

    ./.venv/bin/python scripts/milestones.py
    ./.venv/bin/python scripts/milestones.py --json
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neff import prediction  # noqa: E402
from neff.config import DATA_FREEZE  # noqa: E402

# Read from the modules that enforce them, never re-typed here. A reminder that
# can drift from the rule it is reminding you about is worse than no reminder:
# it tells you the date has not arrived on the morning after it has.
PREDICTION_FILE = ROOT / "predictions" / "week5-prediction.json"

# How long before a window opens to start saying so. Long enough to notice and
# plan around a school week, short enough that the notice is not wallpaper by
# the time it matters.
LEAD_DAYS = 7

# After the window opens, how long a thing may stay undone before "due" becomes
# "overdue". The Week-5 prediction is about a release that has not happened yet,
# and the pool of releases still ahead shrinks every day, so this is deliberately
# short -- days, not weeks.
GRACE_DAYS = 2


@dataclass
class Milestone:
    key: str
    title: str
    opens: datetime
    state: str = "pending"
    days_until: int = 0
    detail: str = ""
    how: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "opens": self.opens.isoformat(),
            "state": self.state,
            "days_until": self.days_until,
            "detail": self.detail,
            "how": self.how,
        }


def _display(path: Path) -> str:
    """Repo-relative when it can be, absolute otherwise -- never an exception.

    A reminder is not worth a traceback. `relative_to` raises for any path
    outside the repository, which is exactly what a test harness hands it.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _classify(opens: datetime, now: datetime, done: bool) -> str:
    """pending -> due -> overdue, unless it is already done."""
    if done:
        return "done"
    if now < opens - timedelta(days=LEAD_DAYS):
        return "pending"
    if now < opens:
        return "due_soon"
    if now < opens + timedelta(days=GRACE_DAYS):
        return "due"
    return "overdue"


def week5(now: datetime) -> Milestone:
    opens = datetime.fromisoformat(prediction.PUBLISH_NOT_BEFORE)
    done = PREDICTION_FILE.exists()
    m = Milestone(
        key="week5_prediction",
        title="Publish the registered Week-5 prediction",
        opens=opens,
        state=_classify(opens, now, done),
        days_until=(opens.date() - now.date()).days,
    )
    if done:
        m.detail = f"{_display(PREDICTION_FILE)} exists; the prediction is never revised."
    else:
        m.detail = (
            "The window opens once 2026-10-02 has collected and its settlements are "
            "recorded. The script refuses before then, refuses on a copy of the record "
            "that is not current, and refuses to run twice."
        )
        # `git pull` comes first because the record is committed by the daily job
        # on GitHub, not on the machine that publishes; `--check` says READY or
        # names what to wait for, and applies exactly what --publish refuses on.
        m.how = [
            "git pull --ff-only                                        # the record lives on GitHub",
            "./.venv/bin/python scripts/week5_prediction.py --check    # READY, or what to wait for",
            "./.venv/bin/python scripts/week5_prediction.py --publish  # the registered look",
            "git add predictions/ && git commit -m 'Week-5 prediction' && git push  # the file IS the evidence",
            "Post the printed SHA-256 publicly (Zenodo new version, OSF wiki) the same day.",
        ]
    return m


def freeze(now: datetime) -> Milestone:
    opens = datetime.fromisoformat(f"{DATA_FREEZE}T00:00:00+00:00")
    m = Milestone(
        key="data_freeze",
        title="Data freeze -- collection ends",
        opens=opens,
        state=_classify(opens, now, done=False),
        days_until=(opens.date() - now.date()).days,
        detail=f"PREREGISTRATION.md 9. Last collection day is {DATA_FREEZE}.",
    )
    # A freeze is a date that arrives, not a task that can be missed, so it never
    # reads as overdue -- saying "you are 40 days late to stop collecting" would
    # be nonsense. After the date it is simply done.
    if m.state == "overdue":
        m.state = "done"
        m.detail = f"Collection ended {DATA_FREEZE}."
    elif m.state in ("due", "due_soon"):
        m.how = [
            "Confirm the last day collected in full before the window closes.",
            "./.venv/bin/python scripts/week5_prediction.py --evaluate  # after the freeze",
        ]
    return m


def collect(now: Optional[datetime] = None) -> List[Milestone]:
    now = now or datetime.now(timezone.utc)
    return [week5(now), freeze(now)]


NEEDS_ATTENTION = ("due_soon", "due", "overdue")

_LABEL = {
    "pending": "pending",
    "due_soon": "DUE SOON",
    "due": "DUE NOW",
    "overdue": "OVERDUE",
    "done": "done",
}


def main() -> int:
    now = datetime.now(timezone.utc)
    milestones = collect(now)

    print(f"today (UTC)    : {now.date().isoformat()}")
    print()
    for m in milestones:
        when = m.opens.date().isoformat()
        if m.days_until > 0:
            offset = f"in {m.days_until} day(s)"
        elif m.days_until == 0:
            offset = "today"
        else:
            offset = f"{-m.days_until} day(s) ago"
        print(f"  [{_LABEL[m.state]:8s}] {m.title}")
        print(f"             {when} ({offset})")
        if m.detail:
            print(f"             {m.detail}")
        for line in m.how:
            print(f"               $ {line}" if line.startswith("./") or line.startswith("git")
                  else f"               - {line}")
        print()

    flagged = [m for m in milestones if m.state in NEEDS_ATTENTION]
    if flagged:
        print("Needs a person: " + ", ".join(m.title for m in flagged))
    else:
        print("Nothing needs a person today.")

    if "--json" in sys.argv:
        Path("milestones.json").write_text(
            json.dumps(
                {
                    "today": now.date().isoformat(),
                    "milestones": [m.as_dict() for m in milestones],
                    "flagged": [m.as_dict() for m in flagged],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

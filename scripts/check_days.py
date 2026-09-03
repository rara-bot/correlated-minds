#!/usr/bin/env python
"""Is the daily record actually unbroken?

The study's central evidentiary claim is that every forecast was committed to a
public history before its outcome existed. That claim is only as good as the
*continuity* of the record: a day that silently failed to collect is a hole in
the evidence, and -- because a forecast cannot honestly be back-dated -- it is a
hole that can never be filled. `neff.collect` deliberately exposes no `--as-of`
flag for exactly that reason.

So the only defence is noticing on the day itself, while a manual re-run can
still save it. This script answers three questions:

    1. Did today collect at all?
    2. Is any day between the first observation and today missing?
    3. Is any model drifting toward the 80% coverage floor of §3.3?

Exit status is 1 if today is missing or the run is broken, so CI and cron can
treat it as an alarm rather than a report.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OBSERVATIONS = ROOT / "data" / "observations.jsonl"
TASKS = ROOT / "data" / "tasks.jsonl"

PRIMARY_ARM = "ws1_prospective"
COVERAGE_FLOOR = 0.80          # PREREGISTRATION.md 3.3
WINDOW_END = date(2026, 12, 11)  # the registered freeze date

# The cron in .github/workflows/daily.yml. GitHub does not honour it precisely:
# across the first twelve scheduled runs the job started anywhere from 30
# minutes to 10 hours late, which is ordinary queueing for scheduled workflows
# on a busy host. So "today has not collected yet" only means something after
# that delay has had time to play out -- alarm any earlier and the alarm is
# noise, which is worse than no alarm at all.
CRON_UTC = time(13, 10)
DELAY_GRACE_HOURS = 10


def _read(path: Path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> int:
    tasks = _read(TASKS)
    arm_of = {t["task_id"]: t.get("arm") for t in tasks}

    by_day: dict[str, list] = defaultdict(list)
    for obs in _read(OBSERVATIONS):
        if arm_of.get(obs["task_id"]) != PRIMARY_ARM:
            continue
        by_day[obs["created_at"][:10]].append(obs)

    if not by_day:
        print("no observations on the primary arm yet")
        return 1

    days = sorted(by_day)
    now = datetime.now(timezone.utc)
    today = now.date()
    first = date.fromisoformat(days[0])

    due_at = datetime.combine(today, CRON_UTC, tzinfo=timezone.utc)
    late_after = due_at + timedelta(hours=DELAY_GRACE_HOURS)
    if now < due_at:
        today_state = "not_due"
    elif now < late_after:
        today_state = "pending"
    else:
        today_state = "late"

    print(f"arm            : {PRIMARY_ARM}")
    print(f"first collected: {days[0]}")
    print(f"today (UTC)    : {today.isoformat()}")
    print()

    # ---- per-day continuity -------------------------------------------------
    expected, missing = [], []
    cursor = first
    horizon = min(today, WINDOW_END)
    while cursor <= horizon:
        expected.append(cursor.isoformat())
        cursor += timedelta(days=1)

    print(f"{'day':<12}{'obs':>6}{'usable':>8}{'models':>8}")
    for day in expected:
        rows = by_day.get(day, [])
        if not rows:
            missing.append(day)
            if day == today.isoformat():
                note = {"not_due": "not due yet",
                        "pending": "due, still within the usual delay",
                        "late": "LATE"}[today_state]
            else:
                note = "MISSING"
            print(f"{day:<12}{'--':>6}{'--':>8}{'--':>8}   <-- {note}")
            continue
        usable = [o for o in rows if o.get("forecast") is not None and not o.get("error")]
        models = {o["model_key"] for o in rows}
        print(f"{day:<12}{len(rows):>6}{len(usable):>8}{len(models):>8}")

    # ---- coverage against the 3.3 floor -------------------------------------
    seen: dict[str, int] = defaultdict(int)
    good: dict[str, int] = defaultdict(int)
    for rows in by_day.values():
        for o in rows:
            seen[o["model_key"]] += 1
            if o.get("forecast") is not None and not o.get("error"):
                good[o["model_key"]] += 1

    print()
    print("coverage to date (floor 80%, PREREGISTRATION.md 3.3)")
    below = []
    for model in sorted(seen):
        frac = good[model] / seen[model]
        mark = ""
        if frac < COVERAGE_FLOOR:
            below.append(model)
            mark = "   <-- BELOW FLOOR"
        print(f"  {model:<18}{good[model]:>4}/{seen[model]:<4}{frac:>7.1%}{mark}")

    # ---- verdict ------------------------------------------------------------
    print()
    problems = False

    hard_missing = [d for d in missing
                    if d != today.isoformat() or today_state == "late"]
    if hard_missing:
        problems = True
        print(f"MISSING DAYS: {len(hard_missing)} -- {', '.join(hard_missing)}")
        stale = [d for d in missing if d != today.isoformat()]
        if stale:
            print("  Days before today cannot be recovered: a forecast collected")
            print("  now would be stamped with a day the model never saw. Record")
            print("  them as lost in PREREGISTRATION.md 11 rather than back-filling.")
        if today.isoformat() in missing:
            if today_state == "late":
                print("  TODAY is LATE -- past the cron plus its usual delay.")
                print("  A manual run can still save it:")
                print("  Actions -> daily-collection -> Run workflow.")
            elif today_state == "pending":
                print(f"  TODAY is due but not in yet ({now:%H:%M} UTC). Still inside")
                print(f"  the usual delay; treat as an alarm after {late_after:%H:%M} UTC.")
            else:
                print(f"  TODAY is not due until {CRON_UTC:%H:%M} UTC. Not a fault.")

    if below:
        print(f"BELOW COVERAGE FLOOR: {', '.join(below)}")
        print("  A model under 80% leaves the primary panel (3.3). Check whether")
        print("  this is one bad day already recovered, or an ongoing fault.")

    if not problems and not below:
        collected = len(expected) - len(missing)
        print(f"Unbroken: {collected} day(s) collected, no gaps, "
              f"every model above the floor.")

    # Only a LATE today is actionable enough to fail on. A historic gap is
    # permanent, and failing forever on it would train the alarm to be ignored;
    # a today that is merely not due yet is not news at all.
    return 1 if (today.isoformat() in missing and today_state == "late") else 0


if __name__ == "__main__":
    sys.exit(main())

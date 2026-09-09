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

# Coverage is judged over a trailing window rather than over all history. A
# model that lost a single day early on carries that day in its cumulative
# figure for weeks, which would either fire a standing alarm or -- far worse --
# teach us to ignore the one that matters. The question worth alarming on is
# "is this model failing *now*", and that is a rolling question.
COVERAGE_WINDOW_DAYS = 7
COVERAGE_MIN_DAYS = 3          # too few days to judge a trend

# A model is alarmed on only when it is below the floor over the window AND was
# still below it on the most recent collected day. The window alone is not
# enough: qwen lost all of 1 Sep to an upstream routing fault and has been at
# 100% every day since, yet its 7-day figure stays under 80% until that day
# ages out. Waking someone each morning for a fault that fixed itself is how an
# alarm stops being read -- and the alarm nobody reads is the one that misses
# the day that actually matters. Models under the floor on the window alone are
# still printed, under "watching", because the 3.3 consequence is real even
# when the cause is historic.


def _read(path: Path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _coverage(rows) -> tuple[int, int]:
    good = sum(1 for o in rows
               if o.get("forecast") is not None and not o.get("error"))
    return good, len(rows)


# --- market state -------------------------------------------------------------
#
# The stress leg of H1 is a tercile contrast on `vix_level`, and it is the one
# leg that depends on markets cooperating (PREREGISTRATION.md §10, limitation 5).
# If a genuine shock lands inside the window it will be a handful of days, and
# those days ARE the stress leg -- losing one costs incomparably more than losing
# an ordinary Tuesday. Nothing here can prevent that, but silence is the failure
# mode worth removing: a spike that nobody noticed is a spike nobody checked
# collected.
#
# NOTHING IN THIS SECTION MAY FAIL A RUN. It is reporting, not a gate: it never
# touches the exit status and is wrapped so a malformed state field prints a note
# instead of halting collection. A day that does not collect can never be filled.

# Absolute bands, for a reader who does not know this study's own range.
VIX_BANDS = ((30.0, "SEVERE"), (25.0, "stressed"), (20.0, "elevated"),
             (15.0, "normal"), (0.0, "calm"))


def _vix_band(v: float) -> str:
    for floor, name in VIX_BANDS:
        if v >= floor:
            return name
    return "calm"


def _market_state(tasks) -> dict:
    """VIX per collection day, and whether today is an extreme worth noticing."""
    by_day = {}
    for t in tasks:
        # FAIL-CLOSED on the arm label, the same rule panel.load_panel uses. The
        # 36 unlabelled task rows predate the label and are all pre-registration
        # pilot (2026-08-17/21/22); admitting them would report a VIX range the
        # stress leg will never see.
        if t.get("arm") != PRIMARY_ARM:
            continue
        st = t.get("state") or {}
        d, v = st.get("asked_on"), st.get("vix_level")
        if isinstance(d, str) and isinstance(v, (int, float)):
            by_day[d] = float(v)
    return by_day


def _print_market_state(tasks, today: str) -> dict:
    out = {}
    try:
        by_day = _market_state(tasks)
        if not by_day:
            return out
        days = sorted(by_day)
        vals = [by_day[d] for d in days]
        latest_day = days[-1]
        latest = by_day[latest_day]
        distinct = sorted(set(vals))

        print()
        print("market state -- the stress leg of H1 lives on this variable")
        print(f"  vix range      : {min(vals):.2f} - {max(vals):.2f} "
              f"(spread {max(vals) - min(vals):.2f}) over {len(days)} day(s)")
        print(f"  distinct values: {len(distinct)}  "
              f"({len(days) - len(distinct)} day(s) repeat an earlier state)")
        print(f"  latest         : {latest:.2f} on {latest_day} [{_vix_band(latest)}]")

        out = {"vix_latest": latest, "vix_latest_day": latest_day,
               "vix_min": min(vals), "vix_max": max(vals),
               "vix_distinct": len(distinct), "vix_band": _vix_band(latest),
               "vix_new_high": False, "vix_notable": False}

        prior = [by_day[d] for d in days[:-1]]
        # The maximum EXCLUDING today. `vix_max` includes it, so a consumer
        # asking "how big a jump was this?" needs the prior bar, not the new one.
        out["vix_max_prior"] = max(prior) if prior else None
        if prior:
            if latest > max(prior):
                out["vix_new_high"] = out["vix_notable"] = True
                print(f"  *** NEW HIGH: {latest:.2f} exceeds every earlier day "
                      f"(prev max {max(prior):.2f}, {latest_day}).")
                print(f"      This day is worth more to H1 than an ordinary one. "
                      f"Confirm it collected in full before anything else.")
            elif latest < min(prior):
                out["vix_notable"] = True
                print(f"  *** NEW LOW: {latest:.2f} below every earlier day "
                      f"(prev min {min(prior):.2f}). Widens the bottom tercile.")
        if latest >= 25.0:
            out["vix_notable"] = True
            print(f"  *** {_vix_band(latest).upper()} in absolute terms "
                  f"(VIX >= 25). A genuine stress regime, if it holds.")

        if len(distinct) >= 3:
            mid = distinct[len(distinct) // 3], distinct[(2 * len(distinct)) // 3]
            print(f"  tercile cuts   : {mid[0]:.2f} / {mid[1]:.2f}")
        else:
            print(f"  tercile cuts   : not yet meaningful "
                  f"({len(distinct)} distinct value(s))")
    except Exception as exc:                                       # noqa: BLE001
        # Deliberately swallowed. This is a report; it must never be the reason
        # a day fails to collect.
        print(f"\nmarket state   : unavailable ({type(exc).__name__})")
    return out


def main() -> int:
    emit_json = "--json" in sys.argv
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
    collected_days = [d for d in days]
    window = collected_days[-COVERAGE_WINDOW_DAYS:]
    judgeable = len(window) >= COVERAGE_MIN_DAYS

    latest = window[-1] if window else None
    seen: dict[str, int] = defaultdict(int)
    good: dict[str, int] = defaultdict(int)
    wseen: dict[str, int] = defaultdict(int)
    wgood: dict[str, int] = defaultdict(int)
    lseen: dict[str, int] = defaultdict(int)
    lgood: dict[str, int] = defaultdict(int)
    for day, rows in by_day.items():
        for o in rows:
            ok = o.get("forecast") is not None and not o.get("error")
            seen[o["model_key"]] += 1
            good[o["model_key"]] += ok
            if day in window:
                wseen[o["model_key"]] += 1
                wgood[o["model_key"]] += ok
            if day == latest:
                lseen[o["model_key"]] += 1
                lgood[o["model_key"]] += ok

    print()
    print(f"coverage -- floor {COVERAGE_FLOOR:.0%} (PREREGISTRATION.md 3.3), "
          f"judged on the last {len(window)} collected day(s)")
    if not judgeable:
        print(f"  (only {len(window)} day(s) so far; a trend needs "
              f"{COVERAGE_MIN_DAYS} -- shown, not alarmed on)")
    print(f"  {'model':<18}{'window':>13}{'latest day':>15}{'all time':>16}")
    below, watching = [], []
    for model in sorted(seen):
        wfrac = wgood[model] / wseen[model] if wseen[model] else 0.0
        lfrac = lgood[model] / lseen[model] if lseen[model] else 1.0
        frac = good[model] / seen[model]
        mark = ""
        if wfrac < COVERAGE_FLOOR:
            if not judgeable:
                mark = "   <-- low, too early to judge"
            elif lfrac < COVERAGE_FLOOR:
                below.append(model)
                mark = "   <-- BELOW FLOOR, STILL FAILING"
            else:
                watching.append(model)
                mark = "   <-- under floor, but recovered"
        print(f"  {model:<18}{wgood[model]:>4}/{wseen[model]:<3}{wfrac:>6.1%}"
              f"{lgood[model]:>6}/{lseen[model]:<3}{lfrac:>6.1%}"
              f"{good[model]:>7}/{seen[model]:<4}{frac:>6.1%}{mark}")

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
        print(f"BELOW COVERAGE FLOOR AND STILL FAILING: {', '.join(below)}")
        print("  Under 80% across the window and again on the most recent day.")
        print("  A model under the floor leaves the primary panel (3.3).")

    if watching:
        print(f"WATCHING (under floor, recovered): {', '.join(watching)}")
        print(f"  Below 80% across the last {len(window)} collected days, but at or")
        print("  above it on the most recent one -- an old bad day still inside the")
        print("  window. Not alarmed on. It clears as the bad day ages out.")

    if not problems and not below:
        collected = len(expected) - len(missing)
        low = watching or [m for m in sorted(wseen)
                           if wseen[m] and wgood[m] / wseen[m] < COVERAGE_FLOOR]
        if low:
            # Accurate rather than reassuring: these models ARE under the floor
            # over the window, whether or not the cause is still live.
            why = ("recovered since" if watching
                   else f"only {len(window)} of {COVERAGE_MIN_DAYS} days to judge")
            print(f"Unbroken: {collected} day(s) collected, no gaps. "
                  f"Watching {', '.join(low)} -- under the floor, {why}.")
        else:
            print(f"Unbroken: {collected} day(s) collected, no gaps, "
                  f"every model above the floor.")

    market = _print_market_state(tasks, today.isoformat())

    if emit_json:
        Path("continuity.json").write_text(json.dumps({
            **market,
            "today": today.isoformat(),
            "today_state": today_state,
            "today_collected": today.isoformat() not in missing,
            "missing_days": hard_missing,
            "below_floor": below,
            "window_days": len(window),
            "coverage_window": {m: round(wgood[m] / wseen[m], 4)
                                for m in sorted(wseen) if wseen[m]},
        }, indent=2), encoding="utf-8")

    # Only a LATE today is actionable enough to fail on. A historic gap is
    # permanent, and failing forever on it would train the alarm to be ignored;
    # a today that is merely not due yet is not news at all.
    return 1 if (today.isoformat() in missing and today_state == "late") else 0


if __name__ == "__main__":
    sys.exit(main())

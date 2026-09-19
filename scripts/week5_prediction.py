#!/usr/bin/env python
"""Rehearse, check, publish, or evaluate the registered Week-5 prediction (PREREGISTRATION.md 5.3).

Every rule this script applies is fixed in PREREGISTRATION.md 11, deviations 18
and 22, and implemented in `neff/prediction.py`.

  (no flag)    REHEARSAL. Outcomes are permuted and nothing is written. Run it any
               time to watch the whole pipeline work; its numbers are meaningless
               by construction.

  --check      Is this copy of the record ready to publish from? Reads GitHub and
               Kalshi, writes nothing, and prints READY or what to wait for. It
               applies exactly the conditions --publish refuses on.

  --publish    On or after 2026-10-02 20:00 UTC, once that day's collection has
               run and its settlements are recorded. This is the registered look:
               it unblinds weeks 1-5, fits H1 on them, computes X and Y, writes
               predictions/week5-prediction.json and predictions/week5-h1-fit.json,
               and prints the SHA-256 to post publicly. It refuses to run twice,
               and it refuses to run on a copy of the record that is not current.

  --evaluate   Once a qualifying release has settled, or after the 11 Dec freeze.
               Unblinds the holdout and writes the verdict: HIT, MISS or UNTESTED.

On 2 October, in this order:

    git pull --ff-only
    ./.venv/bin/python scripts/week5_prediction.py --check
    ./.venv/bin/python scripts/week5_prediction.py --publish
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from neff import h1, prediction, surprise  # noqa: E402
from scripts import release_surprise  # noqa: E402
from neff.analysis import _permute_outcomes, apply_registered_exclusions, resolution_event  # noqa: E402
from neff.config import PRIMARY_ARM, RESOLUTIONS_PATH, TASKS_PATH  # noqa: E402
from neff.panel import load_panel  # noqa: E402
from neff.sources import kalshi  # noqa: E402
from neff.sources.http import FetchError  # noqa: E402
from neff.store import JsonlStore  # noqa: E402

OUT_DIR = ROOT / "predictions"
PREDICTION_FILE = OUT_DIR / "week5-prediction.json"
H1_FIT_FILE = OUT_DIR / "week5-h1-fit.json"
EVALUATION_FILE = OUT_DIR / "week5-evaluation.json"


def _clean(value):
    """JSON without NaN: undefined is null, never a number that looks like one."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


def _git(*args: str) -> str:
    return _run_git(*args).stdout.decode("utf-8", "replace").strip()


def _inputs(blind: bool, seed: int = 0):
    panel = load_panel()
    panel, exclusions = apply_registered_exclusions(panel)
    if blind and panel.n_tasks:
        panel = _permute_outcomes(panel, seed)
    tasks = [t for t in JsonlStore(TASKS_PATH).read() if t.get("arm") == PRIMARY_ARM]
    return panel, prediction.event_close_times(tasks), h1.load_release_surprises(), exclusions


def _threshold() -> float:
    rows = [r for r in JsonlStore(h1.RELEASE_SURPRISE_PATH).read() if r.get("role") == "reference"]
    recomputed = surprise.percentile_80(r.get("surprise") for r in rows)
    registered = prediction.REGISTERED_P80
    if registered is None or recomputed is None:
        raise SystemExit("the registered threshold is not recorded; run "
                         "scripts/release_surprise.py --reference first")
    if abs(recomputed - registered) > 1e-12:
        raise SystemExit(f"REFUSING: the reference releases give {recomputed}, but deviation 18 "
                         f"registers {registered}. Do not publish until that is explained.")
    return registered


def _write(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_clean(payload), indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record_settled_surprises() -> None:
    """Every listed release that has fully settled gets its surprise first.

    Market prices and settlements only, never a forecast (deviation 18). A
    release not yet fully settled is left for a later run.
    """
    store = JsonlStore(h1.RELEASE_SURPRISE_PATH)
    failures = release_surprise.study(store, store.existing_ids("kalshi_event"))
    if failures:
        raise SystemExit(f"{failures} release(s) could not be read from Kalshi; retry "
                         f"before publishing so no calibration surprise is missing")


# --- is this copy of the record current? (PREREGISTRATION.md 11, deviation 22) -------
#
# The publisher runs on the operator's machine. The record it unblinds is written by
# the daily job on GitHub, which commits each day's questions, answers and
# settlements some hours after 13:10 UTC. A copy that has not pulled that commit is
# missing the day's questions and, worse, its settlements -- and deviation 18 (5)
# registers the calibration as EVERY eligible release closing by 2026-10-02 23:59
# UTC. On 2026-09-19 three listed releases had settled with five or more task-days;
# September payrolls, asked every day and closing 2026-10-02 12:29 UTC, is the only
# other one asked so far that closes inside the window, and it is the fourth release
# the registered fit needs (prediction.MIN_FIT_EVENTS). Published from a copy that
# had not pulled it, the prediction would be a different prediction -- and the rule
# that it is never revised would make that permanent.
#
# So publication waits for the record, never the other way round. Every condition
# below is a count of questions, settlements and commits; none reads an outcome.

# How long a listed release that has closed but not settled may hold publication.
# Kalshi settled every listed release of the study's first three weeks within about
# an hour of its close, so two days is only ever reached if something is wrong, and
# then publishing without it is better than never publishing.
SETTLEMENT_GRACE = timedelta(days=2)

# Kalshi statuses of a market that is still trading, or not yet open.
OPEN_STATUSES = ("open", "active", "initialized", "unopened")

# The one file --publish itself writes under data/ (deviation 18 (6): it "first
# records the surprise of every fully settled listed release"). Rows it appended on
# an earlier attempt are the only difference from GitHub a retry may carry.
SELF_WRITTEN = "data/release_surprise.jsonl"


def _ts(value) -> Optional[datetime]:
    return prediction._ts(value or "")


def _window_end() -> datetime:
    return datetime.fromisoformat(prediction.CALIBRATION_CLOSES_BY)


def _holding(now: datetime) -> bool:
    """True while an unsettled calibration release may still hold publication."""
    return now < datetime.fromisoformat(prediction.PUBLISH_NOT_BEFORE) + SETTLEMENT_GRACE


def _appended_only(path: str) -> bool:
    """Does the local file consist of GitHub's copy plus appended rows?"""
    upstream = _run_git("show", f"origin/main:{path}")
    if upstream.returncode != 0:
        return False
    try:
        local = (ROOT / path).read_bytes()
    except OSError:
        return False
    return local.startswith(upstream.stdout)


def git_problems() -> List[str]:
    """This copy must be GitHub's record: not behind it, and its data unaltered."""
    fetched = _run_git("fetch", "--quiet", "origin", "main")
    if fetched.returncode != 0:
        why = (fetched.stderr or fetched.stdout).decode("utf-8", "replace").strip()[:200]
        return [f"could not reach GitHub to confirm this copy of the record is current "
                f"({why or 'git fetch failed'}). Connect to the internet and retry."]
    if _run_git("merge-base", "--is-ancestor", "origin/main", "HEAD").returncode != 0:
        behind = _git("rev-list", "--count", "HEAD..origin/main") or "some"
        return [f"this copy is {behind} commit(s) behind GitHub, so it is missing data the "
                f"daily job has already committed. Run:  git pull --ff-only  "
                f"(if git refuses because of {SELF_WRITTEN}, first run:  "
                f"git checkout -- {SELF_WRITTEN})"]
    problems = []
    for path in sorted(set(_git("diff", "--name-only", "origin/main", "--", "data/").splitlines())):
        if path == SELF_WRITTEN and _appended_only(path):
            continue
        problems.append(f"{path} differs from GitHub's copy. The record is written only by "
                        f"the daily job; restore it with:  git checkout origin/main -- {path}")
    # Not _git(): porcelain lines are column-aligned, and stripping the output
    # would eat the first line's leading status column.
    status = _run_git("status", "--porcelain", "--untracked-files=all", "--",
                      "data/", "neff/", "scripts/").stdout.decode("utf-8", "replace")
    for line in status.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        if path.startswith("data/") and code != "??":
            continue                                   # judged against GitHub above
        if path.startswith("data/"):
            problems.append(f"{path} is not part of GitHub's record; move it out of data/.")
        else:
            problems.append(f"{path} has uncommitted changes. The prediction records the "
                            f"commit of the code that made it, so commit or undo them first.")
    return problems


def collection_problems(tasks: List[Dict], now: datetime) -> List[str]:
    """Weeks 1-5 end with 2026-10-02's questions; wait for them while that day lasts."""
    day = prediction.PREDICTION_DATE
    if any(str(t.get("asked_at", ""))[:10] == day for t in tasks):
        return []
    if now.date().isoformat() > day:
        return []                                      # lost, not late: see readiness()
    return [f"{day}'s collection is not in this copy yet, and weeks 1-5 end with it. Wait "
            f"for the daily job to commit it (or start it: GitHub -> Actions -> "
            f"daily-collection -> Run workflow), then  git pull --ff-only  and retry."]


def _calibration_refs(tasks: List[Dict], resolved: Set[str]) -> Dict[str, datetime]:
    """Unresolved event questions asked by 2026-10-02 that close inside the window."""
    out: Dict[str, datetime] = {}
    for task in tasks:
        if task.get("kind") != "event" or str(task.get("task_id")) in resolved:
            continue
        if str(task.get("asked_at", ""))[:10] > prediction.PREDICTION_DATE:
            continue
        close, ref = _ts(task.get("resolves_after")), str(task.get("source_ref") or "")
        if ref and close is not None and close <= _window_end():
            out[ref] = max(close, out.get(ref, close))
    return out


def settlement_problems(tasks: List[Dict], resolved: Set[str], now: datetime,
                        market: Callable[[str], Optional[Dict]] = None) -> List[str]:
    """No settlement Kalshi has published may be missing from the record.

    A settled contract the copy has not recorded always blocks: that is the record
    being behind, whatever the release. A listed release that has closed but not
    settled, or closes later than now, blocks only within SETTLEMENT_GRACE, because
    it decides X and Y; any other question simply enters the H1 fit if it has
    settled by the time of publication.
    """
    market = market or kalshi.fetch_market
    problems = []
    for ref, close in sorted(_calibration_refs(tasks, resolved).items(), key=lambda kv: kv[1]):
        listed = surprise.is_release_event(resolution_event(ref))
        if close > now:
            if listed and _holding(now):
                problems.append(f"{ref} closes at {close:%Y-%m-%d %H:%M} UTC, inside the "
                                f"calibration window. Publish after it has settled.")
            continue
        state = market(ref)
        if state is None:
            problems.append(f"could not read {ref} from Kalshi to confirm whether it has "
                            f"settled. Retry in a few minutes.")
            continue
        if kalshi.settlement_of(state) is not None:
            problems.append(f"Kalshi has settled {ref}, but this copy of the record has not "
                            f"recorded it. The daily job records settlements: wait for its next "
                            f"run (or start it: GitHub -> Actions -> daily-collection -> Run "
                            f"workflow), then  git pull --ff-only  and retry.")
            continue
        status = str(state.get("status") or "").lower()
        live_close = _ts(state.get("close_time"))
        if status in OPEN_STATUSES or (live_close is not None and live_close > _window_end()):
            continue            # still trading, or its close moved out of the window
        if listed and _holding(now):
            problems.append(f"{ref} closed at {close:%Y-%m-%d %H:%M} UTC but Kalshi has not "
                            f"settled it yet (status: {status or 'unknown'}). Settlement "
                            f"usually follows within an hour or two; retry then.")
    return problems


def surprise_problems(tasks: List[Dict], resolved: Set[str], have: Set[str], now: datetime,
                      event_markets: Callable = None) -> List[str]:
    """Every settled calibration release must be able to carry its surprise.

    A release's surprise is recorded once every market in it has settled, which can
    trail the markets this study asked about. Published in that gap, the release
    would enter the calibration without a surprise and, with it, the fit could
    silently fall below the registered four releases.
    """
    if not _holding(now):
        return []
    event_markets = event_markets or surprise.fetch_event_markets
    events = set()
    for task in tasks:
        if task.get("kind") != "event" or str(task.get("task_id")) not in resolved:
            continue
        if str(task.get("asked_at", ""))[:10] > prediction.PREDICTION_DATE:
            continue
        close, event = _ts(task.get("resolves_after")), resolution_event(str(task.get("source_ref") or ""))
        if close is not None and close <= _window_end() and surprise.is_release_event(event):
            events.add(event)
    problems = []
    for event in sorted(events - have):
        try:
            markets, _ = event_markets(event)
        except FetchError as exc:
            problems.append(f"could not read {event} from Kalshi ({exc}). Retry in a few minutes.")
            continue
        if not release_surprise.fully_settled(markets):
            problems.append(f"{event} has settled for this study's questions, but not every "
                            f"market in the release has, so its surprise cannot be recorded "
                            f"yet. Retry later today.")
    return problems


def readiness(now: datetime, market: Callable = None, event_markets: Callable = None) -> Dict:
    """Everything --publish refuses on beyond the date and the one-shot rule."""
    problems = git_problems()
    if problems:
        # Nothing below means anything on a copy that is not GitHub's.
        return {"ready": False, "problems": problems, "notes": []}
    tasks = [t for t in JsonlStore(TASKS_PATH).read() if t.get("arm") == PRIMARY_ARM]
    resolved = JsonlStore(RESOLUTIONS_PATH).existing_ids("task_id")
    have = JsonlStore(h1.RELEASE_SURPRISE_PATH).existing_ids("kalshi_event")
    problems += collection_problems(tasks, now)
    problems += settlement_problems(tasks, resolved, now, market)
    problems += surprise_problems(tasks, resolved, have, now, event_markets)
    notes = []
    day = prediction.PREDICTION_DATE
    if now.date().isoformat() > day and not any(
            str(t.get("asked_at", ""))[:10] == day for t in tasks):
        notes.append(f"{day} was never collected; weeks 1-5 end with the day before.")
    return {"ready": not problems, "problems": problems, "notes": notes,
            "origin_main": _git("rev-parse", "origin/main"), "checked_at": now.isoformat()}


def _not_ready(problems: List[str], action: str = "publish") -> str:
    lines = [f"REFUSING: this copy of the record is not ready to {action} from "
             f"(PREREGISTRATION.md 11, deviation 22). Nothing was written or unblinded."]
    lines += [f"  - {p}" for p in problems]
    return "\n".join(lines)


def _shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check(now: datetime | None = None) -> int:
    """--check: the publisher's conditions, read-only."""
    now = now or datetime.now(timezone.utc)
    opens = datetime.fromisoformat(prediction.PUBLISH_NOT_BEFORE)
    print(f"now (UTC)       : {now.isoformat(timespec='minutes')}")
    print(f"window opens    : {opens.isoformat(timespec='minutes')}"
          + ("" if now >= opens else "  <-- not yet"))
    if PREDICTION_FILE.exists():
        print(f"already published: {_shown(PREDICTION_FILE)} exists; it is never revised.")
        return 1
    state = readiness(now)
    for note in state["notes"]:
        print(f"note            : {note}")
    if state["ready"] and now >= opens:
        print("READY: run  ./.venv/bin/python scripts/week5_prediction.py --publish")
        return 0
    if state["ready"]:
        print("The record is current, but the window has not opened; --publish would refuse.")
        return 1
    print("NOT READY:")
    for p in state["problems"]:
        print(f"  - {p}")
    return 1


# --- the four modes ----------------------------------------------------------------

def rehearse() -> int:
    panel, closes, surprises, _ = _inputs(blind=True)
    try:
        p80 = _threshold()
    except SystemExit as exc:
        print(f"(rehearsal) {exc}; using 0.1 so the pipeline can run")
        p80 = 0.1
    cal = prediction.calibrate(panel, closes, surprises, p80)
    print("REHEARSAL -- outcomes permuted, nothing written, numbers meaningless")
    print(json.dumps(_clean({k: v for k, v in cal.items() if k != "events"}), indent=2))
    for event in cal["events"]:
        print("  ", _clean(event))
    return 0


def publish(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    if now < datetime.fromisoformat(prediction.PUBLISH_NOT_BEFORE):
        raise SystemExit(f"REFUSING: the registered prediction is made on or after "
                         f"{prediction.PUBLISH_NOT_BEFORE}; it is {now.isoformat()}.")
    if PREDICTION_FILE.exists():
        raise SystemExit(f"REFUSING: {PREDICTION_FILE.name} exists. The prediction is never revised.")

    p80 = _threshold()
    ready = readiness(now)
    if not ready["ready"]:
        raise SystemExit(_not_ready(ready["problems"]))
    _record_settled_surprises()
    panel, closes, surprises, exclusions = _inputs(blind=False)
    cal = prediction.calibrate(panel, closes, surprises, p80)
    fit = h1.run(blind=False, asked_on_or_before=prediction.PREDICTION_DATE)

    record = {
        "registered_in": "PREREGISTRATION.md 5.3 and 11 (deviations 18 and 22)",
        "made_at_utc": now.isoformat(),
        "code_commit": _git("rev-parse", "HEAD"),
        "data_commit": _git("log", "-1", "--format=%H", "--", "data/"),
        "record_checked_against": {"github_main": ready["origin_main"],
                                   "checked_at_utc": ready["checked_at"],
                                   "notes": ready["notes"]},
        "models_excluded_by_5_6": exclusions.get("models_below_coverage_floor", {}),
        **cal,
    }
    digest = _write(PREDICTION_FILE, record)
    _write(H1_FIT_FILE, fit)
    print(cal.get("statement") or f"NO PREDICTION COULD BE MADE: {cal.get('why_not')}")
    print(f"\nSHA-256 of {_shown(PREDICTION_FILE)}: {digest}")
    steps = ["git add predictions/ && git commit -m 'Week-5 prediction' && git push"]
    if _git("status", "--porcelain", "--", "data/"):
        # Never push data/ from this machine: the daily job appends to the same
        # files, and two writers racing on an append-only file is how a day's
        # commit fails to land. The job records the same surprise itself.
        steps.append("git checkout -- data/   (drops the surprise row this run wrote "
                     "locally; the daily job records the same row itself)")
    steps.append("Zenodo: New version of 10.5281/zenodo.22220263 -> upload both files -> Publish")
    steps.append("OSF project wiki: paste the statement above and the SHA-256")
    print("\nNow, today, in this order:")
    for number, step in enumerate(steps, start=1):
        print(f"  {number}. {step}")
    return 0 if cal.get("made") else 1


def evaluate() -> int:
    if not PREDICTION_FILE.exists():
        raise SystemExit("no published prediction to evaluate")
    made = json.loads(PREDICTION_FILE.read_text(encoding="utf-8"))
    if not made.get("made"):
        raise SystemExit("the published record says no prediction was made")
    stale = git_problems()
    if stale:
        raise SystemExit(_not_ready(stale, action="evaluate"))
    _record_settled_surprises()
    panel, closes, surprises, _ = _inputs(blind=False)
    outcome = prediction.evaluate(panel, closes, surprises, made)
    digest = _write(EVALUATION_FILE, {"prediction_sha256": hashlib.sha256(
        PREDICTION_FILE.read_bytes()).hexdigest(), **outcome})
    print(f"VERDICT: {outcome['verdict']}")
    if outcome["deciding_event"]:
        print(json.dumps(_clean(outcome["deciding_event"]), indent=2))
    print(f"written {_shown(EVALUATION_FILE)} (sha256 {digest})")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--evaluate", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    if args.publish:
        return publish()
    if args.evaluate:
        return evaluate()
    return rehearse()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Rehearse, publish, or evaluate the registered Week-5 prediction (PREREGISTRATION.md 5.3).

Every rule this script applies is fixed in PREREGISTRATION.md 11, deviation 18,
and implemented in `neff/prediction.py`.

  (no flag)    REHEARSAL. Outcomes are permuted and nothing is written. Run it any
               time to watch the whole pipeline work; its numbers are meaningless
               by construction.

  --publish    On or after 2026-10-02 20:00 UTC, once that day's collection has
               run and its settlements are recorded. This is the registered look:
               it unblinds weeks 1-5, fits H1 on them, computes X and Y, writes
               predictions/week5-prediction.json and predictions/week5-h1-fit.json,
               and prints the SHA-256 to post publicly. It refuses to run twice.

  --evaluate   Once a qualifying release has settled, or after the 11 Dec freeze.
               Unblinds the holdout and writes the verdict: HIT, MISS or UNTESTED.

    ./.venv/bin/python scripts/week5_prediction.py
    ./.venv/bin/python scripts/week5_prediction.py --publish
    ./.venv/bin/python scripts/week5_prediction.py --evaluate
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from neff import h1, prediction, surprise  # noqa: E402
from scripts import release_surprise  # noqa: E402
from neff.analysis import _permute_outcomes, apply_registered_exclusions  # noqa: E402
from neff.config import PRIMARY_ARM, TASKS_PATH  # noqa: E402
from neff.panel import load_panel  # noqa: E402
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


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip()


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
    _record_settled_surprises()
    panel, closes, surprises, exclusions = _inputs(blind=False)
    cal = prediction.calibrate(panel, closes, surprises, p80)
    fit = h1.run(blind=False, asked_on_or_before=prediction.PREDICTION_DATE)

    record = {
        "registered_in": "PREREGISTRATION.md 5.3 and 11 (deviation 18)",
        "made_at_utc": now.isoformat(),
        "code_commit": _git("rev-parse", "HEAD"),
        "data_commit": _git("log", "-1", "--format=%H", "--", "data/"),
        "models_excluded_by_5_6": exclusions.get("models_below_coverage_floor", {}),
        **cal,
    }
    digest = _write(PREDICTION_FILE, record)
    _write(H1_FIT_FILE, fit)
    print(cal.get("statement") or f"NO PREDICTION COULD BE MADE: {cal.get('why_not')}")
    print(f"\nSHA-256 of {PREDICTION_FILE.relative_to(ROOT)}: {digest}")
    print("\nNow, today, in this order:")
    print("  1. git add predictions/ && git commit -m 'Week-5 prediction' && git push")
    print("  2. Zenodo: New version of 10.5281/zenodo.22220263 -> upload both files -> Publish")
    print("  3. OSF project wiki: paste the statement above and the SHA-256")
    return 0 if cal.get("made") else 1


def evaluate() -> int:
    if not PREDICTION_FILE.exists():
        raise SystemExit("no published prediction to evaluate")
    made = json.loads(PREDICTION_FILE.read_text(encoding="utf-8"))
    if not made.get("made"):
        raise SystemExit("the published record says no prediction was made")
    _record_settled_surprises()
    panel, closes, surprises, _ = _inputs(blind=False)
    outcome = prediction.evaluate(panel, closes, surprises, made)
    digest = _write(EVALUATION_FILE, {"prediction_sha256": hashlib.sha256(
        PREDICTION_FILE.read_bytes()).hexdigest(), **outcome})
    print(f"VERDICT: {outcome['verdict']}")
    if outcome["deciding_event"]:
        print(json.dumps(_clean(outcome["deciding_event"]), indent=2))
    print(f"written {EVALUATION_FILE.relative_to(ROOT)} (sha256 {digest})")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--evaluate", action="store_true")
    args = parser.parse_args(argv)
    if args.publish:
        return publish()
    if args.evaluate:
        return evaluate()
    return rehearse()


if __name__ == "__main__":
    sys.exit(main())

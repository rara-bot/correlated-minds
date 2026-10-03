"""The Week-5 out-of-sample prediction (PREREGISTRATION.md 5.3), made mechanical.

§5.3 registers the date, the fit and the form: "On 2 Oct 2026 (end of Week 5) we
fit H1 on weeks 1-5, then publish a hashed, timestamped numerical prediction of
the form: 'On the next macro release with |surprise| above the 80th percentile,
headroom will fall below X and rho_bar will exceed Y.' Weeks 6-15 are a genuine
holdout. The prediction is never revised. A miss is reported as a miss."

It does not say what a macro release is, how its surprise is measured, which
task-days make up a release's panel, how X and Y follow from the fit, or what
happens if no qualifying release arrives. Every one of those is fixed in
PREREGISTRATION.md 11, deviation 18, on 2026-09-13 -- nineteen days before the
calibration window closes and while no calibration outcome had been looked at --
and implemented here exactly as written there.

  release        a Kalshi event in `surprise.RELEASE_SERIES`
  surprise       `surprise.event_surprise`: the market's Brier score a day before
  event panel    every primary task-day resolving against the release, after the
                 registered exclusions, estimated with the registered estimator
  calibration    releases closing by the end of 2026-10-02, task-days asked by then
  threshold      REGISTERED_P80: the 80th percentile of surprise over every listed
                 release in the twelve months before collection began
  X, Y           the calibration medians of headroom and rho_bar, made stricter --
                 never looser -- by the event-level fit at the threshold when at
                 least MIN_FIT_EVENTS releases support one
  holdout        releases closing after the calibration window, their panels
                 built from task-days asked from 2026-10-03 only
  verdict        the first holdout release at or above the threshold: HIT if its
                 headroom is below X and its rho_bar above Y, otherwise MISS; no
                 such release by the 11 Dec freeze: UNTESTED
"""

import math
from datetime import datetime
from typing import Dict, List, Optional, Sequence

import numpy as np

from .analysis import resolution_event
from .config import DATA_FREEZE
from .panel import Panel, _rows
from .stats import mean_pairwise_correlation, n_eff
from .surprise import is_release_event

PREDICTION_DATE = "2026-10-02"
PUBLISH_NOT_BEFORE = "2026-10-02T20:00:00+00:00"   # after that day's collection and settlements
CALIBRATION_CLOSES_BY = "2026-10-02T23:59:59+00:00"
HOLDOUT_FIRST_ASK = "2026-10-03"
HOLDOUT_CLOSES_BY = f"{DATA_FREEZE}T23:59:59+00:00"
MIN_EVENT_TASK_DAYS = 5
MIN_FIT_EVENTS = 4

# Registered in deviation 18: the 80th percentile (numpy, linear) of the market
# surprise of all 66 listed releases that closed from 2025-09-01 to 2026-08-31,
# recorded in data/release_surprise.jsonl with role "reference" on 2026-09-13.
# The tests and `scripts/week5_prediction.py` recompute it from those rows and
# refuse to go on if the two ever differ.
REGISTERED_P80: Optional[float] = 0.2425625


def _ts(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def event_close_times(tasks: Sequence[Dict]) -> Dict[str, datetime]:
    """Latest close time among the tasks resolving against each Kalshi event."""
    out: Dict[str, datetime] = {}
    for task in tasks:
        ref = str(task.get("source_ref") or "")
        close = _ts(task.get("resolves_after") or "")
        if not ref or close is None:
            continue
        event = resolution_event(ref)
        if event not in out or close > out[event]:
            out[event] = close
    return out


def event_metrics(panel: Panel, rows: Sequence[int], event: str,
                  close: Optional[datetime], surprise_value: Optional[float]) -> Dict[str, object]:
    """One release's panel, estimated with the registered estimator."""
    sub = _rows(panel, rows)
    record: Dict[str, object] = {
        "event": event,
        "close_time": close.isoformat() if close else None,
        "task_days": sub.n_tasks,
        "ask_days": len({d for d in sub.asked_on if d}),
        "surprise": surprise_value,
        "headroom": math.nan,
        "rho_bar": math.nan,
        "eligible": False,
    }
    if sub.n_tasks < MIN_EVENT_TASK_DAYS:
        record["why_not"] = f"{sub.n_tasks} task-day(s)"
        return record
    rho = mean_pairwise_correlation(sub.errors)
    if not np.isfinite(rho):
        record["why_not"] = "no estimable pair"
        return record
    record.update(rho_bar=float(rho), headroom=float(n_eff(rho, sub.n_models) - 1.0),
                  eligible=True)
    return record


def release_events(panel: Panel, closes: Dict[str, datetime], surprises: Dict[str, float],
                   closes_after: Optional[str], closes_by: str,
                   asked_from: Optional[str] = None,
                   asked_to: Optional[str] = None) -> List[Dict[str, object]]:
    lo, hi = (_ts(closes_after) if closes_after else None), _ts(closes_by)
    rows_by_event: Dict[str, List[int]] = {}
    for i, ref in enumerate(panel.question_ids):
        event = resolution_event(ref)
        day = panel.asked_on[i]
        if not is_release_event(event):
            continue
        if (asked_from and day < asked_from) or (asked_to and day > asked_to):
            continue
        rows_by_event.setdefault(event, []).append(i)
    out = []
    for event, rows in rows_by_event.items():
        close = closes.get(event)
        if close is None or close > hi or (lo is not None and close <= lo):
            continue
        s = surprises.get(event)
        out.append(event_metrics(panel, rows, event, close,
                                 None if s is None or not np.isfinite(s) else float(s)))
    return sorted(out, key=lambda r: r["close_time"] or "")


def _median(values: List[float]) -> float:
    finite = [v for v in values if np.isfinite(v)]
    return float(np.median(finite)) if finite else math.nan


def calibrate(panel: Panel, closes: Dict[str, datetime], surprises: Dict[str, float],
              p80: float) -> Dict[str, object]:
    """X and Y from weeks 1-5, exactly as deviation 18 registers them."""
    events = release_events(panel, closes, surprises, closes_after=None,
                            closes_by=CALIBRATION_CLOSES_BY, asked_to=PREDICTION_DATE)
    eligible = [e for e in events if e["eligible"]]
    out: Dict[str, object] = {"events": events, "eligible": len(eligible), "threshold_p80": p80}
    if not eligible:
        out.update(made=False, why_not="no eligible calibration release")
        return out
    median_h = _median([e["headroom"] for e in eligible])
    median_r = _median([e["rho_bar"] for e in eligible])
    X, Y, fit = median_h, median_r, None
    with_surprise = [e for e in eligible if e["surprise"] is not None]
    if len(with_surprise) >= MIN_FIT_EVENTS:
        s = np.array([e["surprise"] for e in with_surprise])
        if np.ptp(s) > 0:
            h_slope, h_icpt = np.polyfit(s, [e["headroom"] for e in with_surprise], 1)
            r_slope, r_icpt = np.polyfit(s, [e["rho_bar"] for e in with_surprise], 1)
            fit = {"events": len(with_surprise),
                   "headroom_at_p80": float(h_icpt + h_slope * p80),
                   "rho_bar_at_p80": float(r_icpt + r_slope * p80),
                   "headroom_slope": float(h_slope), "rho_bar_slope": float(r_slope)}
            # Stricter, never looser: a fit pointing against H1 cannot make the
            # prediction easier than "below the calibration median".
            X = min(fit["headroom_at_p80"], median_h)
            Y = max(fit["rho_bar_at_p80"], median_r)
    out.update(made=True, median_headroom=median_h, median_rho_bar=median_r, fit=fit,
               X=float(X), Y=float(Y), statement=statement(p80, X, Y))
    return out


def statement(p80: float, X: float, Y: float) -> str:
    return (f"On the first listed macro release to close after {CALIBRATION_CLOSES_BY} "
            f"and before {HOLDOUT_CLOSES_BY} whose market surprise is at or above "
            f"{p80:.7f}, the primary panel's headroom, estimated on its task-days asked "
            f"from {HOLDOUT_FIRST_ASK}, will be below {X:.6f} and its rho_bar above {Y:.6f}.")


def evaluate(panel: Panel, closes: Dict[str, datetime], surprises: Dict[str, float],
             prediction: Dict[str, object]) -> Dict[str, object]:
    """HIT, MISS or UNTESTED -- decided by the first qualifying holdout release."""
    p80, X, Y = (float(prediction[k]) for k in ("threshold_p80", "X", "Y"))
    events = release_events(panel, closes, surprises, closes_after=CALIBRATION_CLOSES_BY,
                            closes_by=HOLDOUT_CLOSES_BY, asked_from=HOLDOUT_FIRST_ASK)
    for event in events:
        if event["eligible"] and event["surprise"] is not None and event["surprise"] >= p80:
            hit = event["headroom"] < X and event["rho_bar"] > Y
            return {"verdict": "HIT" if hit else "MISS", "deciding_event": event,
                    "holdout_events": events}
    return {"verdict": "UNTESTED", "deciding_event": None, "holdout_events": events}

"""H2 -- the shared-prior mechanism. Its confirmatory test: base-rate convergence.

PREREGISTRATION.md 4 registers it: "The panel median forecast moves closer to the
category base rate as ambiguity rises: mean |panel median - base rate| is compared
across terciles of ambiguity ... with a block-bootstrap interval on the
top-minus-bottom difference." FALSIFIED IF the difference "is not negative with an
interval excluding zero". Rationale similarity, demoted to exploratory by the same
section, is not built.

Until 2026-09-14 nothing computed it, and the plan names neither the category nor
where its base rate comes from. PREREGISTRATION.md 11, deviation 20 fixes both,
and every other open choice, before the test has run on anything but shuffled
inputs:

  ambiguity  H1's, row for row: 1 - ladder_distance where the question's own
             Kalshi event is a numeric ladder, undefined elsewhere (deviation 17 (1))
  category   the Kalshi series, the first segment of the ticker (KXCPIYOY, KXU3).
             Section 3.2's three categories each pool unrelated quantities, CPI
             with gas prices, and the base rate of such a pool is nobody's prior
  base rate  the share of the series' markets that settled YES, over its events
             closing in deviation 18's reference window, the twelve months before
             collection began; pinned once per series in
             data/category_base_rates.jsonl by scripts/category_base_rates.py, and
             undefined below MIN_REFERENCE_EVENTS events or MIN_REFERENCE_MARKETS
             settled markets. It reads no outcome of this study
  median     over the models that answered the task-day
  contrast   cut points at the 1/3 and 2/3 quantiles of ambiguity over the
             task-days where the distance is defined, fixed across resamples, as
             for H1 (deviation 17 (4)); every task-day counts once
  claim      negative only if the question-clustered interval and the
             settlement-clustered one both lie below zero; provisional below 30
             questions or 10 settlements

The statistic reads forecasts and pre-study settlements and never a study outcome,
so permuting outcomes would leave it exactly as it is. A blind run shuffles the
ambiguity values among the task-days that have one instead.

One mechanical reading is disclosed rather than designed away. A strike near its
ladder's median is both the most ambiguous kind of question and, on a ladder built
around the expected print, the kind whose honest probability sits nearest a base
rate that itself sits near one half. The registered contrast can therefore come
out negative with no shared prior at work. The same contrast on the panel's
distance from the base rate MINUS the market's own distance, on task-days with a
recorded market price (deviation 15), is reported beside it as an unregistered
sensitivity: did the panel move toward the base rate by more than the market did?
It cannot change the registered verdict.
"""

import math
from pathlib import Path
from typing import Dict, Sequence

import numpy as np

from . import h1
from .analysis import N_BOOT, apply_registered_exclusions, claimed_sign, intervals, resampled
from .config import DATA_DIR, TASKS_PATH
from .panel import Panel, _rows, load_panel
from .store import JsonlStore

BASE_RATES_PATH = DATA_DIR / "category_base_rates.jsonl"
MIN_REFERENCE_EVENTS = 2
MIN_REFERENCE_MARKETS = 10


def category_of(source_ref: str) -> str:
    """The Kalshi series a question belongs to: its ticker's first segment."""
    return str(source_ref or "").split("-", 1)[0]


def reference_base_rate(results_by_event: Dict[str, Sequence[object]]) -> Dict[str, object]:
    """The share of settled markets that settled YES, over the events given.

    Maps each reference-window event to its markets' `result` fields. Only "yes"
    and "no" are settlements; a voided or undetermined market is not counted.
    """
    events = markets = yes = 0
    for results in results_by_event.values():
        settled = [r for r in (str(x or "").lower() for x in results) if r in ("yes", "no")]
        if settled:
            events += 1
            markets += len(settled)
            yes += settled.count("yes")
    out: Dict[str, object] = {"events": events, "markets": markets, "yes": yes, "base_rate": None}
    if events < MIN_REFERENCE_EVENTS or markets < MIN_REFERENCE_MARKETS:
        out["why_not"] = f"{events} event(s) and {markets} settled market(s) in the reference window"
    else:
        out["base_rate"] = yes / markets
    return out


def load_base_rates(path: Path = BASE_RATES_PATH) -> Dict[str, float]:
    """Pinned base rate per series, NaN where the pin records none. First row per series wins."""
    out: Dict[str, float] = {}
    for row in JsonlStore(path).read():
        series = row.get("series")
        if series and str(series) not in out:
            out[str(series)] = h1._num(row.get("base_rate"))
    return out


def ambiguity_column(panel: Panel, snapshot: Dict[str, Dict]) -> np.ndarray:
    """H1's `ambiguity = 1 - ladder_distance`, one value per task-day, NaN where undefined."""
    return np.array([1.0 - h1.ladder_value(panel.state[i], panel.question_ids[i], snapshot)
                     for i in range(panel.n_tasks)], dtype=float)


def tercile_difference(sub: Panel, values: np.ndarray, per_row: np.ndarray,
                       n_boot: int = N_BOOT, seed: int = 0) -> Dict[str, object]:
    """Mean of `per_row` in the top tercile of `values` minus in the bottom, with 5.2's intervals.

    `sub` holds exactly the task-days on which both are defined. The rules are
    H1's tercile rules, applied to a mean rather than to headroom.
    """
    values = np.asarray(values, dtype=float)
    per_row = np.asarray(per_row, dtype=float)
    out: Dict[str, object] = {"task_days": int(sub.n_tasks), "estimable": False}
    if sub.n_tasks < 2 * h1.MIN_TERCILE_TASK_DAYS:
        out["why_not"] = f"{sub.n_tasks} task-day(s) with both defined"
        return out
    low, high = (float(x) for x in np.quantile(values, [1.0 / 3.0, 2.0 / 3.0]))
    out.update(cut_low=low, cut_high=high)
    if not low < high:
        out["why_not"] = f"cut points coincide at {low:.4f}: no usable variation"
        return out
    bottom, top = values <= low, values >= high
    days = np.asarray(sub.asked_on, dtype=object)
    for name, mask in (("bottom", bottom), ("top", top)):
        if mask.sum() < h1.MIN_TERCILE_TASK_DAYS or len(set(days[mask])) < h1.MIN_TERCILE_DAYS:
            out["why_not"] = f"{name} tercile holds {int(mask.sum())} task-day(s)"
            return out

    def difference(idx: np.ndarray) -> float:
        v, d = values[idx], per_row[idx]
        t, b = d[v >= high], d[v <= low]
        return float(t.mean() - b.mean()) if t.size and b.size else math.nan

    out.update(estimable=True, n_bottom=int(bottom.sum()), n_top=int(top.sum()),
               mean_bottom=float(per_row[bottom].mean()), mean_top=float(per_row[top].mean()),
               difference=difference(np.arange(sub.n_tasks)))
    out["intervals"] = intervals(resampled(sub, difference, n_boot, seed))
    out["claimed_sign"] = claimed_sign(out["intervals"])
    return out


def evaluate(panel: Panel, ambiguity: np.ndarray, base_rates: Dict[str, float],
             n_boot: int = N_BOOT, seed: int = 0) -> Dict[str, object]:
    """The registered contrast and its market-referenced sensitivity, on a prepared panel."""
    ambiguity = np.asarray(ambiguity, dtype=float)
    series = [category_of(q) for q in panel.question_ids]
    base = np.array([base_rates.get(s, math.nan) for s in series], dtype=float)
    median = (np.nanmedian(panel.forecasts, axis=1) if panel.n_tasks
              else np.zeros(0))                     # load_panel admits no all-NaN row
    distance = np.abs(median - base)
    on_ladder = ~np.isnan(ambiguity)
    defined = np.nonzero(on_ladder & ~np.isnan(distance))[0]
    asked = {s for s, a in zip(series, on_ladder) if a}
    result: Dict[str, object] = {
        "task_days": panel.n_tasks,
        "task_days_on_a_ladder": int(on_ladder.sum()),
        "task_days_with_a_base_rate": int(defined.size),
        "series_not_pinned": sorted(s for s in asked if s not in base_rates),
        "series_without_a_base_rate": sorted(s for s in asked
                                             if s in base_rates and math.isnan(base_rates[s])),
    }
    sub = _rows(panel, defined)
    registered = tercile_difference(sub, ambiguity[defined], distance[defined], n_boot, seed)
    result["registered"] = registered
    result.update(h1.sample_size(sub))

    excess = distance - np.abs(panel.market_implied - base)
    priced = np.nonzero(on_ladder & ~np.isnan(excess))[0]
    result["sensitivity_panel_minus_market"] = dict(
        tercile_difference(_rows(panel, priced), ambiguity[priced], excess[priced], n_boot, seed),
        unregistered=True)

    claimed = registered.get("claimed_sign")
    if not registered.get("estimable") or claimed is None:
        result["verdict"] = "untested"
    elif claimed == -1:
        result["verdict"] = "supports H2"
    elif claimed == 1:
        result["verdict"] = "falsified: the most ambiguous tercile sits further from the base rate"
    else:
        result["verdict"] = "falsified: the difference is not distinguishable from zero"
    return result


def run(blind: bool = True, seed: int = 0, n_boot: int = N_BOOT, tasks_path: Path = TASKS_PATH,
        ladders_path: Path = h1.LADDERS_PATH, base_rates_path: Path = BASE_RATES_PATH,
        **load_kwargs) -> Dict[str, object]:
    """Load, exclude, (shuffle ambiguity), and test H2 as registered."""
    panel = load_panel(tasks_path=tasks_path, **load_kwargs)
    panel, exclusions = apply_registered_exclusions(panel)
    ambiguity = ambiguity_column(panel, h1.load_ladder_snapshot(ladders_path))
    if blind:
        on_ladder = np.nonzero(~np.isnan(ambiguity))[0]
        ambiguity[on_ladder] = np.random.default_rng(seed).permutation(ambiguity[on_ladder])
    result = evaluate(panel, ambiguity, load_base_rates(base_rates_path), n_boot, seed)
    result.update(blind=blind, models=list(panel.model_keys),
                  models_excluded=exclusions.get("models_below_coverage_floor", {}))
    return result

"""H1 -- conditional collapse. The registered PRIMARY hypothesis, composed.

PREREGISTRATION.md 4 registers two tests and names every variable they use:

  1. a regression of pairwise error products on the seven standardised state
     variables, with task-clustered standard errors, corrected by
     Benjamini-Hochberg at FDR 0.05 across the seven, each coefficient judged
     against the direction registered for it; and
  2. headroom in the top versus the bottom tercile of `vix_level` (the stress
     leg) and of `ambiguity = 1 - ladder_distance` (the ambiguity leg), each with
     block-bootstrap intervals on the headroom scale.

Until 2026-09-13 neither existed in code. What the plan leaves unsaid -- what a
pairwise error product is, what the variables are standardised over, what a
cluster is, what happens to a variable that is undefined on a row or on every
row, how tercile cut points interact with resampling -- is fixed in
PREREGISTRATION.md 11, deviation 17, written while this driver had only ever run
on permuted outcomes. Each choice is marked where it is made.

BLIND BY DEFAULT, like `analysis.run`: outcomes are permuted unless `blind=False`
is passed. The registered occasions for an unblinded run are the Week-5 fit on
weeks 1-5 (PREREGISTRATION.md 5.3, deviation 18) and the final analysis after the
11 Dec freeze. Nothing else.
"""

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy import stats as scipy_stats

from . import state as state_mod
from .analysis import (
    ALPHA,
    BLOCK_DAYS,
    N_BOOT,
    _permute_outcomes,
    apply_registered_exclusions,
    resolution_event,
)
from .config import DATA_DIR, PRIMARY_ARM, STATE_VARIABLES, TASKS_PATH
from .panel import Panel, _rows, load_panel
from .stats import _moving_block_indices, benjamini_hochberg, n_eff_from_errors
from .store import JsonlStore

# PREREGISTRATION.md 4, the table of registered directions. +1: H1 predicts a
# positive coefficient on the standardised variable; -1: negative.
REGISTERED_DIRECTION: Dict[str, int] = {
    "ladder_distance": -1,
    "vix_level": +1,
    "realized_vol_20d": +1,
    "expectation_dispersion": -1,
    "abs_surprise": +1,
    "days_out": +1,
    "novelty_score": +1,
}
FDR = 0.05

LADDERS_PATH = DATA_DIR / "kalshi_ladders.jsonl"
RELEASE_SURPRISE_PATH = DATA_DIR / "release_surprise.jsonl"

# Deviation 17. `abs_surprise` is defined only on task-days that resolve against
# a listed macro release, so it cannot share a complete-case sample with the
# other six without deleting most of the regression. It is estimated in its own
# regression -- the six plus itself, on its own complete cases -- when that sample
# can support one, and is otherwise untested with p = 1.
ALWAYS_JOINT = [v for v in STATE_VARIABLES if v != "abs_surprise"]
SEPARATE_MIN_TASK_DAYS = 30
SEPARATE_MIN_CLUSTERS = 5

# Below these a regression or a tercile is not estimable and is reported so.
MIN_REGRESSION_TASK_DAYS = 10
MIN_REGRESSION_CLUSTERS = 5
MIN_TERCILE_TASK_DAYS = 10
MIN_TERCILE_DAYS = 2

HORIZON_BANDS = ((3, 14), (15, 45), (46, 90), (91, 10_000))   # 5.4(b)

# Deviation 17. Cluster-robust standard errors are optimistic with few clusters:
# run blind on the 20 resolved task-days of 2026-09-13 (14 questions, 5
# settlements), this driver called three variables significant on PERMUTED
# outcomes. Below these counts every verdict is labelled provisional, and the
# claim reported is the weaker of the question- and settlement-clustered fits.
PROVISIONAL_BELOW_QUESTIONS = 30
PROVISIONAL_BELOW_SETTLEMENTS = 10


def _num(value) -> float:
    if value is None or isinstance(value, bool):
        return math.nan
    try:
        out = float(value)
    except (TypeError, ValueError):
        return math.nan
    return out if math.isfinite(out) else math.nan


# --- inputs ----------------------------------------------------------------------

def load_ladder_snapshot(path: Path = LADDERS_PATH) -> Dict[str, Dict]:
    """`scripts/snapshot_kalshi_ladders.py` output, keyed by market ticker."""
    return {str(r.get("ticker")): r for r in JsonlStore(path).read() if r.get("ticker")}


def load_release_surprises(path: Path = RELEASE_SURPRISE_PATH) -> Dict[str, float]:
    """Market surprise per listed macro release, keyed by Kalshi event (deviation 18).

    First row per event wins, as for resolutions: a later row never rewrites one.
    """
    out: Dict[str, float] = {}
    for row in JsonlStore(path).read():
        event = row.get("kalshi_event")
        if event and event not in out:
            out[str(event)] = _num(row.get("surprise"))
    return out


def ladder_value(state: Dict, source_ref: str, snapshot: Dict[str, Dict],
                 per_event: bool = False) -> float:
    """`ladder_distance` where the question sits on a numeric strike ladder, else NaN.

    Deviation 17. The stored value records 0.0 both for a real ladder's median
    strike and for an event with no ladder at all, so it is admitted only where
    the question's own Kalshi event has at least three numeric rungs and the
    question is one of them. Rows from 2026-09-14 say so themselves
    (`event_ladder_distance` is None exactly when it is not); earlier rows are
    judged from the reconstructed snapshot. A row that can be judged neither way
    is NaN -- undefined, never assumed.

    `per_event=True` is the registered SENSITIVITY: distance from the median of
    the question's own event rather than of the pooled series.
    """
    state = state or {}
    if "event_ladder_size" in state:
        event_distance = state.get("event_ladder_distance")
        if event_distance is None:
            return math.nan
        return _num(event_distance) if per_event else _num(state.get("ladder_distance"))
    row = snapshot.get(str(source_ref))
    if not row or not row.get("ladder_defined"):
        return math.nan
    if per_event:
        rungs = sorted(float(x) for x in row.get("event_numeric_rungs") or [])
        span = rungs[-1] - rungs[0] if len(rungs) >= 3 else 0.0
        strike = _num(row.get("strike"))
        if span <= 0 or math.isnan(strike):
            return math.nan
        return abs(strike - float(np.median(rungs))) / span
    return _num(state.get("ladder_distance"))


def state_columns(panel: Panel, novelty: Dict[str, float], snapshot: Dict[str, Dict],
                  surprises: Dict[str, float], per_event_ladder: bool = False
                  ) -> Dict[str, np.ndarray]:
    """The seven registered state variables, one value per task-day. NaN = undefined."""
    n = panel.n_tasks
    cols = {v: np.full(n, np.nan) for v in STATE_VARIABLES}
    for i in range(n):
        st = panel.state[i] or {}
        ref = panel.question_ids[i]
        cols["ladder_distance"][i] = ladder_value(st, ref, snapshot, per_event_ladder)
        cols["vix_level"][i] = _num(st.get("vix_level"))
        cols["realized_vol_20d"][i] = _num(st.get("realized_vol_20d"))
        cols["days_out"][i] = _num(st.get("days_out"))
        cols["abs_surprise"][i] = surprises.get(resolution_event(ref), math.nan)
        cols["novelty_score"][i] = _num(novelty.get(panel.task_ids[i]))
    if n:
        cols["expectation_dispersion"] = state_mod.expectation_dispersion(panel.forecasts)
    return cols


# --- the regression ------------------------------------------------------------------

def pair_products(errors: np.ndarray):
    """(y, row): every pairwise error product, and the task-day each came from.

    Deviation 17: for task-day t and models i < j that both answered it,
    y = e_ti * e_tj. Raw products, not centred ones, so a bias the pair shares
    counts as shared error -- the uncentred reading §4.2 makes co-primary.
    """
    arr = np.asarray(errors, dtype=float)
    ys: List[np.ndarray] = []
    rows: List[np.ndarray] = []
    for i in range(arr.shape[1]):
        for j in range(i + 1, arr.shape[1]):
            idx = np.nonzero(~np.isnan(arr[:, i]) & ~np.isnan(arr[:, j]))[0]
            ys.append(arr[idx, i] * arr[idx, j])
            rows.append(idx)
    if not ys:
        return np.zeros(0), np.zeros(0, dtype=int)
    return np.concatenate(ys), np.concatenate(rows)


def cluster_ols(X: np.ndarray, y: np.ndarray, clusters: Sequence) -> Dict[str, np.ndarray]:
    """OLS with CR1 cluster-robust standard errors and t(G - 1) p-values.

    CR1 is the small-sample-corrected sandwich, G/(G-1) * (N-1)/(N-K). With few
    clusters it is still optimistic, which is why the settlement-clustered fit
    is reported beside it (deviation 17) and why §3.1 refuses this estimator for
    H6, where the clusters number one.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, k = X.shape
    _, inverse = np.unique(np.asarray(clusters, dtype=object).astype(str), return_inverse=True)
    groups = int(inverse.max()) + 1 if n else 0
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta
    scores = np.zeros((groups, k))
    np.add.at(scores, inverse, X * resid[:, None])
    meat = scores.T @ scores
    scale = (groups / (groups - 1)) * ((n - 1) / (n - k)) if groups > 1 and n > k else math.nan
    cov = scale * (xtx_inv @ meat @ xtx_inv)
    se = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        t = beta / se
    df = max(groups - 1, 1)
    p = 2.0 * scipy_stats.t.sf(np.abs(t), df)
    return {"beta": beta, "se": se, "t": t, "p": p, "df": df, "n": n, "clusters": groups}


def regression(panel: Panel, columns: Dict[str, np.ndarray], variables: Sequence[str],
               clusters: Sequence) -> Dict[str, object]:
    """Pairwise error products on standardised state variables, complete cases.

    Standardised over the task-days in the complete-case sample, each task-day
    counted once however many pairs it contributes (deviation 17). A variable
    with no variation in that sample cannot be estimated and is reported as such.
    """
    mask = state_mod.complete_cases({v: columns[v] for v in variables})
    keep = np.nonzero(mask)[0]
    out: Dict[str, object] = {
        "variables": list(variables),
        "task_days": int(keep.size),
        "coverage": float(keep.size / panel.n_tasks) if panel.n_tasks else 0.0,
        "estimable": False,
        "coefficients": {},
    }
    if keep.size < MIN_REGRESSION_TASK_DAYS:
        out["why_not"] = f"{keep.size} complete task-day(s)"
        return out

    usable, z = [], []
    for v in variables:
        values = columns[v][keep]
        sd = float(np.std(values, ddof=1))
        if not np.isfinite(sd) or sd == 0.0:
            out["coefficients"][v] = {"estimable": False, "why_not": "no variation"}
            continue
        usable.append(v)
        z.append((values - float(np.mean(values))) / sd)
    if not usable:
        out["why_not"] = "no variable varies in the sample"
        return out

    sub = _rows(panel, keep)
    y, row = pair_products(sub.errors)
    cl = np.asarray(clusters, dtype=object)[keep][row]
    if len(set(cl.tolist())) < MIN_REGRESSION_CLUSTERS:
        out["why_not"] = f"{len(set(cl.tolist()))} cluster(s)"
        return out
    X = np.column_stack([np.ones(y.size)] + [zv[row] for zv in z])
    fit = cluster_ols(X, y, cl)
    out.update(estimable=True, pair_rows=int(y.size), clusters=fit["clusters"], df=fit["df"])
    for k, v in enumerate(usable, start=1):
        out["coefficients"][v] = {
            "estimable": True,
            "beta": float(fit["beta"][k]),
            "se": float(fit["se"][k]),
            "t": float(fit["t"][k]),
            "p": float(fit["p"][k]),
        }
    return out


def judge(joint: Dict, separate: Optional[Dict]) -> Dict[str, object]:
    """Benjamini-Hochberg across the SEVEN, each against its registered direction.

    A variable that could not be estimated enters with p = 1: it keeps its place
    in the denominator and cannot be rejected, because dropping it would make the
    correction more lenient -- the one direction a missing variable must never
    push (deviation 8).
    """
    rows = []
    for v in STATE_VARIABLES:
        source = separate if (v == "abs_surprise") else joint
        coef = (source or {}).get("coefficients", {}).get(v, {}) if source else {}
        if not coef.get("estimable"):
            rows.append((v, 1.0, math.nan, False))
        else:
            rows.append((v, coef["p"], coef["beta"], True))
    p = [r[1] if np.isfinite(r[1]) else 1.0 for r in rows]
    reject = benjamini_hochberg(p, alpha=FDR)
    verdicts = {}
    for (v, pv, beta, estimable), rej in zip(rows, reject):
        if not estimable:
            verdict = "untested"
        elif not rej:
            verdict = "not significant"
        elif np.sign(beta) == REGISTERED_DIRECTION[v]:
            verdict = "supports H1"
        else:
            verdict = "against H1"
        verdicts[v] = {"p": pv, "beta": beta, "bh_reject": bool(rej), "verdict": verdict,
                       "registered_direction": REGISTERED_DIRECTION[v]}
    return verdicts


# --- the tercile contrasts --------------------------------------------------------------

def _headroom(errors: np.ndarray) -> float:
    if errors.shape[0] < 2 or errors.shape[1] < 2:
        return math.nan
    return float(n_eff_from_errors(errors) - 1.0)


def tercile_contrast(panel: Panel, values: np.ndarray, n_boot: int = N_BOOT,
                     seed: int = 0) -> Dict[str, object]:
    """headroom(top tercile) - headroom(bottom tercile), with the registered intervals.

    Deviation 17: cut points are the 1/3 and 2/3 quantiles of the variable over
    the task-days where it is defined; bottom is at or below the first, top at or
    above the second; the cut points are fixed from the full sample and NOT
    recomputed inside a resample. Whole task-days are resampled -- blocks of five
    days (5.2, interval 1), and whole questions (5.2, interval 2, which governs
    where the two disagree) -- and each resample is split with the fixed cuts.
    If the two cuts coincide there is no usable variation and the contrast is
    reported untested (§10 limitation 5), not estimated.
    """
    values = np.asarray(values, dtype=float)
    defined = np.nonzero(~np.isnan(values))[0]
    out: Dict[str, object] = {"task_days_defined": int(defined.size), "estimable": False}
    if defined.size < 2 * MIN_TERCILE_TASK_DAYS:
        out["why_not"] = f"{defined.size} task-day(s) with the variable defined"
        return out
    sub = _rows(panel, defined)
    v = values[defined]
    low, high = (float(x) for x in np.quantile(v, [1.0 / 3.0, 2.0 / 3.0]))
    out.update(cut_low=low, cut_high=high)
    if not low < high:
        out["why_not"] = f"cut points coincide at {low:.4f}: no usable variation"
        return out
    bottom, top = v <= low, v >= high
    days = np.asarray(sub.asked_on, dtype=object)
    for name, mask in (("bottom", bottom), ("top", top)):
        if mask.sum() < MIN_TERCILE_TASK_DAYS or len(set(days[mask])) < MIN_TERCILE_DAYS:
            out["why_not"] = f"{name} tercile holds {int(mask.sum())} task-day(s)"
            return out

    def difference(idx: np.ndarray) -> float:
        vv = v[idx]
        err = sub.errors[idx]
        return _headroom(err[vv >= high]) - _headroom(err[vv <= low])

    everything = np.arange(sub.n_tasks)
    out.update(
        estimable=True,
        n_bottom=int(bottom.sum()), n_top=int(top.sum()),
        headroom_bottom=_headroom(sub.errors[bottom]),
        headroom_top=_headroom(sub.errors[top]),
        difference=difference(everything),
    )
    rng = np.random.default_rng(seed)
    for label, groups, block in (
        ("day_blocked", sub.asked_on, BLOCK_DAYS),
        ("event_clustered_registered", sub.question_ids, 1),
        ("event_clustered_settlement", [resolution_event(q) for q in sub.question_ids], 1),
    ):
        draws = np.array([difference(_moving_block_indices(sub.n_tasks, block, rng, groups))
                          for _ in range(n_boot)])
        finite = draws[np.isfinite(draws)]
        lo, hi = ((float(np.percentile(finite, 100 * ALPHA / 2)),
                   float(np.percentile(finite, 100 * (1 - ALPHA / 2))))
                  if finite.size else (math.nan, math.nan))
        out[label] = {"lo": lo, "hi": hi, "undefined_draws": int(n_boot - finite.size)}
    governing = out["event_clustered_registered"]
    out["lower_headroom_in_top_tercile"] = bool(np.isfinite(governing["hi"]) and governing["hi"] < 0)
    return out


# --- the driver ---------------------------------------------------------------------

def run(blind: bool = True, seed: int = 0, n_boot: int = N_BOOT,
        asked_on_or_before: Optional[str] = None, tasks_path: Path = TASKS_PATH,
        ladders_path: Path = LADDERS_PATH, surprise_path: Path = RELEASE_SURPRISE_PATH,
        **load_kwargs) -> Dict[str, object]:
    """Load, exclude, (permute), and test H1 exactly as registered.

    `asked_on_or_before` restricts the panel to the task-days asked on or before a
    date -- the Week-5 fit uses weeks 1-5 only (deviation 18).
    """
    panel = load_panel(tasks_path=tasks_path, **load_kwargs)
    panel, exclusions = apply_registered_exclusions(panel)
    if asked_on_or_before:
        panel = _rows(panel, [i for i, d in enumerate(panel.asked_on)
                              if d and d <= asked_on_or_before])
    if blind and panel.n_tasks:
        panel = _permute_outcomes(panel, seed)

    tasks = [t for t in JsonlStore(tasks_path).read() if t.get("arm") == PRIMARY_ARM]
    novelty = state_mod.novelty_scores(tasks)
    snapshot = load_ladder_snapshot(ladders_path)
    surprises = load_release_surprises(surprise_path)
    result: Dict[str, object] = {
        "blind": blind,
        "task_days": panel.n_tasks,
        "models": list(panel.model_keys),
        "models_excluded": exclusions.get("models_below_coverage_floor", {}),
        "asked_on_or_before": asked_on_or_before,
    }
    if panel.n_tasks == 0:
        result["why_not"] = "no resolved task-days"
        return result

    def fit(per_event_ladder: bool, clusters: Sequence) -> Dict[str, object]:
        cols = state_columns(panel, novelty, snapshot, surprises, per_event_ladder)
        joint = regression(panel, cols, ALWAYS_JOINT, clusters)
        surprise_rows = int(state_mod.complete_cases(
            {v: cols[v] for v in ALWAYS_JOINT + ["abs_surprise"]}).sum())
        separate = None
        if surprise_rows >= SEPARATE_MIN_TASK_DAYS:
            separate = regression(panel, cols, ALWAYS_JOINT + ["abs_surprise"], clusters)
            if separate.get("clusters", 0) and separate["clusters"] < SEPARATE_MIN_CLUSTERS:
                separate = None
        coverage = {v: state_mod.coverage(cols[v]) for v in STATE_VARIABLES}
        return {"joint": joint, "abs_surprise_regression": separate,
                "abs_surprise_task_days": surprise_rows, "coverage": coverage,
                "verdicts": judge(joint, separate), "columns": cols}

    questions = list(panel.question_ids)
    settlements = [resolution_event(q) for q in questions]
    primary = fit(False, questions)
    columns = primary.pop("columns")
    result["regression"] = primary
    result["regression_settlement_clustered"] = {
        k: v for k, v in fit(False, settlements).items() if k != "columns"}
    result["regression_per_event_ladder"] = {
        k: v for k, v in fit(True, questions).items() if k != "columns"}

    ambiguity = 1.0 - columns["ladder_distance"]
    result["terciles"] = {
        "stress_vix_level": tercile_contrast(panel, columns["vix_level"], n_boot, seed),
        "ambiguity": tercile_contrast(panel, ambiguity, n_boot, seed),
    }
    days_out = columns["days_out"]
    result["terciles_by_horizon_band"] = {}
    for lo, hi in HORIZON_BANDS:
        rows = [i for i in range(panel.n_tasks) if lo <= days_out[i] <= hi]
        if not rows:
            continue
        band = _rows(panel, rows)
        result["terciles_by_horizon_band"][f"{lo}-{hi}"] = {
            "ambiguity": tercile_contrast(band, ambiguity[rows], n_boot, seed),
            "stress_vix_level": tercile_contrast(band, columns["vix_level"][rows], n_boot, seed),
        }

    verdicts = primary["verdicts"]
    settled = result["regression_settlement_clustered"]["verdicts"]
    contrasts = [c for c in result["terciles"].values() if c.get("estimable")]
    contrast_support = [name for name, c in result["terciles"].items()
                        if c.get("lower_headroom_in_top_tercile")]

    def weaker(a: str, b: str) -> str:
        if a == b:
            return a
        return "untested" if "untested" in (a, b) else "not significant"

    claims = {v: weaker(verdicts[v]["verdict"], settled[v]["verdict"]) for v in STATE_VARIABLES}

    def summary(by_variable: Dict[str, str]) -> Dict[str, object]:
        supports = [v for v, x in by_variable.items() if x == "supports H1"]
        return {
            "variables_supporting": supports,
            "variables_against": [v for v, x in by_variable.items() if x == "against H1"],
            "tercile_contrasts_supporting": contrast_support,
            # PREREGISTRATION.md 4, FALSIFIED IF: no BH-surviving coefficient in
            # the registered direction AND neither tercile contrast shows lower
            # headroom in its top tercile with an interval excluding zero.
            "falsified": (not supports) and not any(
                c.get("lower_headroom_in_top_tercile") for c in contrasts),
        }

    n_questions, n_settlements = len(set(questions)), len(set(settlements))
    result["h1"] = {
        # As registered: question-clustered coefficients.
        "registered": summary({v: r["verdict"] for v, r in verdicts.items()}),
        # What may be claimed: the weaker of the two clusterings (deviation 17).
        "claim": summary(claims),
        "stress_leg_untested": not result["terciles"]["stress_vix_level"].get("estimable"),
        "questions": n_questions,
        "settlements": n_settlements,
        "provisional": (n_questions < PROVISIONAL_BELOW_QUESTIONS
                        or n_settlements < PROVISIONAL_BELOW_SETTLEMENTS),
    }
    return result

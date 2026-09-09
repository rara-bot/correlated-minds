"""Compose the registered analysis: load -> exclude -> estimate -> intervals.

Everything this module needs already existed. `stats.py` implements every
registered estimator and `panel.py` implements every registered exclusion --
but nothing called them together, so on 11 Dec the study would have been
assembling its own headline number for the first time, under time pressure,
against data it could no longer change. This is the driver, written while
collection is still running and there is still time for what it finds to
matter.

IT IS BLIND BY DEFAULT. `run()` permutes outcomes unless `blind=False` is
passed explicitly. A permuted run breaks the forecast-to-outcome link while
keeping every shape that can break the pipeline -- real missingness, real
ragged days, real event clustering, real panel dimensions -- so it exercises
the whole path and reveals nothing about the effect. The registered plan fixes
every analytic choice in advance, so there is nothing legitimate to gain by
looking early, and a pipeline that has only ever been run on the real numbers
is one whose bugs were found by their effect on the answer.
"""

from typing import Dict, List, Optional, Sequence

import numpy as np

from .panel import (
    Panel,
    apply_settled_question_exclusion,
    apply_stale_source_exclusion,
    load_panel,
)
from .stats import block_bootstrap_ci, mean_pairwise_correlation, n_eff_from_errors

BLOCK_DAYS = 5        # PREREGISTRATION.md 5.2
N_BOOT = 2000         # PREREGISTRATION.md 5.2
ALPHA = 0.05          # PREREGISTRATION.md 5.2


def resolution_event(source_ref: str) -> str:
    """The settlement that decides a question, which is coarser than the question.

    A Kalshi ticker is SERIES-EXPIRY-STRIKE. Every strike on one ladder settles
    against ONE print: the five KXAAAGASWNJ-26SEP07 rungs at 4.15 through 4.19
    all resolved to 1.0 on 2026-09-07 from a single AAA gas figure. They are one
    surprise observed five times, not five observations.

    EDGAR refs (`edgar:CIK:PERIOD`) carry no strike -- one company's next filing
    is already one event -- so they are returned unchanged.
    """
    if ":" in source_ref:
        return source_ref
    parts = source_ref.split("-")
    return "-".join(parts[:2]) if len(parts) > 2 else source_ref


def apply_registered_exclusions(panel: Panel) -> Panel:
    """Every exclusion that governs the primary estimate, in one place.

    Kept together deliberately. Both were previously reachable only from tests,
    and an analysis that forgets one silently readmits exactly what it excluded.
    """
    panel = apply_stale_source_exclusion(panel)      # 11, deviation 3
    panel = apply_settled_question_exclusion(panel)  # 3.3
    return panel


def _permute_outcomes(panel: Panel, seed: int) -> Panel:
    """Break the forecast-to-outcome link, keep every shape.

    Errors are recomputed from the shuffled outcomes rather than shuffled
    directly: shuffling the error matrix would carry each row's missingness
    pattern with it and could not produce the error structure the real pipeline
    sees. This keeps NaN exactly where the panel actually failed to answer.
    """
    rng = np.random.default_rng(seed)
    outcomes = np.array(panel.outcomes, dtype=float)
    rng.shuffle(outcomes)
    return Panel(
        forecasts=panel.forecasts,
        outcomes=outcomes,
        errors=panel.forecasts - outcomes[:, None],
        task_ids=list(panel.task_ids),
        model_keys=list(panel.model_keys),
        market_implied=panel.market_implied,
        state=list(panel.state),
        question_ids=list(panel.question_ids),
        asked_on=list(panel.asked_on),
    )


def clamp_binds(rho_bar: float, n_models: int, tol: float = 1e-6) -> bool:
    """Is rho_bar sitting on the floor where N_eff stops meaning anything?

    `stats.n_eff` clamps rho_bar at -1/(M-1), the point below which an
    equicorrelation matrix stops being positive semi-definite. The clamp is
    correct and prevents a division by zero -- but what it returns instead is
    not small, it is astronomical: at M = 9 the blind rehearsal produced an
    N_eff upper bound of 1.1e12 from a panel of five rows.

    A finite nonsense number is more dangerous than an exception, because it
    propagates into a percentile interval and prints. So the driver asks the
    question explicitly rather than letting the value speak for itself.
    """
    if not np.isfinite(rho_bar) or n_models < 2:
        return False
    return rho_bar <= (-1.0 / (n_models - 1)) + tol


def _interval(
    errors: np.ndarray, groups: Sequence, block_size: int, n_boot: int = N_BOOT
) -> Dict[str, float]:
    point, lo, hi = block_bootstrap_ci(
        errors,
        statistic="n_eff",
        block_size=block_size,
        n_boot=n_boot,
        alpha=ALPHA,
        groups=groups,
    )
    # Headroom is N_eff - 1 (PREREGISTRATION.md 2). A shift is monotone, so the
    # percentile interval transforms directly rather than needing its own run.
    return {
        "n_eff": point,
        "n_eff_lo": lo,
        "n_eff_hi": hi,
        "headroom": point - 1.0,
        "headroom_lo": lo - 1.0,
        "headroom_hi": hi - 1.0,
    }


def estimate(panel: Panel, n_boot: int = N_BOOT) -> Dict[str, object]:
    """The registered primary estimate, with every interval 5.2 requires.

    `n_boot` exists so tests can exercise the composition cheaply. It defaults
    to the registered 2000 and production never passes it; the suite gates
    collection, so a full-resample test run would cost every day 60+ seconds of
    the workflow's budget to re-derive a number no test asserts.
    """
    errors = panel.errors
    out: Dict[str, object] = {
        "n_tasks": panel.n_tasks,
        "n_models": panel.n_models,
        "coverage": panel.coverage(),
        "distinct_questions": len(set(panel.question_ids)),
        "distinct_events": len(set(resolution_event(q) for q in panel.question_ids)),
        "rho_bar": mean_pairwise_correlation(errors),
        "point_n_eff": n_eff_from_errors(errors),
    }
    if panel.n_tasks == 0:
        return out

    # 5.2, interval 1 of 2: moving blocks of five TASK-DAYS. Optimistic.
    out["day_blocked"] = _interval(errors, panel.asked_on, BLOCK_DAYS, n_boot)

    # 5.2, interval 2 of 2: whole clusters resampled, block_size=1. Registered
    # AS WRITTEN, on source_ref. This is the interval 5.2 says governs the claim
    # where the two disagree, so it is computed exactly as registered.
    out["event_clustered_registered"] = _interval(errors, panel.question_ids, 1, n_boot)

    # SENSITIVITY, NOT REGISTERED. 11, deviation 5.
    #
    # 5.2 justifies the clustered interval with the CPI ladder -- "every strike
    # on a CPI ladder settles against a single print and therefore shares a
    # single surprise" -- and then operationalises it as `source_ref`. Those are
    # not the same grouping: source_ref CONTAINS the strike, so the ladder it
    # names as the motivating case is split back into one cluster per rung.
    # Measured on the 241 tasks collected to 2026-09-08: 80 source_refs against
    # 40 actual settlements. The interval registered as the conservative bound
    # therefore treats about twice as many clusters as independent as there are,
    # which is the precise error it exists to avoid.
    #
    # The registered interval is not replaced -- 9 gives up the right to revise
    # it and it still governs. This is reported alongside, always labelled.
    events = [resolution_event(q) for q in panel.question_ids]
    out["event_clustered_settlement"] = _interval(errors, events, 1, n_boot)

    # Surfaced, never silently absorbed. If the clamp binds, N_eff is not an
    # effective panel size any more and no interval built on it is reportable;
    # 5.5 already refuses the mirror-image blowup at high rho as "not a
    # reportable headline", and this is the same refusal at the other end.
    out["clamp_binds"] = clamp_binds(float(out["rho_bar"]), panel.n_models)
    out["n_eff_exceeds_m"] = bool(float(out["point_n_eff"]) > panel.n_models + 1e-9)
    warnings_out: List[str] = []
    if out["clamp_binds"]:
        warnings_out.append(
            f"rho_bar {out['rho_bar']:.6f} is at the -1/(M-1) floor for M="
            f"{panel.n_models}: N_eff is unbounded here and must not be reported."
        )
    if out["n_eff_exceeds_m"]:
        warnings_out.append(
            f"N_eff {float(out['point_n_eff']):.3f} exceeds M={panel.n_models}. "
            "That is arithmetically possible when rho_bar < 0, but 'more "
            "independent opinions than forecasters' is not a claim; it means "
            "rho_bar is noise-dominated at this sample size."
        )
    if len(set(panel.asked_on)) < BLOCK_DAYS:
        warnings_out.append(
            f"only {len(set(panel.asked_on))} distinct day(s): the day-blocked "
            f"bootstrap resamples the same day and its interval is degenerate."
        )
    if out["distinct_events"] < 2:
        warnings_out.append(
            f"only {out['distinct_events']} distinct settlement(s): every row "
            "traces to one surprise, so the panel has ~1 independent observation."
        )
    out["warnings"] = warnings_out
    return out


def run(
    blind: bool = True,
    seed: int = 0,
    model_keys: Optional[List[str]] = None,
    n_boot: int = N_BOOT,
    **load_kwargs,
) -> Dict[str, object]:
    """Load the panel, apply the registered exclusions, estimate.

    `blind=True` (the default) permutes outcomes. Ask for `blind=False` only
    when the freeze has passed and the real estimate is the thing wanted.
    """
    panel = load_panel(model_keys=model_keys, **load_kwargs)
    before = panel.n_tasks
    panel = apply_registered_exclusions(panel)
    if blind:
        panel = _permute_outcomes(panel, seed)

    result = estimate(panel, n_boot=n_boot)
    result["blind"] = blind
    result["tasks_before_exclusions"] = before
    result["tasks_excluded"] = before - panel.n_tasks
    return result

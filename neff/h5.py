"""H5 -- task-format invariance. Registered secondary.

PREREGISTRATION.md 4 registers headroom(Type A) ~= headroom(Type B), tested by
"headroom estimated separately by task type, block-bootstrap interval on the
difference", reported regardless of direction, with no falsification clause.
`report.strata` has reported the two headrooms since deviation 17; nothing
computed the interval on their difference. Fixed in deviation 20:

  types       Type B is a filing task (`report.kind_of`), Type A every other
  difference  Type A minus Type B, each at the surviving panel's M, from one
              resample of the whole panel, so the dependence the two types share
              through the calendar day is inside the interval; 5.2's two intervals
              and deviation 5's
  scales      the Pearson headroom 4.1 makes primary and, beside it, the MSE
              headroom 4.2 makes co-primary
  reading     none. The result says which intervals hold zero and draws no
              conclusion, as the registration asks
"""

import math
from pathlib import Path
from typing import Dict, List

import numpy as np

from . import h1
from .analysis import N_BOOT, _permute_outcomes, apply_registered_exclusions, intervals, resampled, sign_of
from .config import TASKS_PATH
from .panel import Panel, load_panel
from .report import kind_of
from .stats import mean_pairwise_correlation, n_eff, n_eff_mse

SCALES = ("headroom_pearson", "headroom_mse")


def headrooms(errors: np.ndarray, m: int) -> List[float]:
    """[Pearson headroom, MSE headroom] of one set of task-days, NaN where undefined."""
    if errors.shape[0] < 3:
        return [math.nan, math.nan]
    rho = mean_pairwise_correlation(errors)
    mse = n_eff_mse(errors)
    return [n_eff(rho, m) - 1.0 if np.isfinite(rho) else math.nan,
            mse - 1.0 if np.isfinite(mse) else math.nan]


def evaluate(panel: Panel, n_boot: int = N_BOOT, seed: int = 0) -> Dict[str, object]:
    """Type A against Type B on a prepared panel."""
    filing = np.array([kind_of(s) == "filing" for s in panel.state], dtype=bool)
    m = panel.n_models
    out: Dict[str, object] = {"task_days_type_a": int((~filing).sum()),
                              "task_days_type_b": int(filing.sum()), "m": m}
    out.update(h1.sample_size(panel))
    if m < 2:
        out["why_not"] = f"M = {m}"
        return out
    type_a, type_b = headrooms(panel.errors[~filing], m), headrooms(panel.errors[filing], m)
    out["type_a"] = dict(zip(SCALES, type_a))
    out["type_b"] = dict(zip(SCALES, type_b))
    out["difference_a_minus_b"] = dict(zip(SCALES, np.subtract(type_a, type_b).tolist()))
    draws = resampled(panel, lambda idx: np.subtract(headrooms(panel.errors[idx][~filing[idx]], m),
                                                     headrooms(panel.errors[idx][filing[idx]], m)),
                      n_boot, seed)
    out["intervals"] = {scale: intervals(draws, k) for k, scale in enumerate(SCALES)}
    out["interval_holds_zero"] = {
        scale: {label: (None if sign_of(iv) is None else sign_of(iv) == 0)
                for label, iv in out["intervals"][scale].items()}
        for scale in SCALES}
    return out


def run(blind: bool = True, seed: int = 0, n_boot: int = N_BOOT, tasks_path: Path = TASKS_PATH,
        **load_kwargs) -> Dict[str, object]:
    """Load, exclude, (permute), and estimate H5 as registered."""
    panel = load_panel(tasks_path=tasks_path, **load_kwargs)
    panel, exclusions = apply_registered_exclusions(panel)
    if blind and panel.n_tasks:
        panel = _permute_outcomes(panel, seed)
    result = evaluate(panel, n_boot, seed)
    result.update(blind=blind, models=list(panel.model_keys),
                  models_excluded=exclusions.get("models_below_coverage_floor", {}))
    return result

"""Everything PREREGISTRATION.md says is reported ALWAYS, beside the headline.

  4.1     `variance_reduction` and `rho_bar` to four decimals, always with headroom
  4.2     `n_eff_mse` -- "the primary for the systemic-risk claim" -- beside the
          Pearson headroom, and the gap between the two
  5.4(a)  the distribution of emitted values, the exact-tie rate, and the estimate
          re-run without exact ties
  5.4(b)  every primary estimate stratified by horizon band (Type A; Type B is one
          unbanded stratum)
  5.4(d)  `rho_bar` raw and disattenuated, with every model's reliability
  H5      headroom on Type A against Type B
  and the sensitivities the record owes: without `claude_sonnet`, and without the
  two days collected at max_tokens 400 (VALIDITY.md 7, deviation 1).

Until 2026-09-13 the analysis driver computed `rho_bar` and N_eff and none of this
(PREREGISTRATION.md 11, deviation 17). This module composes; every estimator in it
is the registered one from `stats.py`, `metrics.py` or `analysis.estimate`. It
never permutes or unpermutes anything -- it reports on the panel it is handed, so
a blind driver hands it a blind panel.
"""

import math
from typing import Callable, Dict, Optional, Sequence

import numpy as np

from . import analysis
from .analysis import ALPHA, BLOCK_DAYS, N_BOOT, resolution_event
from .metrics import variance_reduction
from .panel import Panel, _rows
from .stats import (
    _moving_block_indices,
    disattenuate,
    mean_pairwise_correlation,
    mean_uncentered_correlation,
    n_eff,
    n_eff_mse,
    pairwise_error_correlations,
)

HORIZON_BANDS = ((3, 14), (15, 45), (46, 90), (91, 10_000))    # 5.4(b)
MAX_TOKENS_400_DAYS = ("2026-09-01", "2026-09-02")             # deviation 1
FRONTIER_ANCHOR = "claude_sonnet"                              # VALIDITY.md 7.5


def _finite(value: float) -> Optional[float]:
    return float(value) if value is not None and np.isfinite(value) else None


def interval(panel: Panel, statistic: Callable[[np.ndarray], float], n_boot: int = N_BOOT,
             seed: int = 0) -> Dict[str, Dict[str, Optional[float]]]:
    """Both registered intervals (5.2), and the settlement-clustered sensitivity, for any statistic."""
    rng = np.random.default_rng(seed)
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for label, groups, block in (
        ("day_blocked", panel.asked_on, BLOCK_DAYS),
        ("event_clustered_registered", panel.question_ids, 1),
        ("event_clustered_settlement", [resolution_event(q) for q in panel.question_ids], 1),
    ):
        draws = np.array([statistic(panel.errors[_moving_block_indices(panel.n_tasks, block, rng, groups)])
                          for _ in range(n_boot)])
        finite = draws[np.isfinite(draws)]
        out[label] = {
            "lo": float(np.percentile(finite, 100 * ALPHA / 2)) if finite.size else None,
            "hi": float(np.percentile(finite, 100 * (1 - ALPHA / 2))) if finite.size else None,
            "undefined_draws": int(n_boot - finite.size),
        }
    return out


def co_primary(panel: Panel, n_boot: int = N_BOOT, seed: int = 0) -> Dict[str, object]:
    """4.1 and 4.2: the Pearson scale and the MSE scale, side by side, with intervals."""
    e = panel.errors
    rho = mean_pairwise_correlation(e)
    m = panel.n_models
    pearson_n_eff = n_eff(rho, m) if m >= 2 and np.isfinite(rho) else math.nan
    mse_n_eff = n_eff_mse(e)
    out: Dict[str, object] = {
        "rho_bar": _finite(round(rho, 4) if np.isfinite(rho) else rho),
        "rho_bar_uncentered": _finite(mean_uncentered_correlation(e)),
        "headroom_pearson": _finite(pearson_n_eff - 1.0),
        "n_eff_mse": _finite(mse_n_eff),
        "headroom_mse": _finite(mse_n_eff - 1.0),
        "variance_reduction": _finite(variance_reduction(e)),
        # 4.2: "Where the two diverge, the divergence IS the shared-bias finding."
        "gap_headroom_pearson_minus_mse": _finite((pearson_n_eff - 1.0) - (mse_n_eff - 1.0)),
    }
    if panel.n_tasks >= 3 and n_boot > 0:
        out["n_eff_mse_intervals"] = interval(panel, n_eff_mse, n_boot, seed)
        out["variance_reduction_intervals"] = interval(panel, variance_reduction, n_boot, seed)
    return out


def exact_tie_rows(panel: Panel) -> np.ndarray:
    """5.4(a): task-days on which every responding model (at least two) emitted one value."""
    ties = np.zeros(panel.n_tasks, dtype=bool)
    for i, row in enumerate(panel.forecasts):
        values = row[~np.isnan(row)]
        ties[i] = values.size >= 2 and bool(np.all(values == values[0]))
    return ties


def emitted_values(panel: Panel, top: int = 12) -> Dict[str, object]:
    """5.4(a): the full distribution of emitted values, summarised, and the tie rate."""
    values = panel.forecasts[~np.isnan(panel.forecasts)]
    uniques, counts = np.unique(np.round(values, 4), return_counts=True)
    order = np.argsort(-counts)[:top]
    ties = exact_tie_rows(panel)
    return {
        "n_values": int(values.size),
        "distinct_values": int(uniques.size),
        "most_common": [[float(uniques[k]), int(counts[k])] for k in order],
        "share_on_tenths": float(np.mean(np.isclose((values * 10) % 1, 0) | np.isclose((values * 10) % 1, 1)))
        if values.size else None,
        "exact_tie_rate": float(ties.mean()) if ties.size else None,
        "exact_tie_task_days": int(ties.sum()),
    }


def disattenuated_rho(panel: Panel, reliabilities: Dict[str, Dict[str, float]]) -> Dict[str, object]:
    """5.4(d): each estimable pair's correlation corrected for both models' noise, averaged.

    Reported beside the raw value, never instead of it: the correction raises rho
    and lowers N_eff, toward this study's own hypothesis.
    """
    corr, pairs = pairwise_error_correlations(panel.errors)
    corrected = []
    for r, (i, j) in zip(corr, pairs):
        rel_i = (reliabilities.get(panel.model_keys[i]) or {}).get("reliability")
        rel_j = (reliabilities.get(panel.model_keys[j]) or {}).get("reliability")
        if rel_i is None or rel_j is None:
            continue
        value = disattenuate(float(r), float(rel_i), float(rel_j))
        if np.isfinite(value):
            corrected.append(value)
    return {
        "rho_bar_raw": _finite(float(np.mean(corr)) if corr.size else math.nan),
        "rho_bar_disattenuated": _finite(float(np.mean(corrected)) if corrected else math.nan),
        "pairs_corrected": len(corrected),
        "pairs": len(pairs),
        "reliabilities": {k: v for k, v in reliabilities.items() if k in panel.model_keys},
    }


def kind_of(state: Dict) -> str:
    return "filing" if (state or {}).get("last_reported_end") else "event"


def _estimate(panel: Panel, n_boot: int) -> Dict[str, object]:
    if panel.n_tasks < 3 or panel.n_models < 2:
        return {"n_tasks": panel.n_tasks, "estimable": False}
    out = analysis.estimate(panel, n_boot=n_boot)
    out.update(co_primary(panel, n_boot=0))
    return out


def strata(panel: Panel, n_boot: int = N_BOOT) -> Dict[str, object]:
    kinds = [kind_of(s) for s in panel.state]
    days_out = [(s or {}).get("days_out") for s in panel.state]
    out: Dict[str, object] = {"by_task_type": {}, "by_horizon_band": {}, "sensitivity": {}}
    for kind in ("event", "filing"):
        out["by_task_type"][kind] = _estimate(_rows(panel, [i for i, k in enumerate(kinds) if k == kind]), n_boot)
    for lo, hi in HORIZON_BANDS:
        rows = [i for i, (k, d) in enumerate(zip(kinds, days_out))
                if k == "event" and isinstance(d, (int, float)) and lo <= d <= hi]
        out["by_horizon_band"][f"{lo}-{hi}"] = _estimate(_rows(panel, rows), n_boot)
    ties = exact_tie_rows(panel)
    out["sensitivity"]["without_exact_ties"] = _estimate(_rows(panel, np.nonzero(~ties)[0]), n_boot)
    out["sensitivity"]["without_max_tokens_400_days"] = _estimate(
        _rows(panel, [i for i, d in enumerate(panel.asked_on) if d not in MAX_TOKENS_400_DAYS]), n_boot)
    if FRONTIER_ANCHOR in panel.model_keys:
        out["sensitivity"]["without_" + FRONTIER_ANCHOR] = _estimate(
            panel.subset_by_models([k for k in panel.model_keys if k != FRONTIER_ANCHOR]), n_boot)
    return out


def registered_report(panel: Panel, n_boot: int = N_BOOT,
                      reliabilities: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, object]:
    """Every always-reported quantity for one (already excluded, possibly permuted) panel."""
    return {
        "co_primary": co_primary(panel, n_boot),
        "emitted_values": emitted_values(panel),
        "disattenuation": disattenuated_rho(panel, reliabilities or {}),
        "strata": strata(panel, n_boot),
    }

"""Estimators for effective independence of a forecaster panel.

The central object is N_eff, the *effective number of independent forecasters*.

Given M forecasters whose errors are equicorrelated with mean pairwise correlation
rho_bar, the variance of their mean error is

    Var(mean error) = (sigma^2 / M) * (1 + (M - 1) * rho_bar)

An ensemble of N independent forecasters would give Var = sigma^2 / N. Setting the
two equal:

    N_eff = M / (1 + (M - 1) * rho_bar)

So N_eff answers: "how many genuinely independent opinions is this panel worth?"
At rho_bar = 0, N_eff = M. At rho_bar = 1, N_eff = 1.

IMPORTANT — we correlate ERRORS, not raw forecasts. Two forecasters who are both
right agree strongly but are not redundant in the dangerous sense; the task simply
had a knowable answer. Correlating errors nets out the shared signal and isolates
*shared wrongness*, which is the only kind that creates systemic risk. This is the
distinction the theory literature draws and never measures.
"""

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

__all__ = [
    "pairwise_error_correlations",
    "mean_pairwise_correlation",
    "n_eff",
    "n_eff_from_errors",
    "block_bootstrap_ci",
    "_moving_block_indices",
    "benjamini_hochberg",
    "signal_error_decomposition",
]


def _as_error_matrix(errors: np.ndarray) -> np.ndarray:
    """Validate and coerce to a (n_tasks, n_forecasters) float array."""
    arr = np.asarray(errors, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"errors must be 2-D (n_tasks, n_forecasters), got shape {arr.shape}")
    if arr.shape[0] < 2:
        raise ValueError("need at least 2 tasks to estimate a correlation")
    if arr.shape[1] < 2:
        raise ValueError("need at least 2 forecasters to estimate a pairwise correlation")
    return arr


def pairwise_error_correlations(
    errors: np.ndarray,
    min_overlap: int = 3,
) -> Tuple[np.ndarray, List[Tuple[int, int]]]:
    """Pearson correlation for every forecaster pair, over tasks both answered.

    Args:
        errors: (n_tasks, n_forecasters). NaN marks "this forecaster skipped this task".
        min_overlap: minimum jointly-answered tasks required to report a pair.

    Returns:
        (correlations, pairs) where correlations[k] corresponds to pairs[k] = (i, j).
        Pairs with insufficient overlap, or with zero variance in either leg, are omitted.

    Missing data is handled pairwise rather than by dropping tasks, because a panel
    where one model rate-limits on a busy day should not silently discard that day
    for everyone -- that would preferentially drop high-volatility days, which is
    exactly where our hypothesis lives.
    """
    arr = _as_error_matrix(errors)
    n_forecasters = arr.shape[1]

    correlations: List[float] = []
    pairs: List[Tuple[int, int]] = []

    for i in range(n_forecasters):
        for j in range(i + 1, n_forecasters):
            a, b = arr[:, i], arr[:, j]
            mask = ~np.isnan(a) & ~np.isnan(b)
            if int(mask.sum()) < min_overlap:
                continue
            av, bv = a[mask], b[mask]
            # A degenerate leg (constant error) has undefined correlation. Skip it
            # rather than emitting a NaN that silently poisons the mean.
            if np.std(av) == 0.0 or np.std(bv) == 0.0:
                continue
            correlations.append(float(np.corrcoef(av, bv)[0, 1]))
            pairs.append((i, j))

    return np.asarray(correlations, dtype=float), pairs


def mean_pairwise_correlation(errors: np.ndarray, min_overlap: int = 3) -> float:
    """Mean pairwise error correlation (rho_bar). NaN if no pair is estimable."""
    correlations, _ = pairwise_error_correlations(errors, min_overlap=min_overlap)
    if correlations.size == 0:
        return float("nan")
    return float(np.mean(correlations))


def n_eff(rho_bar: float, n_forecasters: int) -> float:
    """Effective number of independent forecasters.

        N_eff = M / (1 + (M - 1) * rho_bar)

    Negative rho_bar (forecasters that are anti-correlated, i.e. better than
    independent) can push the denominator to zero or below. We clamp rho_bar at
    its theoretical floor of -1/(M-1), the point below which an equicorrelation
    matrix stops being positive semi-definite and the formula is meaningless.
    """
    if n_forecasters < 2:
        raise ValueError("n_forecasters must be >= 2")
    if not np.isfinite(rho_bar):
        return float("nan")

    floor = -1.0 / (n_forecasters - 1)
    rho = max(float(rho_bar), floor + 1e-12)
    return n_forecasters / (1.0 + (n_forecasters - 1) * rho)


def n_eff_from_errors(errors: np.ndarray, min_overlap: int = 3) -> float:
    """Convenience: rho_bar then N_eff, using the panel's forecaster count."""
    arr = _as_error_matrix(errors)
    rho_bar = mean_pairwise_correlation(arr, min_overlap=min_overlap)
    return n_eff(rho_bar, arr.shape[1])


def _moving_block_indices(
    n_rows: int,
    block_size: int,
    rng: np.random.Generator,
    groups: Optional[Sequence] = None,
) -> np.ndarray:
    """Row indices for one moving-block resample.

    `groups is None` -- blocks are contiguous ROWS. Correct only when one row is
    one time step.

    `groups` supplied -- blocks are contiguous GROUPS (task-days), and every row
    belonging to a sampled day travels with it. This is what the pre-registration
    means by "block size 5 task-days", and it is NOT the same thing as five rows.

    Why the distinction is not pedantic: the panel carries ~25 tasks per day and
    `tasks.py` re-asks each open question every day until it resolves, so the
    same question's rows sit ~25 apart in day-major order. A five-ROW block
    therefore lies strictly inside one day and can never span two observations of
    the same question -- the dominant dependence in the design is invisible to it,
    and the interval collapses. Measured on a simulation matching the real panel
    shape (9 models, 25 tasks/day, 105 days, AR(.95) per-question persistence):

        block_size=5 rows      CI width 0.0038   <- 57% too narrow
        block_size=5 task-days CI width 0.0089

    This is the same failure as the row-ordering bug recorded in panel.py, and it
    reaches the headline statistic, so it is enforced here rather than left to the
    caller to remember.
    """
    if groups is None:
        bs = max(1, min(block_size, n_rows))
        n_blocks = int(np.ceil(n_rows / bs))
        starts = rng.integers(0, n_rows - bs + 1, size=n_blocks)
        return np.concatenate([np.arange(s, s + bs) for s in starts])[:n_rows]

    # First-appearance order. Panel rows are already sorted day-major, so this
    # preserves true temporal adjacency between consecutive days.
    order: List[List[int]] = []
    seen: Dict[object, int] = {}
    for i, g in enumerate(groups):
        if g not in seen:
            seen[g] = len(order)
            order.append([])
        order[seen[g]].append(i)

    day_rows = [np.asarray(rows, dtype=int) for rows in order]
    n_days = len(day_rows)
    if n_days == 0:
        return np.arange(0, dtype=int)

    bs = max(1, min(block_size, n_days))
    n_blocks = int(np.ceil(n_days / bs))
    starts = rng.integers(0, n_days - bs + 1, size=n_blocks)

    picked = [day_rows[d] for s in starts for d in range(s, s + bs)]
    # Deliberately NOT truncated to n_rows: days hold unequal numbers of tasks,
    # and clipping mid-block would systematically drop the later days of every
    # block and bias the resample toward block-leading days.
    return np.concatenate(picked)


def block_bootstrap_ci(
    errors: np.ndarray,
    statistic: str = "n_eff",
    block_size: int = 5,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: Optional[int] = 0,
    min_overlap: int = 3,
    groups: Optional[Sequence] = None,
) -> Tuple[float, float, float]:
    """Moving-block bootstrap confidence interval.

    Pass `groups=panel.asked_on` for study analysis. Then `block_size` counts
    TASK-DAYS, which is what the pre-registration registers. Without it,
    `block_size` counts rows and the interval will be far too narrow -- see
    `_moving_block_indices`.

    Why *block* bootstrap and not the ordinary kind: our tasks arrive as a daily
    time series, and both market state and model behaviour are autocorrelated
    across adjacent days. An ordinary bootstrap resamples individual tasks as if
    they were independent draws, which destroys that dependence and produces
    intervals that are far too narrow -- it would make us claim more precision
    than the data supports. Resampling contiguous blocks preserves short-range
    dependence within each block.

    Returns:
        (point_estimate, lower, upper) using the percentile method.
    """
    arr = _as_error_matrix(errors)
    n_tasks, n_forecasters = arr.shape

    if block_size < 1:
        raise ValueError("block_size must be >= 1")
    block_size = min(block_size, n_tasks)

    def _stat(sample: np.ndarray) -> float:
        if statistic == "n_eff":
            return n_eff_from_errors(sample, min_overlap=min_overlap)
        if statistic == "rho_bar":
            return mean_pairwise_correlation(sample, min_overlap=min_overlap)
        raise ValueError(f"unknown statistic: {statistic!r}")

    point = _stat(arr)

    if groups is not None and len(groups) != n_tasks:
        raise ValueError(
            f"groups has length {len(groups)} but errors has {n_tasks} rows"
        )

    rng = np.random.default_rng(seed)

    draws = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = _moving_block_indices(n_tasks, block_size, rng, groups)
        draws[b] = _stat(arr[idx])

    finite = draws[np.isfinite(draws)]
    if finite.size == 0:
        return point, float("nan"), float("nan")

    lower = float(np.percentile(finite, 100 * alpha / 2))
    upper = float(np.percentile(finite, 100 * (1 - alpha / 2)))
    return point, lower, upper


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg FDR control. Returns a boolean 'reject' mask.

    We test state-dependence across the SEVEN registered state variables
    (ladder distance, VIX, realised vol, dispersion, |surprise|, days-to-
    resolution, novelty -- `config.STATE_VARIABLES`). Testing seven hypotheses at
    alpha=0.05 each gives roughly a 30% chance of at least one false positive.

    The denominator is the length of that list, so adding or dropping a variable
    moves H1's falsification threshold. It listed `news_volume` -- never
    registered -- and omitted days-to-resolution until the 18 Aug audit.
    BH controls the expected *proportion* of false discoveries instead, which is
    the right correction when the tests are related and we care about which
    findings survive as a set.
    """
    p = np.asarray(list(p_values), dtype=float)
    if p.size == 0:
        return np.zeros(0, dtype=bool)
    if np.any((p < 0) | (p > 1)):
        raise ValueError("p-values must lie in [0, 1]")

    n = p.size
    order = np.argsort(p)
    ranked = p[order]
    thresholds = alpha * np.arange(1, n + 1) / n

    passing = np.nonzero(ranked <= thresholds)[0]
    reject = np.zeros(n, dtype=bool)
    if passing.size > 0:
        # Everything up to the largest passing rank is rejected.
        reject[order[: passing[-1] + 1]] = True
    return reject


def signal_error_decomposition(
    forecasts: np.ndarray,
    outcomes: np.ndarray,
    min_overlap: int = 3,
) -> Dict[str, float]:
    """Separate agreement driven by shared signal from agreement driven by shared error.

    Reports:
        forecast_corr -- mean pairwise correlation of raw forecasts
        error_corr    -- mean pairwise correlation of errors
        excess        -- forecast_corr - error_corr

    High forecast correlation with low error correlation is the benign case: the
    panel agrees because the questions had knowable answers. High *error*
    correlation is the dangerous case: the panel is wrong together. Reporting
    both makes it impossible to overstate the finding by quoting raw agreement.
    """
    f = np.asarray(forecasts, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if f.ndim != 2:
        raise ValueError("forecasts must be 2-D (n_tasks, n_forecasters)")
    if y.shape[0] != f.shape[0]:
        raise ValueError("outcomes length must match number of tasks")

    errors = f - y[:, None]
    forecast_corr = mean_pairwise_correlation(f, min_overlap=min_overlap)
    error_corr = mean_pairwise_correlation(errors, min_overlap=min_overlap)
    return {
        "forecast_corr": forecast_corr,
        "error_corr": error_corr,
        "excess": forecast_corr - error_corr,
        "n_eff_forecast": n_eff(forecast_corr, f.shape[1]),
        "n_eff_error": n_eff(error_corr, f.shape[1]),
    }


# ---------------------------------------------------------------------------
# UNCENTERED (SECOND-MOMENT) ESTIMATORS
#
# Added 17 Aug 2026, before collection, after a simulation showed the Pearson
# estimators above are BLIND to the failure mode this study exists to measure.
#
# Pearson correlation subtracts each forecaster's own mean error, so a bias that
# every forecaster shares is differenced away. Simulated at M = 7, T = 400 with
# independent idiosyncratic errors and a common bias b added to all seven:
#
#     b = 0.00 -> Pearson rho = +0.016, headroom 5.40  | true N_eff(MSE) = 6.38
#     b = 0.10 -> Pearson rho = -0.008, headroom 6.35  | true N_eff(MSE) = 3.27
#     b = 0.20 -> Pearson rho = +0.010, headroom 5.59  | true N_eff(MSE) = 1.70
#     b = 0.30 -> Pearson rho = +0.013, headroom 5.49  | true N_eff(MSE) = 1.37
#
# Pearson reports "seven nearly independent minds" at every bias level while the
# panel is in fact collapsing to one. "Every model wrong in the same direction"
# IS the systemic-risk story, so an estimator that cannot see it is the wrong
# primary. These uncentered versions keep the mean in.
# ---------------------------------------------------------------------------


def uncentered_pairwise_correlations(
    errors: np.ndarray, min_overlap: int = 3
) -> Tuple[np.ndarray, List[Tuple[int, int]]]:
    """Second-moment correlation E[e_i e_j] / sqrt(E[e_i^2] E[e_j^2]) per pair.

    Identical in structure to `pairwise_error_correlations` but WITHOUT removing
    each forecaster's mean error, so shared bias counts as shared error -- which
    is what it is.
    """
    arr = _as_error_matrix(errors)
    n_forecasters = arr.shape[1]

    correlations: List[float] = []
    pairs: List[Tuple[int, int]] = []

    for i in range(n_forecasters):
        for j in range(i + 1, n_forecasters):
            a, b = arr[:, i], arr[:, j]
            mask = ~np.isnan(a) & ~np.isnan(b)
            if int(mask.sum()) < min_overlap:
                continue
            av, bv = a[mask], b[mask]
            denom = np.sqrt(np.mean(av**2) * np.mean(bv**2))
            if not np.isfinite(denom) or denom == 0.0:
                continue
            correlations.append(float(np.mean(av * bv) / denom))
            pairs.append((i, j))

    return np.asarray(correlations, dtype=float), pairs


def mean_uncentered_correlation(errors: np.ndarray, min_overlap: int = 3) -> float:
    """rho_bar computed on second moments rather than on deviations from the mean."""
    correlations, _ = uncentered_pairwise_correlations(errors, min_overlap=min_overlap)
    if correlations.size == 0:
        return float("nan")
    return float(np.mean(correlations))


def n_eff_mse(errors: np.ndarray, min_models: int = 2) -> float:
    """Model-free effective panel size on the MSE scale.

        N_eff_mse = mean_i MSE_i / MSE(panel mean)

    This makes no equicorrelation assumption and no zero-bias assumption. It
    answers the operational question directly: by what factor does averaging the
    panel actually reduce squared error? A panel that shares a bias cannot
    average it away, and this statistic shows that; the Pearson version does not.
    """
    arr = np.asarray(errors, dtype=float)
    if arr.ndim != 2:
        raise ValueError("errors must be 2-D (n_tasks, n_forecasters)")

    counts = np.sum(~np.isnan(arr), axis=1)
    keep = counts >= min_models
    if int(keep.sum()) < 3:
        return float("nan")
    arr = arr[keep]

    with np.errstate(invalid="ignore"):
        per_model_mse = np.nanmean(arr**2, axis=0)
        panel_mean = np.nanmean(arr, axis=1)

    mean_mse = float(np.nanmean(per_model_mse))
    panel_mse = float(np.mean(panel_mean**2))
    if not np.isfinite(mean_mse) or panel_mse <= 0:
        return float("nan")
    return mean_mse / panel_mse


__all__ += [
    "uncentered_pairwise_correlations",
    "mean_uncentered_correlation",
    "n_eff_mse",
]


# --- test-retest reliability -------------------------------------------------
#
# `TEMPERATURE = 0.0` is registered so that cross-model differences reflect the
# models rather than our sampling. Measured 22 Aug 2026 (3 prompts x 4 reps) it
# holds for only five of ten models; the rest move their probability by
# 0.033-0.093 on average against an IDENTICAL prompt, and which models move
# shifts between runs -- so it is infrastructure, not a model property.
#
# The consequence is specific and it runs one way. Sampling noise is
# IDIOSYNCRATIC: it is uncorrelated across models by construction, so it dilutes
# every measured pairwise correlation and INFLATES apparent independence --
# rho_bar too low, N_eff too high. That biases against this study's own
# hypothesis, which is the safe direction, but the SIZE of the bias was unknown.
#
# These functions measure it from the daily replicates and undo it, so §5.4(d)
# can report rho_bar raw AND corrected rather than merely arguing about sign.


def test_retest_reliability(first: Sequence[float], second: Sequence[float]) -> float:
    """Reliability of one model: how much of its variance is signal, not noise.

    `first` and `second` are the model's two answers to the SAME prompts, asked
    identically on the same day.

    Returns 1 - Var(difference) / (2 * Var(all answers)), the standard
    test-retest form. 1.0 means perfectly repeatable; 0.0 means the answer is
    indistinguishable from noise. Clipped to [0, 1] because sampling error can
    push the raw quantity slightly outside it on small samples.
    """
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if a.size < 2:
        return float("nan")

    total = np.var(np.concatenate([a, b]), ddof=1)
    if total <= 0:
        # Every answer identical: no variance to explain, and no noise either.
        return 1.0
    noise = np.var(a - b, ddof=1) / 2.0
    return float(np.clip(1.0 - noise / total, 0.0, 1.0))


def disattenuate(rho: float, reliability_i: float, reliability_j: float) -> float:
    """Correct an observed correlation for measurement noise in both members.

    Spearman's classic correction: an observed correlation between two noisy
    measurements understates the true one by sqrt(rel_i * rel_j).

    This is reported ALONGSIDE the raw value, never instead of it. The correction
    moves rho UP, which moves N_eff DOWN -- toward this study's own hypothesis --
    so presenting only the corrected number would be arguing our own case with a
    statistical adjustment. Both, always, with the reliabilities stated.
    """
    if not np.isfinite(rho):
        return float("nan")
    denom = np.sqrt(max(reliability_i, 0.0) * max(reliability_j, 0.0))
    if denom <= 0:
        return float("nan")
    return float(np.clip(rho / denom, -1.0, 1.0))


def noise_floor(first: Sequence[float], second: Sequence[float]) -> float:
    """Standard deviation of a model's own sampling noise, in probability units.

    The directly interpretable companion to `test_retest_reliability`: "this
    model's answer wobbles by about +/- X on an identical question."
    """
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if a.size < 2:
        return float("nan")
    return float(np.sqrt(np.var(a - b, ddof=1) / 2.0))

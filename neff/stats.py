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


def block_bootstrap_ci(
    errors: np.ndarray,
    statistic: str = "n_eff",
    block_size: int = 5,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: Optional[int] = 0,
    min_overlap: int = 3,
) -> Tuple[float, float, float]:
    """Moving-block bootstrap confidence interval.

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

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n_tasks / block_size))
    max_start = n_tasks - block_size

    draws = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block_size) for s in starts])[:n_tasks]
        draws[b] = _stat(arr[idx])

    finite = draws[np.isfinite(draws)]
    if finite.size == 0:
        return point, float("nan"), float("nan")

    lower = float(np.percentile(finite, 100 * alpha / 2))
    upper = float(np.percentile(finite, 100 * (1 - alpha / 2)))
    return point, lower, upper


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg FDR control. Returns a boolean 'reject' mask.

    We test state-dependence across several state variables (VIX, realised vol,
    dispersion, |surprise|, news volume, novelty). Testing six hypotheses at
    alpha=0.05 each gives roughly a 26% chance of at least one false positive.
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

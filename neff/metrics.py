"""Primary outcome measures, and why these rather than the obvious ones.

THREE METRICS WERE CONSIDERED. TWO WERE REJECTED FOR STATED REASONS.

REJECTED 1 -- raw mean pairwise error correlation, reported as a level.
    Not wrong, but unreadable. Forecast errors are dominated by the surprise
    nobody anticipated, so rho sits near 1 for humans and machines alike
    (measured: 0.996 for SPF unemployment nowcasts). Reporting "0.996 versus
    0.994" buries a large practical difference under two decimal places.

REJECTED 2 -- "excess correlation over the common component", i.e. correlating
    residuals after removing the cross-panel mean error.
    **This is mathematically broken and was caught before collection began.**
    Residuals sum to zero by construction, so for independent idiosyncratic
    parts their pairwise correlation is EXACTLY -1/(M-1) -- verified by
    simulation at rho_true = 0.0, 0.5 and 0.9 for M = 3, 5, 7, 12, which all
    returned -1/(M-1) to three decimals. The statistic carries no information
    about the quantity it was meant to isolate. It was in an earlier draft of the
    pre-registration and has been removed.

ADOPTED -- diversification headroom, on the (1 - rho) scale.
    Near saturation, writing rho = 1 - eps gives

        N_eff - 1  ~  ((M-1)/M) * eps

    so the practical benefit of ensembling is proportional to (1 - rho), not to
    rho. That quantity is estimated to four decimal places with only 400 tasks
    (rho = 0.996 separates from 0.990 at 7.7 sigma), so nothing is saturated --
    the original metric was merely badly scaled for human reading.

    We report:
      - variance_reduction   : model-free, assumes no correlation structure
      - diversification_benefit : the fraction of error variance ensembling removes
      - headroom_ratio       : the headline human-versus-AI comparison

The headline number is a RATIO of benefits, because "both round to 1" conceals
differences of 20x in what ensembling actually buys.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .stats import (
    mean_pairwise_correlation,
    mean_uncentered_correlation,
    n_eff,
    n_eff_mse,
)

__all__ = [
    "variance_reduction",
    "mse_reduction",
    "diversification_benefit",
    "headroom",
    "effective_panel",
    "headroom_ratio",
    "PanelSummary",
]


@dataclass
class PanelSummary:
    """Everything we report about one panel's effective independence."""

    n_tasks: int
    n_forecasters: int
    rho_bar: float
    n_eff: float
    headroom: float                 # N_eff - 1: how much ensembling actually buys
    variance_reduction: float       # empirical Var(mean)/mean(Var), model-free
    diversification_benefit: float  # 1 - variance_reduction

    # --- uncentered / MSE scale: keeps shared bias in (see stats.py) ---------
    rho_bar_uncentered: float = float("nan")
    n_eff_mse: float = float("nan")
    headroom_mse: float = float("nan")
    mse_reduction: float = float("nan")
    mse_benefit: float = float("nan")

    ci: Optional[Tuple[float, float]] = None

    def describe(self) -> str:
        return (
            f"{self.n_forecasters} forecasters, {self.n_tasks} tasks: "
            f"rho={self.rho_bar:.4f} (uncentered {self.rho_bar_uncentered:.4f}), "
            f"N_eff={self.n_eff:.3f} (MSE scale {self.n_eff_mse:.3f}); "
            f"ensembling removes {100 * self.mse_benefit:.1f}% of squared error"
        )


def variance_reduction(errors: np.ndarray, min_models: int = 2) -> float:
    """Var(panel mean error) / mean(Var of individual errors).

    This is the model-free counterpart of 1/N_eff. It makes no equicorrelation
    assumption -- it simply measures what actually happens to error variance when
    you average the panel, which is exactly the quantity a risk manager cares
    about. Under equicorrelation it equals 1/N_eff; where it diverges, the
    equicorrelation assumption is doing work and we want to know that.

    Rows are used only where at least `min_models` forecasters responded, so a
    task answered by one model cannot masquerade as a zero-variance consensus.
    """
    arr = np.asarray(errors, dtype=float)
    if arr.ndim != 2:
        raise ValueError("errors must be 2-D (n_tasks, n_forecasters)")

    counts = np.sum(~np.isnan(arr), axis=1)
    keep = counts >= min_models
    if keep.sum() < 3:
        return float("nan")
    arr = arr[keep]

    with np.errstate(invalid="ignore"):
        panel_mean = np.nanmean(arr, axis=1)

    mean_var = float(np.nanmean(np.nanvar(arr, axis=0, ddof=1)))
    if not np.isfinite(mean_var) or mean_var <= 0:
        return float("nan")

    return float(np.var(panel_mean, ddof=1) / mean_var)


def mse_reduction(errors: np.ndarray, min_models: int = 2) -> float:
    """MSE(panel mean) / mean(MSE of individuals). The uncentered counterpart.

    `variance_reduction` above centres both terms, so a bias shared by the whole
    panel cancels from numerator and denominator alike and the statistic reports
    a diversification benefit the panel does not actually have. This version
    keeps the mean in. Where the two diverge, the gap IS the shared-bias finding.
    """
    value = n_eff_mse(errors, min_models=min_models)
    if not np.isfinite(value) or value <= 0:
        return float("nan")
    return float(1.0 / value)


def diversification_benefit(errors: np.ndarray) -> float:
    """Fraction of error variance removed by averaging the panel. In [0, 1)."""
    vr = variance_reduction(errors)
    if not np.isfinite(vr):
        return float("nan")
    return float(max(0.0, 1.0 - vr))


def headroom(rho_bar: float, n_forecasters: int) -> float:
    """N_eff - 1. Zero means the panel is worth exactly one opinion.

    This is the quantity that stays informative near saturation: it is
    approximately ((M-1)/M) * (1 - rho), so it scales linearly in the thing we
    can actually measure precisely.
    """
    value = n_eff(rho_bar, n_forecasters)
    if not np.isfinite(value):
        return float("nan")
    return float(value - 1.0)


def effective_panel(
    errors: np.ndarray, min_overlap: int = 3, ci: Optional[Tuple[float, float]] = None
) -> PanelSummary:
    """Full summary of one panel."""
    arr = np.asarray(errors, dtype=float)
    rho = mean_pairwise_correlation(arr, min_overlap=min_overlap)
    rho_unc = mean_uncentered_correlation(arr, min_overlap=min_overlap)
    m = int(arr.shape[1])
    vr = variance_reduction(arr)
    nem = n_eff_mse(arr)
    msr = mse_reduction(arr)
    return PanelSummary(
        n_tasks=int(arr.shape[0]),
        n_forecasters=m,
        rho_bar=float(rho),
        n_eff=float(n_eff(rho, m)),
        headroom=headroom(rho, m),
        variance_reduction=float(vr),
        diversification_benefit=float(diversification_benefit(arr)),
        rho_bar_uncentered=float(rho_unc),
        n_eff_mse=float(nem),
        headroom_mse=float(nem - 1.0) if np.isfinite(nem) else float("nan"),
        mse_reduction=float(msr),
        mse_benefit=float(max(0.0, 1.0 - msr)) if np.isfinite(msr) else float("nan"),
        ci=ci,
    )


def headroom_ratio(
    errors_reference: np.ndarray,
    errors_test: np.ndarray,
    n_boot: int = 2000,
    seed: int = 0,
    block_size: int = 5,
) -> Dict[str, float]:
    """How much more (or less) does the reference panel diversify than the test panel?

    This is the study's headline comparison, with `reference` = human forecasters
    and `test` = the AI panel.

        ratio = headroom(reference) / headroom(test)

    A ratio of 3 means human forecasters buy three times as much variance
    reduction from ensembling as the AI panel does -- which is the systemic-risk
    claim stated in a form a risk manager can act on.

    Reported with a block-bootstrap interval, resampling contiguous blocks
    because task-days are serially dependent.
    """
    ref = np.asarray(errors_reference, dtype=float)
    test = np.asarray(errors_test, dtype=float)

    def _headroom(sample: np.ndarray) -> float:
        rho = mean_pairwise_correlation(sample, min_overlap=3)
        return headroom(rho, int(sample.shape[1]))

    def _benefit(sample: np.ndarray) -> float:
        """Fraction of SQUARED error removed by averaging. Bounded in [0, 1)."""
        value = n_eff_mse(sample)
        if not np.isfinite(value) or value <= 0:
            return float("nan")
        return float(max(0.0, 1.0 - 1.0 / value))

    point_ref, point_test = _headroom(ref), _headroom(test)
    benefit_ref, benefit_test = _benefit(ref), _benefit(test)
    ratio = (
        point_ref / point_test
        if np.isfinite(point_test) and point_test > 0
        else float("nan")
    )

    rng = np.random.default_rng(seed)

    def _resample(sample: np.ndarray) -> np.ndarray:
        n = sample.shape[0]
        bs = min(block_size, n)
        n_blocks = int(np.ceil(n / bs))
        starts = rng.integers(0, max(1, n - bs + 1), size=n_blocks)
        idx = np.concatenate([np.arange(s, s + bs) for s in starts])[:n]
        return sample[idx]

    draws: List[float] = []
    diffs: List[float] = []
    benefit_diffs: List[float] = []
    for _ in range(n_boot):
        ra, rb = _resample(ref), _resample(test)
        a, b = _headroom(ra), _headroom(rb)
        if np.isfinite(a) and np.isfinite(b):
            diffs.append(a - b)
            if b > 0:
                draws.append(a / b)
        ba, bb = _benefit(ra), _benefit(rb)
        if np.isfinite(ba) and np.isfinite(bb):
            benefit_diffs.append(ba - bb)

    def _ci(values: List[float]) -> Tuple[float, float]:
        if not values:
            return float("nan"), float("nan")
        return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))

    lo, hi = _ci(draws)
    diff_lo, diff_hi = _ci(diffs)
    ben_lo, ben_hi = _ci(benefit_diffs)

    return {
        # --- PRIMARY: bounded and interpretable ------------------------------
        # The ratio is unstable precisely where H4 predicts it lands: as the AI
        # panel's headroom approaches zero the ratio runs away (simulated: 3.9 at
        # rho_AI = 0.97 but 1294 at rho_AI = 0.9999), and "AI is 1294x less
        # diversified" is an arithmetically true, rhetorically worthless number.
        # The variance-reduction difference is bounded in [-1, 1] and states the
        # same fact in a form a risk manager can act on.
        "benefit_reference": float(benefit_ref),
        "benefit_test": float(benefit_test),
        "benefit_difference": float(benefit_ref - benefit_test),
        "benefit_difference_ci": (ben_lo, ben_hi),
        "headroom_reference": float(point_ref),
        "headroom_test": float(point_test),
        "headroom_difference": float(point_ref - point_test),
        "headroom_difference_ci": (diff_lo, diff_hi),
        # --- SECONDARY: the ratio, with its instability made visible ---------
        "ratio": float(ratio),
        "ci_low": lo,
        "ci_high": hi,
        "n_boot_valid": len(draws),
        "n_boot_ratio_undefined": int(n_boot - len(draws)),
    }

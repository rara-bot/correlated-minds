"""Registered analyses that need to exist as code, not just as prose in the plan.

Three of the pre-registered tests were specified in PREREGISTRATION.md before
they were implementable. A registered analysis nobody has written is a promise,
not a method -- so each one here is executable and tested against synthetic data
with a known answer.

  H6  capability control  -- does same-family lineage predict error correlation
                             once the pair's ACCURACY is in the model? (arXiv
                             2607.20768 shows most diversity findings do not
                             survive this.)
  5.4a exact-tie rate     -- do models collapse onto identical round numbers?
  5.4b horizon strata     -- are primary estimates stable across horizon bands,
                             or is the eligible pool's drift toward the freeze
                             doing the work?
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import panel_by_key
from .stats import mean_pairwise_correlation

__all__ = [
    "brier_skill_per_model",
    "lineage_permutation_test",
    "exact_tie_rate",
    "pairwise_capability_frame",
    "capability_controlled_lineage_test",
    "horizon_strata",
    "LineageTest",
]

HORIZON_BANDS: Tuple[Tuple[str, float, float], ...] = (
    ("3-14d", 3.0, 14.0),
    ("15-45d", 15.0, 45.0),
    ("46-90d", 46.0, 90.0),
    ("91d+", 91.0, float("inf")),
)


def brier_skill_per_model(forecasts: np.ndarray, outcomes: np.ndarray) -> np.ndarray:
    """Brier skill vs. the base rate, per model. Higher is better; 0 = no skill.

    Skill rather than raw Brier because the reference must be the same for every
    model, otherwise "accuracy" in the H6 regression would partly encode which
    questions a model happened to answer.
    """
    f = np.asarray(forecasts, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    base = float(np.nanmean(y))
    reference = float(np.nanmean((base - y) ** 2))
    if not np.isfinite(reference) or reference <= 0:
        return np.full(f.shape[1], np.nan)
    with np.errstate(invalid="ignore"):
        brier = np.nanmean((f - y[:, None]) ** 2, axis=0)
    return 1.0 - brier / reference


def exact_tie_rate(forecasts: np.ndarray, min_models: int = 3) -> Dict[str, float]:
    """Fraction of task-days on which every responding model returned the SAME value.

    This is the shared-mass-point threat from §5.4(a). Independent rounding adds
    idiosyncratic noise and is harmless; models converging on one identical round
    number collapses cross-model dispersion and inflates rho for a reason that is
    about verbal habit rather than shared priors.
    """
    f = np.asarray(forecasts, dtype=float)
    ties = 0
    usable = 0
    values: List[float] = []
    for row in f:
        present = row[~np.isnan(row)]
        if present.size < min_models:
            continue
        usable += 1
        values.extend(present.tolist())
        if np.allclose(present, present[0]):
            ties += 1
    unique = len(set(np.round(values, 6))) if values else 0
    return {
        "tasks_considered": float(usable),
        "exact_tie_rate": float(ties / usable) if usable else float("nan"),
        "distinct_values_emitted": float(unique),
        "values_per_task": float(len(values) / usable) if usable else float("nan"),
    }


def pairwise_capability_frame(
    errors: np.ndarray,
    forecasts: np.ndarray,
    outcomes: np.ndarray,
    model_keys: Sequence[str],
    block_index: Optional[Sequence[int]] = None,
    min_overlap: int = 6,
) -> Dict[str, np.ndarray]:
    """One row per (model pair, time block): correlation, lineage, capability.

    Blocking by time rather than pooling is what makes H6 estimable. Pooled over
    the whole sample there are only M(M-1)/2 = 21 correlations -- too few to
    separate lineage from capability. Computing each pair's correlation within
    each block gives 21 x n_blocks rows, and standard errors are then clustered
    BY PAIR, because a pair's blocks are not independent of one another.
    """
    e = np.asarray(errors, dtype=float)
    f = np.asarray(forecasts, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    keys = list(model_keys)
    spec = panel_by_key()
    families = [spec[k].family if k in spec else k for k in keys]

    blocks = (
        np.asarray(block_index, dtype=int)
        if block_index is not None
        else np.zeros(e.shape[0], dtype=int)
    )

    rho: List[float] = []
    same_family: List[float] = []
    mean_skill: List[float] = []
    skill_gap: List[float] = []
    pair_id: List[int] = []

    pair_counter = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            for b in np.unique(blocks):
                rows = blocks == b
                if int(rows.sum()) < min_overlap:
                    continue
                sub = e[rows][:, [i, j]]
                r = mean_pairwise_correlation(sub, min_overlap=min_overlap)
                if not np.isfinite(r):
                    continue
                skill = brier_skill_per_model(f[rows][:, [i, j]], y[rows])
                if not np.all(np.isfinite(skill)):
                    continue
                rho.append(r)
                same_family.append(1.0 if families[i] == families[j] else 0.0)
                mean_skill.append(float(np.mean(skill)))
                skill_gap.append(float(abs(skill[0] - skill[1])))
                pair_id.append(pair_counter)
            pair_counter += 1

    return {
        "rho": np.asarray(rho, dtype=float),
        "same_family": np.asarray(same_family, dtype=float),
        "mean_skill": np.asarray(mean_skill, dtype=float),
        "skill_gap": np.asarray(skill_gap, dtype=float),
        "pair_id": np.asarray(pair_id, dtype=int),
    }


@dataclass
class LineageTest:
    """Result of H6. `survives` is the pre-registered decision rule."""

    n_obs: int
    n_pairs: int
    coefficients: Dict[str, float] = field(default_factory=dict)
    std_errors: Dict[str, float] = field(default_factory=dict)
    t_stats: Dict[str, float] = field(default_factory=dict)
    survives: bool = False

    def describe(self) -> str:
        if not self.coefficients:
            return "H6: not estimable"
        parts = [
            f"{k}={self.coefficients[k]:+.4f} (t={self.t_stats.get(k, float('nan')):+.2f})"
            for k in self.coefficients
        ]
        verdict = "LINEAGE SURVIVES" if self.survives else "capability explains it"
        return f"H6 [{verdict}] n={self.n_obs} pairs={self.n_pairs}: " + ", ".join(parts)


def capability_controlled_lineage_test(
    frame: Dict[str, np.ndarray], t_threshold: float = 2.0
) -> LineageTest:
    """OLS of pairwise error correlation on lineage + capability, clustered by pair.

    Registered decision rule (H6): the lineage claim survives only if the
    `same_family` coefficient remains distinguishable from zero WITH the
    capability terms in the model. If it does not, the honest reading is that the
    measured correlation is a capability phenomenon and H3 is reinterpreted.
    """
    rho = frame["rho"]
    if rho.size < 8:
        return LineageTest(n_obs=int(rho.size), n_pairs=0)

    names = ["intercept", "same_family", "mean_skill", "skill_gap"]
    X = np.column_stack(
        [np.ones_like(rho), frame["same_family"], frame["mean_skill"], frame["skill_gap"]]
    )
    # Drop regressors with no variation, otherwise the design is singular.
    keep = [0] + [k for k in range(1, X.shape[1]) if np.std(X[:, k]) > 1e-12]
    X = X[:, keep]
    names = [names[k] for k in keep]

    beta, *_ = np.linalg.lstsq(X, rho, rcond=None)
    resid = rho - X @ beta
    XtX_inv = np.linalg.pinv(X.T @ X)

    # Cluster-robust (CR0) by pair: a pair's blocks are serially dependent.
    meat = np.zeros((X.shape[1], X.shape[1]))
    clusters = frame["pair_id"]
    for c in np.unique(clusters):
        rows = clusters == c
        Xc, uc = X[rows], resid[rows]
        s = Xc.T @ uc
        meat += np.outer(s, s)
    cov = XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.clip(np.diag(cov), 0.0, None))

    coefficients = {n: float(b) for n, b in zip(names, beta)}
    std_errors = {n: float(s) for n, s in zip(names, se)}
    t_stats = {
        n: float(coefficients[n] / std_errors[n]) if std_errors[n] > 0 else float("nan")
        for n in names
    }
    return LineageTest(
        n_obs=int(rho.size),
        n_pairs=int(np.unique(clusters).size),
        coefficients=coefficients,
        std_errors=std_errors,
        t_stats=t_stats,
        survives=bool(abs(t_stats.get("same_family", 0.0)) >= t_threshold),
    )


def lineage_permutation_test(
    errors: np.ndarray,
    forecasts: np.ndarray,
    outcomes: np.ndarray,
    model_keys: Sequence[str],
    block_index: Optional[Sequence[int]] = None,
    n_permutations: int = 5000,
    seed: int = 0,
    min_overlap: int = 6,
) -> Dict[str, float]:
    """Exact-style permutation test for the lineage effect. REGISTERED inference for H6.

    WHY THIS REPLACES THE CLUSTER-ROBUST t-STATISTIC.

    The `same_family` dummy is switched on by a handful of specific pairs. The
    OLS above clusters by pair, so with k within-family pairs that coefficient's
    variance is estimated from k clusters. At k = 1 the standard error is not a
    standard error at all: on synthetic data with NO family structure whatsoever,
    the clustered t-statistic came back at +7.06 and declared the lineage effect
    real. That is a false positive produced by the inference, not by the data.

    The permutation test conditions on the observed correlations and re-randomises
    which models are labelled as sharing a family, holding family sizes fixed. It
    makes no asymptotic claim, and its resolution is bounded honestly by the
    number of distinct labelings:

        1 within-family pair  (7 models, 21 pairs)  -> min achievable p = 1/21 = 0.048
        3 within-family pairs (9 models, 36 pairs)  -> min achievable p < 0.001

    That bound is why the panel carries three within-family pairs rather than one.
    """
    e = np.asarray(errors, dtype=float)
    keys = list(model_keys)
    spec = panel_by_key()
    families_observed = [spec[k].family if k in spec else k for k in keys]

    blocks = (
        np.asarray(block_index, dtype=int)
        if block_index is not None
        else np.zeros(e.shape[0], dtype=int)
    )

    # Pairwise correlations are computed ONCE; only the labels are permuted.
    rho: List[float] = []
    idx_i: List[int] = []
    idx_j: List[int] = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            for b in np.unique(blocks):
                rows = blocks == b
                if int(rows.sum()) < min_overlap:
                    continue
                r = mean_pairwise_correlation(e[rows][:, [i, j]], min_overlap=min_overlap)
                if np.isfinite(r):
                    rho.append(r)
                    idx_i.append(i)
                    idx_j.append(j)

    rho_arr = np.asarray(rho, dtype=float)
    ii, jj = np.asarray(idx_i), np.asarray(idx_j)
    if rho_arr.size == 0:
        return {"observed": float("nan"), "p_value": float("nan"), "n_permutations": 0}

    def _gap(labels: Sequence[str]) -> float:
        labels = list(labels)
        same = np.asarray([labels[a] == labels[b] for a, b in zip(ii, jj)], dtype=bool)
        if not same.any() or same.all():
            return float("nan")
        return float(np.mean(rho_arr[same]) - np.mean(rho_arr[~same]))

    observed = _gap(families_observed)

    rng = np.random.default_rng(seed)
    null: List[float] = []
    for _ in range(n_permutations):
        value = _gap(list(rng.permutation(families_observed)))
        if np.isfinite(value):
            null.append(value)

    null_arr = np.asarray(null, dtype=float)
    if null_arr.size == 0 or not np.isfinite(observed):
        return {"observed": float(observed), "p_value": float("nan"), "n_permutations": 0}

    # One-sided: the hypothesis is that same-family pairs correlate MORE.
    p = float((1 + np.sum(null_arr >= observed)) / (1 + null_arr.size))
    return {
        "observed": float(observed),
        "p_value": p,
        "null_mean": float(np.mean(null_arr)),
        "null_sd": float(np.std(null_arr)),
        "n_permutations": int(null_arr.size),
        "within_family_pairs": int(
            sum(1 for a, b in zip(ii, jj) if families_observed[a] == families_observed[b])
        ),
    }


def horizon_strata(state: Sequence[Dict]) -> Dict[str, np.ndarray]:
    """Row indices per registered horizon band (§5.4b).

    Primary estimates are reported within band as well as pooled, so that the
    eligible pool's drift toward short horizons as the freeze approaches cannot
    be mistaken for a state effect.
    """
    out: Dict[str, List[int]] = {label: [] for label, _, _ in HORIZON_BANDS}
    for i, row in enumerate(state):
        value = row.get("days_out")
        if not isinstance(value, (int, float)):
            continue
        for label, low, high in HORIZON_BANDS:
            if low <= float(value) <= high:
                out[label].append(i)
                break
    return {k: np.asarray(v, dtype=int) for k, v in out.items()}


# ---------------------------------------------------------------------------
# H2 — SHARED-PRIOR MECHANISM
#
# H2 registered two legs. Only one of them had a method, which is the same
# defect that H6 had: a registered analysis nobody has written is a promise, not
# a hypothesis. Resolved by implementing the tractable leg and demoting the other.
#
#   KEPT, CONFIRMATORY -- base-rate convergence. If models fall back on absorbed
#     priors when evidence is weak, the panel's judgement should drift toward the
#     category base rate as ambiguity rises. This is measurable from the forecasts
#     alone: no text, no embeddings, no judgement calls from us.
#
#   DEMOTED TO EXPLORATORY -- cross-model rationale similarity. Measuring it
#     honestly needs sentence embeddings and a validation study of its own, and
#     the rationales we collect are capped at 25 words, which is thin evidence for
#     a confirmatory claim. Reported as exploratory and labelled as such.
# ---------------------------------------------------------------------------


def base_rate_convergence(
    forecasts: np.ndarray,
    outcomes: np.ndarray,
    ambiguity: Sequence[float],
    n_terciles: int = 3,
) -> Dict[str, float]:
    """Does the panel drift toward the base rate as questions get more ambiguous?

    Returns the mean absolute distance between the panel median forecast and the
    sample base rate, by ambiguity tercile. H2 predicts this SHRINKS with
    ambiguity: under weak evidence the panel stops discriminating between
    questions and reverts to what it absorbed in training.
    """
    f = np.asarray(forecasts, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    a = np.asarray(list(ambiguity), dtype=float)

    usable = np.isfinite(a) & np.any(~np.isnan(f), axis=1)
    if int(usable.sum()) < 3 * n_terciles:
        return {"estimable": 0.0}

    f, y, a = f[usable], y[usable], a[usable]
    base = float(np.nanmean(y))
    with np.errstate(invalid="ignore"):
        median = np.nanmedian(f, axis=1)
    distance = np.abs(median - base)

    cuts = np.quantile(a, np.linspace(0, 1, n_terciles + 1)[1:-1])
    bucket = np.digitize(a, cuts)

    out: Dict[str, float] = {"estimable": 1.0, "base_rate": base}
    means = []
    for b in range(n_terciles):
        rows = bucket == b
        value = float(np.mean(distance[rows])) if rows.any() else float("nan")
        out[f"tercile_{b}_distance"] = value
        out[f"tercile_{b}_n"] = float(rows.sum())
        means.append(value)
    if np.all(np.isfinite(means)):
        # Negative => the panel converges on the base rate as ambiguity rises,
        # which is the direction H2 predicts.
        out["high_minus_low"] = float(means[-1] - means[0])
    return out


__all__ += ["base_rate_convergence"]

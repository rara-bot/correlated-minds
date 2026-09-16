"""H6 -- lineage, not capability. The registered confound control.

PREREGISTRATION.md 4 registers a regression of pairwise error correlation on (a) a
`same_family` indicator, (b) the pair's mean Brier skill score and (c) the absolute
difference in the pair's Brier skill, with inference "by exact permutation over
family labels (family sizes held fixed), not by the cluster-robust t-statistic"
(3.1). The lineage claim needs the same-family gap to survive with the capability
terms in. Also reported: correlation within accuracy-matched pairs from different
families against the same family. FALSIFIED IF the `same_family` coefficient is
not distinguishable from zero once the capability terms are included; the
correlation is then a capability phenomenon and H3 is read accordingly. Fixed in
deviation 20, while the driver has only run on permuted outcomes:

  pairs        every pair of surviving primary models with a defined error
               correlation (at least three task-days both answered, 5.1), over
               every task-day of the primary panel after the registered exclusions
  skill        `metrics.brier_skill`: each model's Brier score against the
               climatology of the task-days it answered, the base rate taken over
               every task-day
  fit          ordinary least squares of the pair correlation on an intercept and
               the three terms; the coefficient on `same_family` is the statistic
  permutation  every distinct partition of the models into groups of the observed
               family sizes (`stats.family_partitions`: 1260 at the nine, 420 at
               eight when a single-model family is gone). The indicator is rebuilt
               and the model refitted under each, the capability terms unchanged.
               Two-sided p: the share of partitions whose |coefficient| is at least
               the observed one. The observed labeling is among them, so p is never
               below 1 / partitions
  verdict      lineage if p < 0.05 with a positive coefficient, against lineage if
               p < 0.05 with a negative one, falsified otherwise. The same test
               without the capability terms is reported beside it, so the part of
               the gap they absorb can be seen
  matched      for each same-family pair, the cross-family pair nearest to it in
               (mean skill, |skill difference|), Euclidean, the first on a tie,
               repeats allowed; the same-family mean correlation beside that of the
               matches. Descriptive: no test
"""

import math
from itertools import combinations
from pathlib import Path
from typing import Dict, Sequence

import numpy as np

from . import h1
from .analysis import _permute_outcomes, apply_registered_exclusions
from .config import TASKS_PATH, panel_by_key
from .metrics import brier_skill
from .panel import Panel, load_panel
from .stats import family_partitions, pair_correlation

ALPHA = 0.05


def pair_table(panel: Panel) -> Dict[str, object]:
    """Every estimable pair: its correlation, mean skill and skill gap."""
    skill = brier_skill(panel.forecasts, panel.outcomes)["skill"]
    pairs, rho, mean_skill, gap = [], [], [], []
    for i, j in combinations(range(panel.n_models), 2):
        r = pair_correlation(panel.errors, i, j)
        if np.isfinite(r) and np.isfinite(skill[i]) and np.isfinite(skill[j]):
            pairs.append((i, j))
            rho.append(r)
            mean_skill.append((skill[i] + skill[j]) / 2.0)
            gap.append(abs(skill[i] - skill[j]))
    return {"pairs": pairs, "rho": np.array(rho), "mean_skill": np.array(mean_skill),
            "skill_gap": np.array(gap), "skill": skill}


def same_family_coefficient(table: Dict[str, object], groups: Sequence[object],
                            capability: bool = True) -> float:
    """OLS coefficient on `same_family` under a labeling; NaN if the fit is not identified."""
    y = table["rho"]
    same = np.array([1.0 if groups[i] == groups[j] else 0.0 for i, j in table["pairs"]])
    columns = [np.ones(len(same)), same]
    if capability:
        columns += [table["mean_skill"], table["skill_gap"]]
    X = np.column_stack(columns) if len(same) else np.zeros((0, len(columns)))
    if X.shape[0] <= X.shape[1] or np.linalg.matrix_rank(X) < X.shape[1]:
        return math.nan
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(beta[1])


def permutation_test(table: Dict[str, object], labels: Sequence[str],
                     capability: bool = True) -> Dict[str, object]:
    observed = same_family_coefficient(table, labels, capability)
    partitions = family_partitions(labels)
    out: Dict[str, object] = {"coefficient": observed, "partitions": len(partitions),
                              "smallest_p": 1.0 / len(partitions) if partitions else None,
                              "p_two_sided": None}
    if not np.isfinite(observed):
        return out
    values = np.array([same_family_coefficient(table, p, capability) for p in partitions])
    defined = values[np.isfinite(values)]
    out["undefined_partitions"] = int(values.size - defined.size)
    out["p_two_sided"] = float(np.mean(np.abs(defined) >= abs(observed) - 1e-12))
    return out


def matched_pairs(table: Dict[str, object], labels: Sequence[str],
                  keys: Sequence[str]) -> Dict[str, object]:
    pairs = table["pairs"]
    same = [k for k, (i, j) in enumerate(pairs) if labels[i] == labels[j]]
    cross = [k for k, (i, j) in enumerate(pairs) if labels[i] != labels[j]]
    if not same or not cross:
        return {"why_not": f"{len(same)} same-family and {len(cross)} cross-family pair(s)"}
    position = np.column_stack([table["mean_skill"], table["skill_gap"]])
    matches = [cross[int(np.argmin(np.linalg.norm(position[cross] - position[k], axis=1)))]
               for k in same]

    def name(k: int) -> str:
        return f"{keys[pairs[k][0]]}~{keys[pairs[k][1]]}"

    return {"same_family_rho": float(np.mean(table["rho"][same])),
            "matched_cross_family_rho": float(np.mean(table["rho"][matches])),
            "matches": {name(k): name(c) for k, c in zip(same, matches)}}


def evaluate(panel: Panel, family: Dict[str, str]) -> Dict[str, object]:
    """H6 on a prepared panel whose columns are all primary models."""
    labels = [family[k] for k in panel.model_keys]
    table = pair_table(panel)
    out: Dict[str, object] = {
        "pairs": len(table["pairs"]),
        "pairs_possible": panel.n_models * (panel.n_models - 1) // 2,
        "same_family_pairs": sum(labels[i] == labels[j] for i, j in table["pairs"]),
        "brier_skill_by_model": dict(zip(panel.model_keys, table["skill"].tolist())),
    }
    out.update(h1.sample_size(panel))
    out["with_capability_terms"] = permutation_test(table, labels, capability=True)
    out["same_family_only"] = permutation_test(table, labels, capability=False)
    out["accuracy_matched_pairs"] = matched_pairs(table, labels, panel.model_keys)
    p = out["with_capability_terms"]["p_two_sided"]
    coefficient = out["with_capability_terms"]["coefficient"]
    if p is None:
        out["verdict"] = "untested"
    elif p < ALPHA and coefficient > 0:
        out["verdict"] = "supports H6: lineage, over and above capability"
    elif p < ALPHA:
        out["verdict"] = "against H6: same-family pairs are less correlated than capability predicts"
    else:
        out["verdict"] = ("falsified: a capability phenomenon, not a lineage one; "
                          "H3 is read accordingly")
    return out


def run(blind: bool = True, seed: int = 0, tasks_path: Path = TASKS_PATH,
        **load_kwargs) -> Dict[str, object]:
    """Load, exclude, (permute), and test H6 as registered."""
    panel = load_panel(tasks_path=tasks_path, **load_kwargs)
    panel, exclusions = apply_registered_exclusions(panel)
    if blind and panel.n_tasks:
        panel = _permute_outcomes(panel, seed)
    family = {k: spec.family for k, spec in panel_by_key().items()}
    result = evaluate(panel, family)
    result.update(blind=blind, models=list(panel.model_keys),
                  models_excluded=exclusions.get("models_below_coverage_floor", {}))
    return result

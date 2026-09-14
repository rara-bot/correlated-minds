"""H3 -- the diversification illusion.

PREREGISTRATION.md 4 registers "N_eff for (a) one model under 5 prompt variants,
(b) the three within-family pairs, (c) family-matched cross-family pairs -- matched
on panel size, with permutation inference", FALSIFIED IF "the intra-model and
cross-family N_eff intervals overlap". The variants are collected from 2026-09-14
(deviation 14). What the plan leaves open is fixed in deviation 20, while the
driver has only run on permuted outcomes:

  panel size   two, in every arm: N_eff = 2 / (1 + rho_bar), rho_bar the mean error
               correlation over the arm's pairs
  (a)          the C(5,2) = 10 pairs of `gpt_mid`'s five prompt variants, variant 0
               being its primary answer
  (b)          the pairs of surviving primary models that share a family
  (c)          the pairs of surviving primary models from different families
               when both families still have two members: the cross-family pairs
               among the models (b) is built from, 12 at the registered nine
  task-days    the primary panel's after the registered exclusions, asked on or
               after config.H3_VARIANT_START; all three arms on the same ones
  intervals    5.2's, all three arms from one resample. (a) and (c) are separated
               only if neither their question-clustered intervals nor their
               settlement-clustered ones overlap
  direction    H3 predicts (a) below (c); separated the other way counts against
               it; overlap falsifies it, as registered
  permutation  exact, over family labels with family sizes held fixed
               (`stats.family_partitions`, 1260 labelings at the nine): the
               statistic is rho_bar(b) - rho_bar(c) under each labeling, and the
               one-sided p is the share of labelings at least as large as the
               observed one
"""

import math
import warnings
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import h1
from .analysis import GOVERNING, N_BOOT, _permute_outcomes, apply_registered_exclusions, intervals, resampled
from .config import (
    H3_VARIANT_MODEL,
    H3_VARIANT_START,
    H3_VARIANTS,
    OBS_PATH,
    RESOLUTIONS_PATH,
    TASKS_PATH,
    primary_panel,
)
from .panel import Panel, _rows, load_panel
from .stats import family_partitions, n_eff, pair_correlation

ARMS = ("intra_model", "within_family", "cross_family_matched")
SETTLEMENT = "event_clustered_settlement"
VERDICTS = {
    None: "untested",
    -1: "supports H3",
    1: "against H3: the model's prompt variants buy more independence than cross-family pairs",
    0: "falsified: the intra-model and cross-family intervals overlap",
}


def variant_key(variant: int, model: str = H3_VARIANT_MODEL) -> str:
    return f"{model}@v{variant}"


def attach_variants(panel: Panel, obs_path: Path = OBS_PATH, resolutions_path: Path = RESOLUTIONS_PATH,
                    tasks_path: Path = TASKS_PATH, model: str = H3_VARIANT_MODEL,
                    variants: int = H3_VARIANTS) -> Panel:
    """The panel with one more column per prompt variant of `model`, on the panel's own rows.

    Each column is read exactly as `load_panel` reads variant 0 -- same arm, mock
    and error filters, last row wins -- so the variant-0 column repeats the model's
    primary one. Rows and outcomes stay the panel's, so attaching before outcomes
    are permuted keeps every column on the one permutation.
    """
    extra = np.full((panel.n_tasks, variants), np.nan)
    row = {t: i for i, t in enumerate(panel.task_ids)}
    for v in range(variants):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # a variant not yet collected admits nothing
            one = load_panel(obs_path=obs_path, resolutions_path=resolutions_path, tasks_path=tasks_path,
                             model_keys=[model], prompt_variant=v, min_models_per_task=1)
        for task, value in zip(one.task_ids, one.forecasts[:, 0]):
            if task in row:
                extra[row[task], v] = value
    forecasts = np.hstack([panel.forecasts, extra])
    return Panel(
        forecasts=forecasts,
        outcomes=panel.outcomes,
        errors=forecasts - panel.outcomes[:, None],
        task_ids=list(panel.task_ids),
        model_keys=list(panel.model_keys) + [variant_key(v, model) for v in range(variants)],
        market_implied=panel.market_implied,
        state=list(panel.state),
        question_ids=list(panel.question_ids),
        asked_on=list(panel.asked_on),
    )


def arm_pairs(model_keys: Sequence[str], family: Dict[str, str], model: str = H3_VARIANT_MODEL,
              variants: int = H3_VARIANTS) -> Dict[str, List[Tuple[int, int]]]:
    """The column pairs of each arm. Columns not in `family` are not primary models."""
    index = {k: i for i, k in enumerate(model_keys)}
    members = [k for k in model_keys if k in family]
    size = Counter(family[k] for k in members)
    variant_columns = [index[variant_key(v, model)] for v in range(variants)
                       if variant_key(v, model) in index]
    out: Dict[str, List[Tuple[int, int]]] = {
        "intra_model": list(combinations(variant_columns, 2)), "within_family": [],
        "cross_family_matched": []}
    for a, b in combinations(members, 2):
        if family[a] == family[b]:
            out["within_family"].append((index[a], index[b]))
        elif size[family[a]] >= 2 and size[family[b]] >= 2:
            out["cross_family_matched"].append((index[a], index[b]))
    return out


def arm_rho(errors: np.ndarray, pairs: Sequence[Tuple[int, int]]) -> float:
    values = [r for r in (pair_correlation(errors, i, j) for i, j in pairs) if np.isfinite(r)]
    return float(np.mean(values)) if values else math.nan


def n_eff_of_two(rho: float) -> float:
    return n_eff(rho, 2) if np.isfinite(rho) else math.nan


def separation(first: Optional[Dict], second: Optional[Dict]) -> Optional[int]:
    """-1 if the first interval lies wholly below the second, +1 wholly above, 0 if they overlap."""
    bounds = [(first or {}).get("lo"), (first or {}).get("hi"),
              (second or {}).get("lo"), (second or {}).get("hi")]
    if any(b is None for b in bounds):
        return None
    lo_a, hi_a, lo_b, hi_b = bounds
    return -1 if hi_a < lo_b else (1 if lo_a > hi_b else 0)


def family_permutation(errors: np.ndarray, model_keys: Sequence[str],
                       family: Dict[str, str]) -> Dict[str, object]:
    """Exact permutation over family labels: rho_bar(within) - rho_bar(matched cross), one-sided."""
    members = [k for k in model_keys if k in family]
    labels = [family[k] for k in members]
    column = [list(model_keys).index(k) for k in members]
    rho = {(a, b): pair_correlation(errors, column[a], column[b])
           for a, b in combinations(range(len(members)), 2)}

    def statistic(groups: Sequence[object]) -> float:
        size = Counter(groups)
        within = [r for (a, b), r in rho.items() if groups[a] == groups[b] and np.isfinite(r)]
        cross = [r for (a, b), r in rho.items() if groups[a] != groups[b] and np.isfinite(r)
                 and size[groups[a]] >= 2 and size[groups[b]] >= 2]
        return float(np.mean(within) - np.mean(cross)) if within and cross else math.nan

    partitions = family_partitions(labels)
    observed = statistic(labels)
    out: Dict[str, object] = {"labelings": len(partitions), "observed": observed,
                              "smallest_p": 1.0 / len(partitions) if partitions else None,
                              "p_one_sided": None}
    if not np.isfinite(observed):
        return out
    values = np.array([statistic(p) for p in partitions])
    defined = values[np.isfinite(values)]
    out["undefined_labelings"] = int(values.size - defined.size)
    out["p_one_sided"] = float(np.mean(defined >= observed - 1e-12))
    return out


def evaluate(panel: Panel, family: Dict[str, str], n_boot: int = N_BOOT, seed: int = 0,
             model: str = H3_VARIANT_MODEL, variants: int = H3_VARIANTS) -> Dict[str, object]:
    """H3 on a prepared panel: variant columns attached, rows restricted to the variant days."""
    pairs = arm_pairs(panel.model_keys, family, model, variants)
    out: Dict[str, object] = {"task_days": panel.n_tasks,
                              "pairs": {arm: len(p) for arm, p in pairs.items()}}
    out.update(h1.sample_size(panel))
    empty = [arm for arm in ARMS if not pairs[arm]]
    if panel.n_tasks < 3 or empty:
        out["why_not"] = (f"{panel.n_tasks} task-day(s) with prompt variants" if panel.n_tasks < 3
                          else f"no pairs in {', '.join(empty)}")
        out["verdict"] = VERDICTS[None]
        return out

    out["rho_bar"] = {arm: arm_rho(panel.errors, pairs[arm]) for arm in ARMS}
    out["n_eff"] = {arm: n_eff_of_two(out["rho_bar"][arm]) for arm in ARMS}
    draws = resampled(panel, lambda idx: [n_eff_of_two(arm_rho(panel.errors[idx], pairs[arm]))
                                          for arm in ARMS], n_boot, seed)
    out["intervals"] = {arm: intervals(draws, k) for k, arm in enumerate(ARMS)}
    registered = separation(out["intervals"]["intra_model"].get(GOVERNING),
                            out["intervals"]["cross_family_matched"].get(GOVERNING))
    settlement = separation(out["intervals"]["intra_model"].get(SETTLEMENT),
                            out["intervals"]["cross_family_matched"].get(SETTLEMENT))
    claimed = None if registered is None or settlement is None else (
        registered if registered == settlement else 0)
    out["separation"] = {"registered": registered, "settlement": settlement, "claimed": claimed}
    out["permutation_within_vs_cross"] = family_permutation(panel.errors, panel.model_keys, family)
    out["verdict"] = VERDICTS[claimed]
    return out


def run(blind: bool = True, seed: int = 0, n_boot: int = N_BOOT, obs_path: Path = OBS_PATH,
        resolutions_path: Path = RESOLUTIONS_PATH, tasks_path: Path = TASKS_PATH,
        start: str = H3_VARIANT_START, **load_kwargs) -> Dict[str, object]:
    """Load, exclude, attach the variants, (permute), and test H3 as registered."""
    panel = load_panel(obs_path=obs_path, resolutions_path=resolutions_path, tasks_path=tasks_path,
                       **load_kwargs)
    panel, exclusions = apply_registered_exclusions(panel)
    panel = attach_variants(panel, obs_path, resolutions_path, tasks_path)
    if blind and panel.n_tasks:
        panel = _permute_outcomes(panel, seed)
    family = {m.key: m.family for m in primary_panel()}
    rows = [i for i, day in enumerate(panel.asked_on) if day and day >= start]
    result = evaluate(_rows(panel, rows), family, n_boot, seed)
    result.update(blind=blind, variants_from=start,
                  models=[k for k in panel.model_keys if k in family],
                  models_excluded=exclusions.get("models_below_coverage_floor", {}))
    return result

"""H4 -- the human comparison. Confirmatory secondary.

PREREGISTRATION.md 4 registers that on matched questions and matched panel size AI
diversification headroom is smaller than human headroom, benefit(humans) -
benefit(AI) > 0, against SPF RECESS (2.3), on Type A tasks only, with human panels
subsampled to the AI panel's size over 500 draws, both panels' Brier scores always
reported, and the comparison at matched accuracy as the confirmatory form --
reported as confounded where the two accuracies do not overlap. 5.5 makes the
bounded difference the headline and the headroom ratio a secondary; 7 calls the
comparison uninformative if humans have negligible headroom too. Deviation 17 (6)
matches the humans to the surviving M, and deviation 19 pins the human inputs.
The rest is fixed in deviation 20, while the AI side has only been computed on
permuted outcomes. The human side is public, registered in 2.3, and never blinded.

  benefit     `metrics.mse_benefit`: 1 - MSE(panel mean) / mean_i MSE_i, floored at
              zero, the "fraction of squared error removed by averaging the panel"
              5.5 names, over the task-days or rounds at least two members answered
  AI panel    the Type A task-days of the surviving primary panel; M its columns
  human draw  M forecasters drawn without replacement from the RECESS panel at one
              horizon (2000 onward, as in 2.3), 500 draws from seed 0. With every
              forecaster eligible these are the draws behind 2.3's table
  horizons    all five. H4 cites the benchmark as a band across horizons 1-5, so
              AI headroom is smaller than human headroom only if it is smaller at
              each of them, and no single horizon is chosen
  accuracy    Brier skill against climatology (`metrics.brier_skill`). GDP declines
              in about 13% of RECESS quarters, and the AI questions' base rate is
              set by what they ask, so raw Brier scores are reported and never matched
  stratum     the horizon's forecasters ranked by skill and split into three groups
              of equal count; the matched stratum is the one whose mean skill is
              nearest the AI panel's mean skill. Accuracy overlaps if that mean lies
              within the stratum's range, and the horizon is CONFOUNDED if not. A
              stratum of fewer than M forecasters leaves the horizon untested
  interval    each AI bootstrap draw, under each of 5.2's resamplings, set against
              the human draw of the same index, cycling through the 500
  negligible  a horizon is UNINFORMATIVE (7) when the matched human panels' mean
              Pearson headroom is below NEGLIGIBLE_HEADROOM. Section 2 calls nowcast
              headroom of 0.000-0.004 unmeasurable and 0.08-0.19 measurable; 0.01 is
              above every value it calls saturated and an order of magnitude below
              the smallest it calls measurable. (The first definition, a benefit
              whose 2.5th percentile is zero, is met at every RECESS horizon and in
              every stratum, because the benefit is floored at zero)
  verdict     AI headroom smaller only if every horizon is informative, unconfounded
              and positive under both the question- and settlement-clustered
              intervals; the reverse, reported with equal standing, only if every
              horizon is negative the same way; otherwise not established, with
              each horizon's reason
  secondary   Pearson headroom on both sides and their ratio, human over AI, with
              its intervals and the count of draws where it is undefined (5.5)
"""

import math
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import h1
from .analysis import (
    N_BOOT,
    _permute_outcomes,
    apply_registered_exclusions,
    claimed_sign,
    intervals,
    percentile_interval,
    resampled,
)
from .config import TASKS_PATH
from .metrics import brier_skill, mse_benefit
from .panel import Panel, _rows, load_panel
from .report import kind_of
from .sources import spf
from .stats import mean_pairwise_correlation, n_eff

HORIZONS = (1, 2, 3, 4, 5)
HUMAN_DRAWS = 500
STRATA = 3
HUMAN_MIN_OVERLAP = 6    # `spf._matched`, which produced the table in 2.3
NEGLIGIBLE_HEADROOM = 0.01


def _mean(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    return float(np.mean(values[np.isfinite(values)])) if np.isfinite(values).any() else math.nan


def headroom(errors: np.ndarray, m: int, min_overlap: int = 3) -> float:
    if errors.shape[0] < 2:
        return math.nan
    rho = mean_pairwise_correlation(errors, min_overlap=min_overlap)
    return n_eff(rho, m) - 1.0 if np.isfinite(rho) else math.nan


def human_draws(errors: np.ndarray, members: Sequence[int], m: int, n_draws: int = HUMAN_DRAWS,
                seed: int = 0) -> Optional[Dict[str, np.ndarray]]:
    """Benefit and Pearson headroom of `n_draws` random panels of M forecasters from `members`."""
    members = np.asarray(members, dtype=int)
    if members.size < m:
        return None
    rng = np.random.default_rng(seed)
    benefit, room = np.full(n_draws, np.nan), np.full(n_draws, np.nan)
    with warnings.catch_warnings():
        # A drawn forecaster can miss every round the others answered; its MSE is
        # then undefined and left out of the mean, which numpy announces each time.
        warnings.simplefilter("ignore", RuntimeWarning)
        for k in range(n_draws):
            picks = rng.choice(members, size=m, replace=False)
            benefit[k] = mse_benefit(errors[:, picks])
            room[k] = headroom(errors[:, picks], m, HUMAN_MIN_OVERLAP)
    return {"benefit": benefit, "headroom": room}


def strata(skill: np.ndarray, n: int = STRATA) -> List[np.ndarray]:
    """Forecaster columns ranked by skill, least skilled first, in n groups of equal count."""
    skill = np.asarray(skill, dtype=float)
    defined = np.nonzero(np.isfinite(skill))[0]
    order = defined[np.argsort(skill[defined], kind="stable")]
    return list(np.array_split(order, n))


def matched_stratum(skill: np.ndarray, target: float) -> Dict[str, object]:
    """The stratum whose mean skill is nearest `target`, and whether `target` lies in its range."""
    skill = np.asarray(skill, dtype=float)
    groups = strata(skill)
    means = [float(np.mean(skill[g])) if g.size else math.nan for g in groups]
    candidates = [k for k, x in enumerate(means) if np.isfinite(x)]
    if not candidates or not np.isfinite(target):
        return {"members": np.zeros(0, dtype=int), "accuracy_overlaps": False,
                "why_not": "a skill is undefined on one side"}
    k = min(candidates, key=lambda j: abs(means[j] - target))
    lo, hi = float(np.min(skill[groups[k]])), float(np.max(skill[groups[k]]))
    return {"members": groups[k], "stratum": k, "strata": len(groups),
            "forecasters": int(groups[k].size), "mean_skill": means[k],
            "skill_range": [lo, hi], "accuracy_overlaps": bool(lo <= target <= hi)}


def comparison(ai_point: Dict[str, float], ai: Dict[str, np.ndarray],
               human: Dict[str, np.ndarray]) -> Dict[str, object]:
    """benefit(humans) - benefit(AI), the headline, and the ratio of headroom, the secondary."""
    difference: Dict[str, np.ndarray] = {}
    ratio: Dict[str, np.ndarray] = {}
    for label, draws in ai.items():
        draws = np.asarray(draws, dtype=float)
        if draws.ndim != 2 or not draws.shape[0]:
            continue
        k = np.arange(draws.shape[0]) % human["benefit"].size
        difference[label] = human["benefit"][k] - draws[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio[label] = np.where(draws[:, 1] > 0, human["headroom"][k] / draws[:, 1], np.nan)
    benefit_humans = _mean(human["benefit"])
    headroom_humans = _mean(human["headroom"])
    spread = percentile_interval(human["benefit"])
    out: Dict[str, object] = {
        "benefit_humans": benefit_humans,
        "benefit_humans_range": spread,
        "benefit_ai": ai_point["benefit"],
        "difference": benefit_humans - ai_point["benefit"],
        "difference_intervals": intervals(difference),
        "headroom_humans": headroom_humans,
        "headroom_ai": ai_point["headroom"],
        "ratio": headroom_humans / ai_point["headroom"] if ai_point["headroom"] > 0 else math.nan,
        "ratio_intervals": intervals(ratio),
        "uninformative": not headroom_humans >= NEGLIGIBLE_HEADROOM,
    }
    out["claimed_sign"] = claimed_sign(out["difference_intervals"])
    return out


def verdict(horizons: Dict[int, Dict[str, object]]) -> Dict[str, object]:
    """The registered claim over every horizon, with each horizon's reason when it fails."""
    reasons: Dict[int, str] = {}
    signs: Dict[int, int] = {}
    for h, row in horizons.items():
        matched = row.get("matched_accuracy") or {}
        if "claimed_sign" not in matched:
            reasons[h] = "untested: " + str(matched.get("why_not", "no comparison"))
        elif not matched.get("accuracy_overlaps"):
            reasons[h] = "confounded: the AI panel's skill lies outside the matched human stratum"
        elif matched.get("uninformative"):
            reasons[h] = "uninformative: the matched human panels have negligible headroom (7)"
        elif matched["claimed_sign"] is None:
            reasons[h] = "untested: the interval is undefined"
        else:
            signs[h] = int(matched["claimed_sign"])
    if horizons and not reasons and all(s == 1 for s in signs.values()):
        text = "supports H4: AI headroom is smaller than human headroom at every horizon"
    elif horizons and not reasons and all(s == -1 for s in signs.values()):
        text = "reverse of H4: AI headroom is larger than human headroom at every horizon"
    else:
        text = "not established"
    return {"verdict": text, "signs_by_horizon": signs, "reasons_by_horizon": reasons}


def evaluate(panel: Panel, humans: Dict[int, "spf.HumanErrors"], n_boot: int = N_BOOT,
             seed: int = 0, n_draws: Optional[int] = None) -> Dict[str, object]:
    """H4 on a prepared Type A panel, against each horizon's RECESS error matrix."""
    n_draws = n_draws or HUMAN_DRAWS
    m = panel.n_models
    out: Dict[str, object] = {"task_days": panel.n_tasks, "m": m, "horizons": {}}
    out.update(h1.sample_size(panel))
    if panel.n_tasks < 3 or m < 2:
        out.update(why_not=f"{panel.n_tasks} Type A task-day(s), M = {m}", verdict="not established")
        return out

    skill = brier_skill(panel.forecasts, panel.outcomes)
    ai_skill = _mean(skill["skill"])
    ai_point = {"benefit": mse_benefit(panel.errors), "headroom": headroom(panel.errors, m)}
    ai = resampled(panel, lambda idx: [mse_benefit(panel.errors[idx]), headroom(panel.errors[idx], m)],
                   n_boot, seed)
    out["ai"] = dict(ai_point, base_rate=skill["base_rate"], brier_mean=_mean(skill["brier"]),
                     brier_skill_mean=ai_skill,
                     brier_skill_by_model=dict(zip(panel.model_keys, skill["skill"].tolist())))

    for h, human in sorted(humans.items()):
        human_skill = brier_skill(human.forecasts, human.outcomes)
        row: Dict[str, object] = {
            "rounds": int(human.errors.shape[0]), "forecasters": int(human.errors.shape[1]),
            "base_rate": human_skill["base_rate"], "brier_mean": _mean(human_skill["brier"]),
            "brier_skill_mean": _mean(human_skill["skill"])}
        everyone = human_draws(human.errors, np.arange(human.errors.shape[1]), m, n_draws, seed)
        row["all_forecasters"] = (comparison(ai_point, ai, everyone) if everyone is not None
                                  else {"why_not": f"fewer than M = {m} forecasters"})
        stratum = matched_stratum(human_skill["skill"], ai_skill)
        members = stratum.pop("members")
        drawn = human_draws(human.errors, members, m, n_draws, seed)
        row["matched_accuracy"] = dict(stratum, **(
            comparison(ai_point, ai, drawn) if drawn is not None else
            {"why_not": stratum.get("why_not")
             or f"the matched stratum holds {len(members)} forecaster(s), fewer than M = {m}"}))
        out["horizons"][h] = row
    out.update(verdict(out["horizons"]))
    return out


def run(blind: bool = True, seed: int = 0, n_boot: int = N_BOOT,
        horizons: Optional[Sequence[int]] = None, n_draws: Optional[int] = None,
        tasks_path: Path = TASKS_PATH, spf_source: str = "pinned", **load_kwargs) -> Dict[str, object]:
    """Load, exclude, (permute), keep Type A, and test H4 against every RECESS horizon."""
    panel = load_panel(tasks_path=tasks_path, **load_kwargs)
    panel, exclusions = apply_registered_exclusions(panel)
    if blind and panel.n_tasks:
        panel = _permute_outcomes(panel, seed)
    type_a = _rows(panel, [i for i, s in enumerate(panel.state) if kind_of(s) == "event"])
    humans = {h: spf.human_errors(spf.RECESS_SHEET, h, source=spf_source)
              for h in (horizons or HORIZONS)}
    result = evaluate(type_a, humans, n_boot, seed, n_draws)
    result.update(blind=blind, models=list(panel.model_keys),
                  models_excluded=exclusions.get("models_below_coverage_floor", {}))
    return result

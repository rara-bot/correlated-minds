"""Assemble stored observations into the matrices the estimators consume.

This is the join between collection and analysis: observations.jsonl (one row
per model per task) plus resolutions.jsonl (one row per settled task) become a
(n_tasks x n_models) forecast matrix, an aligned outcome vector, and an error
matrix.

Two decisions here have real consequences for the result, so they are explicit
rather than incidental:

  MISSING DATA IS KEPT AS NaN, NOT DROPPED. If a model fails on a task we leave
  a hole and let the pairwise estimator handle it. Dropping whole tasks would
  preferentially discard busy market days, since rate limits and timeouts
  cluster exactly when markets are active -- which is where H1 lives.

  ERRORS USE THE BRIER DECOMPOSITION FOR BINARY OUTCOMES. For a binary event the
  natural error is (forecast_probability - outcome). Its square is the Brier
  score, a proper scoring rule, so a forecaster cannot improve their score by
  misreporting their true belief.
"""

import json
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import (
    OBS_PATH,
    PRE_REGISTRATION_ARM,
    PRIMARY_ARM,
    RESOLUTIONS_PATH,
    TASKS_PATH,
    primary_panel,
)
from .sources.edgar import MAX_REPORTING_GAP_DAYS
from .store import JsonlStore


def _is_mock(record: Dict) -> bool:
    """Is this a synthetic observation from `neff.collect --mock`?

    Checked two ways because either alone could be lost in a schema change.
    """
    if str(record.get("provider", "")).lower() == "mock":
        return True
    return str(record.get("model_id_returned", "")).endswith("-mock")


@dataclass
class Panel:
    """A resolved panel ready for analysis."""

    forecasts: np.ndarray          # (n_tasks, n_models), NaN where missing
    outcomes: np.ndarray           # (n_tasks,)
    errors: np.ndarray             # forecasts - outcomes[:, None]
    task_ids: List[str]
    model_keys: List[str]
    market_implied: np.ndarray     # (n_tasks,), NaN where unavailable
    state: List[Dict]              # per-task market state at ask time
    question_ids: List[str]        # stable question identity across days
    asked_on: List[str]            # ISO date the question was put to the panel

    @property
    def n_tasks(self) -> int:
        return int(self.forecasts.shape[0])

    @property
    def n_models(self) -> int:
        return int(self.forecasts.shape[1])

    def coverage(self) -> float:
        """Fraction of (task, model) cells actually filled."""
        total = self.forecasts.size
        return float(np.sum(~np.isnan(self.forecasts)) / total) if total else 0.0

    def subset_by_state(
        self, key: str, low: Optional[float] = None, high: Optional[float] = None
    ) -> "Panel":
        """Tasks whose state variable falls in [low, high] -- the H1 conditional cut."""
        keep = []
        for i, state in enumerate(self.state):
            value = state.get(key)
            if not isinstance(value, (int, float)):
                continue
            if low is not None and value < low:
                continue
            if high is not None and value > high:
                continue
            keep.append(i)

        idx = np.asarray(keep, dtype=int)
        return Panel(
            forecasts=self.forecasts[idx],
            outcomes=self.outcomes[idx],
            errors=self.errors[idx],
            task_ids=[self.task_ids[i] for i in keep],
            model_keys=list(self.model_keys),
            market_implied=self.market_implied[idx],
            state=[self.state[i] for i in keep],
            question_ids=[self.question_ids[i] for i in keep],
            asked_on=[self.asked_on[i] for i in keep],
        )

    def subset_by_models(self, keys: Sequence[str]) -> "Panel":
        """Restrict to named models -- used for the H3 family contrasts."""
        cols = [i for i, k in enumerate(self.model_keys) if k in set(keys)]
        idx = np.asarray(cols, dtype=int)
        return Panel(
            forecasts=self.forecasts[:, idx],
            outcomes=self.outcomes,
            errors=self.errors[:, idx],
            task_ids=list(self.task_ids),
            model_keys=[self.model_keys[i] for i in cols],
            market_implied=self.market_implied,
            state=list(self.state),
            question_ids=list(self.question_ids),
            asked_on=list(self.asked_on),
        )


def load_panel(
    obs_path=OBS_PATH,
    resolutions_path=RESOLUTIONS_PATH,
    tasks_path=TASKS_PATH,
    model_keys: Optional[List[str]] = None,
    prompt_variant: int = 0,
    require_resolved: bool = True,
    min_models_per_task: int = 2,
    include_mock: bool = False,
    arm: Optional[str] = None,
) -> Panel:
    """Build a Panel from the stored record.

    Args:
        require_resolved: keep only tasks with a known outcome. Set False to
            inspect forecasts before anything has settled (useful early on,
            when nothing has resolved yet).
        min_models_per_task: drop tasks answered by too few models to contribute
            any pair.
        include_mock: DEFAULT FALSE, and it should stay that way.

            `neff.collect --mock` writes synthetic observations into the same
            observations.jsonl as real ones. They are labelled -- provider is
            "mock" and model_id_returned ends in "-mock" -- but nothing in the
            ANALYSIS layer respected that label, so a smoke-test run would be
            silently ingested as study data and analysed as though real. A
            pre-collection dry run on 17 Aug 2026 left 140 such rows in the file
            and load_panel built a clean-looking 20-task panel out of them.

            Fabricated forecasts entering a real panel is the worst failure this
            codebase could have, so the filter is on by default and has to be
            switched off deliberately.

        arm: which registered arm to analyse. Defaults to `config.PRIMARY_ARM`.

            FAIL-CLOSED, and deliberately so. A row is admitted only if it
            carries this exact label; a row with a different arm, or with no arm
            at all, is excluded and counted.

            PREREGISTRATION.md 3.5 declares the 21-22 Aug pilot as a separate
            arm, collected before the registration and excluded from every
            primary estimate. That exclusion was previously unenforceable: `arm`
            was recorded only on the cost ledger, never on the task or the
            observation, so `load_panel` had no way to tell 160 real pilot
            forecasts apart from study data and returned them inside the primary
            panel. This is the same defect class that mock data had before
            `include_mock`, in a form that is harder to spot -- the pilot rows
            are real calls to real models, so nothing about them looks wrong.

            The pilot rows predate the label and so carry none, which is exactly
            why the filter refuses unlabelled rows rather than assuming the best.
            The store is append-only, so they are excluded rather than rewritten.
    """
    # PRIMARY panel, not everything collected. Secondary arms (e.g. the frontier
    # model) are collected daily but must not enter the primary analysis: H4
    # matches humans at M = 9 against SPF headroom measured at that panel size.
    # Pass model_keys explicitly to analyse a secondary arm.
    keys = model_keys or [m.key for m in primary_panel()]
    want_arm = PRIMARY_ARM if arm is None else arm
    key_index = {k: i for i, k in enumerate(keys)}

    resolutions: Dict[str, float] = {}
    for record in JsonlStore(resolutions_path).read():
        task_id = record.get("task_id")
        outcome = record.get("outcome")
        if task_id is not None and isinstance(outcome, (int, float)):
            # First resolution wins; later duplicates never overwrite history.
            resolutions.setdefault(str(task_id), float(outcome))

    task_meta: Dict[str, Dict] = {}
    for record in JsonlStore(tasks_path).read():
        task_id = record.get("task_id")
        if task_id is not None:
            task_meta.setdefault(
                str(task_id),
                {
                    "market_implied": record.get("market_implied"),
                    "state": record.get("state") or {},
                    "source_ref": record.get("source_ref") or "",
                    "asked_on": (record.get("state") or {}).get("asked_on") or "",
                },
            )

    # task_id -> model_key -> forecast
    grid: Dict[str, Dict[str, float]] = {}
    n_mock_skipped = 0
    n_other_arm_skipped = 0
    for record in JsonlStore(obs_path).read():
        if int(record.get("prompt_variant", 0)) != prompt_variant:
            continue
        row_arm = str(record.get("arm") or "")
        # A row with no label predates the label, and everything collected before
        # it was the pre-registration pilot -- all 228 pre-registration ledger
        # entries are `arm="pilot"`. So unlabelled rows resolve to the pilot: they
        # can never satisfy the primary arm (the property that matters), but
        # asking for the pilot explicitly still reaches them, which is what
        # PREREGISTRATION.md 3.5 permits for exploratory use. The store is
        # append-only, so they are reinterpreted on read, never rewritten.
        if not row_arm:
            row_arm = PRE_REGISTRATION_ARM
        if row_arm != want_arm:
            n_other_arm_skipped += 1
            continue
        if not include_mock and _is_mock(record):
            n_mock_skipped += 1
            continue
        model_key = record.get("model_key")
        if model_key not in key_index:
            continue
        forecast = record.get("forecast")
        if forecast is None or record.get("error"):
            continue
        task_id = str(record.get("task_id"))
        grid.setdefault(task_id, {})[str(model_key)] = float(forecast)

    # An empty panel with rows on disk is the failure mode this filter could
    # otherwise introduce, so say why rather than returning a silent zero.
    if not grid and (n_other_arm_skipped or n_mock_skipped):
        warnings.warn(
            f"load_panel: no rows admitted -- skipped {n_other_arm_skipped} row(s) "
            f"not labelled arm={want_arm!r} and {n_mock_skipped} mock row(s). "
            "Observations written before the arm label existed carry none and are "
            "excluded by design (PREREGISTRATION.md 3.5).",
            RuntimeWarning,
            stacklevel=2,
        )

    eligible = [
        tid
        for tid, row in grid.items()
        if len(row) >= min_models_per_task
        and (not require_resolved or tid in resolutions)
    ]

    # ORDER MATTERS AND IS NOT COSMETIC.
    #
    # task_id is a SHA-256 hash, so sorting on it puts rows in an order that is
    # random with respect to time. The moving-block bootstrap resamples
    # CONTIGUOUS ROWS to preserve serial dependence -- under hash ordering those
    # "blocks" are unrelated days, so the block bootstrap silently degrades to an
    # ordinary i.i.d. bootstrap and reports intervals that are far too narrow.
    #
    # Measured on an AR(0.9) simulation, T = 300, M = 7:
    #     time-ordered rows : rho = 0.8978, CI [0.8599, 0.9237], width 0.0638
    #     hash-ordered rows : rho = 0.8978, CI [0.8781, 0.9136], width 0.0355
    # i.e. every interval in the paper would have been 44% too narrow.
    #
    # Sorting on (asked_on, question, task) restores true temporal adjacency.
    def _sort_key(tid: str):
        meta = task_meta.get(tid, {})
        return (str(meta.get("asked_on") or ""), str(meta.get("source_ref") or ""), tid)

    task_ids = sorted(eligible, key=_sort_key)

    n_tasks, n_models = len(task_ids), len(keys)
    forecasts = np.full((n_tasks, n_models), np.nan, dtype=float)
    outcomes = np.full(n_tasks, np.nan, dtype=float)
    implied = np.full(n_tasks, np.nan, dtype=float)
    state: List[Dict] = []
    question_ids: List[str] = []
    asked_on: List[str] = []

    for row, task_id in enumerate(task_ids):
        for model_key, value in grid[task_id].items():
            forecasts[row, key_index[model_key]] = value
        if task_id in resolutions:
            outcomes[row] = resolutions[task_id]
        meta = task_meta.get(task_id, {})
        market_value = meta.get("market_implied")
        if isinstance(market_value, (int, float)):
            implied[row] = float(market_value)
        state.append(dict(meta.get("state") or {}))
        question_ids.append(str(meta.get("source_ref") or task_id))
        asked_on.append(str(meta.get("asked_on") or ""))

    errors = forecasts - outcomes[:, None]

    return Panel(
        forecasts=forecasts,
        outcomes=outcomes,
        errors=errors,
        task_ids=task_ids,
        model_keys=keys,
        market_implied=implied,
        state=state,
        question_ids=question_ids,
        asked_on=asked_on,
    )


def apply_settled_question_exclusion(
    panel: Panel, low: float = 0.05, high: float = 0.95
) -> Panel:
    """Drop questions the panel had effectively already decided. REGISTERED (§3.3).

    The rule is defined on the FIRST DAY a question is asked, and applies to the
    whole question, not to individual task-days. That requires a stable question
    identity across days, which is what `question_ids` provides: `task_id` is
    date-stamped, so it cannot express "the same question, asked again".

    Excluding these is not cosmetic. A question whose median forecast is 0.02
    compresses error variance toward zero for a reason that has nothing to do
    with shared priors, and would inflate measured correlation for free.
    """
    first_day: Dict[str, str] = {}
    for i, qid in enumerate(panel.question_ids):
        day = panel.asked_on[i]
        if qid not in first_day or (day and day < first_day[qid]):
            first_day[qid] = day

    verdict: Dict[str, bool] = {}
    for i, qid in enumerate(panel.question_ids):
        if panel.asked_on[i] != first_day.get(qid):
            continue
        row = panel.forecasts[i]
        row = row[~np.isnan(row)]
        if row.size == 0:
            continue
        median = float(np.median(row))
        verdict[qid] = low <= median <= high

    keep = [i for i, qid in enumerate(panel.question_ids) if verdict.get(qid, True)]
    idx = np.asarray(keep, dtype=int)
    return Panel(
        forecasts=panel.forecasts[idx],
        outcomes=panel.outcomes[idx],
        errors=panel.errors[idx],
        task_ids=[panel.task_ids[i] for i in keep],
        model_keys=list(panel.model_keys),
        market_implied=panel.market_implied[idx],
        state=[panel.state[i] for i in keep],
        question_ids=[panel.question_ids[i] for i in keep],
        asked_on=[panel.asked_on[i] for i in keep],
    )


def apply_stale_source_exclusion(
    panel: Panel, max_gap_days: int = MAX_REPORTING_GAP_DAYS
) -> Panel:
    """Drop filing tasks built on a dead reporting series. DEVIATION 3 (2026-09-08).

    `edgar.build_filing_task` now refuses to construct these, but the store is
    append-only and 9 JPM task-days were already collected before the guard
    existed. They ask for the quarter following 2014-12-31 -- a figure filed in
    2015 and present in every model's pretraining -- so the panel would be
    scoring recall, not forecasting, and models that recall the same fact agree.
    That inflates `rho_bar`, which is the study's primary estimand, in the
    direction the hypothesis predicts. It is the one direction a contaminated
    task must never push.

    THE RULE IS MECHANICAL AND WAS FIXED BEFORE ANY OF THESE TASKS RESOLVED.
    It reproduces the generator's own precondition on the read side -- same
    threshold, stated once -- rather than naming JPM or a CIK. So it is not a
    choice about which rows to keep: it catches any filer whose series goes dead
    later, and it cannot have been fitted to an outcome, because on the date it
    was written none of the affected tasks had one. An exclusion decided after
    seeing the scores would be worth nothing, whatever its rationale.

    Macro tasks carry no `last_reported_end` and are never touched.
    """
    keep: List[int] = []
    for i, st in enumerate(panel.state):
        end = (st or {}).get("last_reported_end")
        asked = (st or {}).get("asked_on") or panel.asked_on[i]
        if not end or not asked:
            keep.append(i)
            continue
        try:
            gap = (date.fromisoformat(str(asked)) - date.fromisoformat(str(end))).days
        except ValueError:
            keep.append(i)
            continue
        if gap <= max_gap_days:
            keep.append(i)

    idx = np.asarray(keep, dtype=int)
    return Panel(
        forecasts=panel.forecasts[idx],
        outcomes=panel.outcomes[idx],
        errors=panel.errors[idx],
        task_ids=[panel.task_ids[i] for i in keep],
        model_keys=list(panel.model_keys),
        market_implied=panel.market_implied[idx],
        state=[panel.state[i] for i in keep],
        question_ids=[panel.question_ids[i] for i in keep],
        asked_on=[panel.asked_on[i] for i in keep],
    )


# PREREGISTRATION.md 5.6. Stated once, here, so the analysis and the daily alarm
# in scripts/check_days.py cannot drift apart on what the floor is.
COVERAGE_FLOOR = 0.80


def model_coverage(panel: Panel) -> Dict[str, float]:
    """Usable coverage per model, measured on the panel as it will be estimated.

    Measured HERE rather than over the raw store because 5.6 governs the
    PRIMARY PANEL, and the primary panel is what survives the row exclusions.
    A model can be at 97% across everything collected and still have answered
    almost none of the tasks that actually resolved.
    """
    out: Dict[str, float] = {}
    for i, key in enumerate(panel.model_keys):
        column = panel.forecasts[:, i]
        out[key] = float(np.sum(~np.isnan(column)) / column.size) if column.size else 0.0
    return out


def apply_coverage_exclusion(
    panel: Panel, floor: float = COVERAGE_FLOOR
) -> Tuple[Panel, Dict[str, float]]:
    """Drop models below the usable-coverage floor. REGISTERED (5.6).

    "If usable coverage falls below 80% for any model, that model is reported
    separately and excluded from the primary panel." Both halves matter, so this
    returns what it dropped as well as what it kept, and the caller reports it.

    THIS IS NOT A JUDGEMENT CALL AND IT IS NOT NEW. The rule was registered
    before collection and is applied mechanically to whatever the panel looks
    like when the analysis runs; there is no list of model keys here, and nothing
    about it can be fitted to a result. It reads only which cells are filled,
    never what is in them or how they scored, so it decides identically on
    permuted and unpermuted outcomes -- `neff.analysis` runs blind by default and
    this must not be the thing that makes blinding a fiction.

    WHY IT IS LOAD-BEARING RATHER THAN TIDY. M is inside the estimator:

        N_eff = M / (1 + (M - 1) * rho_bar)

    and `stats.n_eff_from_errors` takes M from the COLUMN COUNT, while `rho_bar`
    is a mean over pairs that clear `min_overlap`. A model too sparse to form a
    single estimable pair therefore contributes nothing to rho_bar and still
    raises M -- the two halves of one formula estimated on different panels. On
    2026-09-09 that was live: qwen lost 2026-09-01 and 2026-09-07 entirely to an
    upstream host (11, deviation 4), every resolved task then traced to the
    2026-09-07 settlement, and qwen sat at 0.0% coverage inside a nine-column
    panel.

    Guarded against emptying the panel: if the floor would remove every model,
    nothing is dropped and the report says so. A panel with no forecasters is not
    a more conservative estimate, it is an absent one.
    """
    if panel.n_tasks == 0 or panel.n_models == 0:
        return panel, {}

    coverage = model_coverage(panel)
    keep = [k for k in panel.model_keys if coverage[k] >= floor]
    dropped = {k: v for k, v in coverage.items() if v < floor}

    if not dropped or not keep:
        return panel, dropped
    return panel.subset_by_models(keep), dropped


def describe(panel: Panel) -> Dict[str, object]:
    """Quick health read on the panel -- run this daily during collection."""
    per_model = {
        key: int(np.sum(~np.isnan(panel.forecasts[:, i])))
        for i, key in enumerate(panel.model_keys)
    }
    per_task = np.sum(~np.isnan(panel.forecasts), axis=1)
    return {
        "n_tasks": panel.n_tasks,
        "n_models": panel.n_models,
        "coverage": round(panel.coverage(), 4),
        "resolved": int(np.sum(~np.isnan(panel.outcomes))),
        "observations_per_model": per_model,
        "models_per_task_median": float(np.median(per_task)) if per_task.size else 0.0,
        "tasks_with_market_benchmark": int(np.sum(~np.isnan(panel.market_implied))),
        "distinct_questions": len(set(panel.question_ids)),
        "distinct_days": len({d for d in panel.asked_on if d}),
        "rows_time_ordered": panel.asked_on == sorted(panel.asked_on),
    }


def count_mock_observations(obs_path=OBS_PATH) -> int:
    """How many synthetic rows are sitting in the observation log. Should be 0
    once real collection starts; reported by the daily health check."""
    return sum(1 for record in JsonlStore(obs_path).read() if _is_mock(record))


def load_replicate_pairs(obs_path=OBS_PATH, include_mock: bool = False) -> Dict[str, Dict[str, List[float]]]:
    """Pair each model's two answers to the same question, asked identically.

    Returns {model_key: {"first": [...], "second": [...]}}, aligned by task.

    These come from `config.REPLICATE_VARIANT`, a reserved prompt_variant that
    `load_panel` filters out, so replicates never enter the primary panel or
    H3's variant arm. They exist only to measure each model's own sampling
    noise -- see stats.test_retest_reliability and PREREGISTRATION.md 5.4(d).
    """
    from .config import REPLICATE_VARIANT

    first: Dict[tuple, float] = {}
    second: Dict[tuple, float] = {}
    if not Path(obs_path).exists():
        return {}

    for line in Path(obs_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not include_mock and _is_mock(rec):
            continue
        value = rec.get("forecast")
        if value is None:
            continue
        key = (rec.get("model_key"), rec.get("task_id"))
        variant = int(rec.get("prompt_variant", 0))
        if variant == 0:
            first[key] = float(value)
        elif variant == REPLICATE_VARIANT:
            second[key] = float(value)

    out: Dict[str, Dict[str, List[float]]] = {}
    for key in sorted(set(first) & set(second)):
        model = key[0]
        bucket = out.setdefault(model, {"first": [], "second": []})
        bucket["first"].append(first[key])
        bucket["second"].append(second[key])
    return out


def reliability_report(obs_path=OBS_PATH, include_mock: bool = False) -> Dict[str, Dict[str, float]]:
    """Per-model noise floor and reliability, ready for the paper's 5.4(d) table."""
    from .stats import noise_floor, test_retest_reliability

    out = {}
    for model, pair in load_replicate_pairs(obs_path, include_mock=include_mock).items():
        out[model] = {
            "n_replicates": len(pair["first"]),
            "reliability": test_retest_reliability(pair["first"], pair["second"]),
            "noise_sd": noise_floor(pair["first"], pair["second"]),
        }
    return out

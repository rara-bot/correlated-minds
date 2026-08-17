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

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import OBS_PATH, RESOLUTIONS_PATH, TASKS_PATH, enabled_panel
from .store import JsonlStore


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
        )


def load_panel(
    obs_path=OBS_PATH,
    resolutions_path=RESOLUTIONS_PATH,
    tasks_path=TASKS_PATH,
    model_keys: Optional[List[str]] = None,
    prompt_variant: int = 0,
    require_resolved: bool = True,
    min_models_per_task: int = 2,
) -> Panel:
    """Build a Panel from the stored record.

    Args:
        require_resolved: keep only tasks with a known outcome. Set False to
            inspect forecasts before anything has settled (useful early on,
            when nothing has resolved yet).
        min_models_per_task: drop tasks answered by too few models to contribute
            any pair.
    """
    keys = model_keys or [m.key for m in enabled_panel()]
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
                },
            )

    # task_id -> model_key -> forecast
    grid: Dict[str, Dict[str, float]] = {}
    for record in JsonlStore(obs_path).read():
        if int(record.get("prompt_variant", 0)) != prompt_variant:
            continue
        model_key = record.get("model_key")
        if model_key not in key_index:
            continue
        forecast = record.get("forecast")
        if forecast is None or record.get("error"):
            continue
        task_id = str(record.get("task_id"))
        grid.setdefault(task_id, {})[str(model_key)] = float(forecast)

    task_ids = sorted(
        tid
        for tid, row in grid.items()
        if len(row) >= min_models_per_task
        and (not require_resolved or tid in resolutions)
    )

    n_tasks, n_models = len(task_ids), len(keys)
    forecasts = np.full((n_tasks, n_models), np.nan, dtype=float)
    outcomes = np.full(n_tasks, np.nan, dtype=float)
    implied = np.full(n_tasks, np.nan, dtype=float)
    state: List[Dict] = []

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

    errors = forecasts - outcomes[:, None]

    return Panel(
        forecasts=forecasts,
        outcomes=outcomes,
        errors=errors,
        task_ids=task_ids,
        model_keys=keys,
        market_implied=implied,
        state=state,
    )


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
    }

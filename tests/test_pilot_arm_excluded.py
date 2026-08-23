"""The pre-registration pilot must not be analysable as study data.

Real forecasts were collected on 21-22 Aug 2026, before the plan was frozen, to
prove the instrument ran end to end. PREREGISTRATION.md 3.5 declares them and
excludes them from every primary estimate.

That exclusion used to exist only in prose. `arm` was recorded on the cost
ledger and nowhere else -- not on the task, not on the observation -- so
`load_panel` could not tell 160 real pilot forecasts from study data, and
returned them inside the primary panel. Unlike mock rows there is nothing about
them that looks wrong: real models, real prices, real latencies.

These tests bind the declaration to the code.
"""

import json

import pytest

from neff import config
from neff.panel import load_panel
from neff.store import Observation, Task


def _row(task_id, model_key, **over):
    row = {
        "obs_id": f"{task_id}-{model_key}", "task_id": task_id,
        "model_key": model_key, "model_id_returned": "x", "provider": "anthropic",
        "prompt_variant": 0, "forecast": 0.5, "direction": "yes",
        "confidence": 0.5, "error": None,
    }
    row.update(over)
    return row


def _write(tmp_path, rows):
    obs = tmp_path / "obs.jsonl"
    obs.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text("")
    res = tmp_path / "res.jsonl"
    res.write_text("")
    return dict(obs_path=obs, tasks_path=tasks, resolutions_path=res)


class TestTheRecordCarriesItsArm:
    def test_task_has_an_arm_field(self):
        assert "arm" in Task("t", "event", "Q?").__dict__

    def test_observation_has_an_arm_field(self):
        obs = Observation("o", "t", "m", "id", "anthropic", 0, 0.5, "yes", 0.5)
        assert "arm" in obs.__dict__

    def test_the_registered_arm_is_named_once(self):
        assert config.PRIMARY_ARM == "ws1_prospective"
        assert config.PRIMARY_ARM in config.ARM_CAPS_USD


class TestPilotRowsCannotReachAPrimaryEstimate:
    def test_pilot_rows_are_excluded(self, tmp_path):
        rows = [_row("t1", k, arm="pilot") for k in ("a", "b")]
        with pytest.warns(RuntimeWarning, match="not labelled"):
            p = load_panel(**_write(tmp_path, rows), model_keys=["a", "b"],
                           require_resolved=False, min_models_per_task=1)
        assert p.n_tasks == 0, "pilot forecasts entered the primary panel"

    def test_unlabelled_rows_are_excluded_too(self, tmp_path):
        """The 180 rows already on disk predate the label and carry none.

        Fail-closed: an absent label must never be read as consent.
        """
        rows = [_row("t1", k) for k in ("a", "b")]
        with pytest.warns(RuntimeWarning):
            p = load_panel(**_write(tmp_path, rows), model_keys=["a", "b"],
                           require_resolved=False, min_models_per_task=1)
        assert p.n_tasks == 0

    def test_registered_rows_are_admitted(self, tmp_path):
        rows = [_row("t1", k, arm=config.PRIMARY_ARM) for k in ("a", "b")]
        p = load_panel(**_write(tmp_path, rows), model_keys=["a", "b"],
                       require_resolved=False, min_models_per_task=1)
        assert p.n_tasks == 1

    def test_a_mixed_file_keeps_only_the_registered_arm(self, tmp_path):
        rows = ([_row("pilot1", k, arm="pilot") for k in ("a", "b")]
                + [_row("real1", k, arm=config.PRIMARY_ARM) for k in ("a", "b")])
        p = load_panel(**_write(tmp_path, rows), model_keys=["a", "b"],
                       require_resolved=False, min_models_per_task=1)
        assert p.task_ids == ["real1"]

    def test_the_pilot_is_still_analysable_when_asked_for_explicitly(self, tmp_path):
        """Excluded from the primary estimate, not deleted. 3.5 permits
        exploratory use provided it is labelled as such."""
        rows = [_row("t1", k, arm="pilot") for k in ("a", "b")]
        p = load_panel(**_write(tmp_path, rows), model_keys=["a", "b"],
                       require_resolved=False, min_models_per_task=1, arm="pilot")
        assert p.n_tasks == 1


class TestTheDeclarationExists:
    def test_prereg_declares_the_pilot_arm(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parent.parent
                / "PREREGISTRATION.md").read_text(encoding="utf-8")
        assert "3.5 Data collected before this registration" in text
        assert "excluded from every primary estimate" in text

"""Deviation 25: a retired model's answers from its first day gone never reach the panel.

On 2026-10-10 Google answered every request for the pinned `gemini-3.5-flash` with
`gemini-3.6-flash`. Those rows are in the append-only record; `load_panel` must
read them as missing, and keep the same model's earlier answers.
"""
import json

from neff.config import PRIMARY_ARM, RETIREMENTS
from neff.panel import load_panel


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_answers_from_the_retirement_day_on_are_dropped(tmp_path):
    assert RETIREMENTS["gemini_flash_pro"] == "2026-10-10"
    days = {"t1": "2026-10-09", "t2": "2026-10-10"}
    tasks, obs = tmp_path / "t.jsonl", tmp_path / "o.jsonl"
    res = tmp_path / "r.jsonl"
    _write(tasks, [{"task_id": t, "state": {"asked_on": d}} for t, d in days.items()])
    _write(res, [{"task_id": t, "outcome": 1.0} for t in days])
    _write(obs, [{"task_id": t, "model_key": k, "forecast": 0.6, "prompt_variant": 0,
                  "arm": PRIMARY_ARM, "provider": "x", "model_id_returned": "x",
                  "created_at": d + "T12:00:00Z"}
                 for t, d in days.items() for k in ("gemini_flash_pro", "gemini_flash", "llama")])
    panel = load_panel(obs_path=obs, resolutions_path=res, tasks_path=tasks)
    col = panel.model_keys.index("gemini_flash_pro")
    by_task = dict(zip(panel.task_ids, panel.forecasts[:, col]))
    assert by_task["t1"] == 0.6
    assert by_task["t2"] != by_task["t2"]  # NaN: not the registered model

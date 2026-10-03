"""The December final look must work in December -- proved on outcomes we made up.

Two separate things are asserted here, and the distinction is the whole point.

  1. THE GATE HOLDS. `scripts/analyze.py --unblind` refuses on every date up to
     and including the freeze. That gate is the only thing standing between the
     study and an unregistered look at its own outcomes (deviation 17 (9)
     permits exactly two: the Week-5 fit on 2026-10-02, and after 2026-12-11).

  2. THE PATH RUNS. Every registered analysis accepts `blind=False` and
     completes -- so nothing is discovered to be broken on 12 December, when
     there is no time left to fix it.

(2) is the reason this file exists, and it is deliberately NOT tested by running
the real analysis unblinded. Doing that IS the thing the gate forbids, and a
test that did it would commit the offence on every push, in CI, forever. So the
unblinded run here is driven against a store fabricated in `tmp_path`: the real
observations, resolutions and tasks are never opened, and the outcomes the
estimator sees were written by this file three lines above.

That is enough, because `blind` does exactly one thing everywhere it appears --
it decides whether `_permute_outcomes` is applied. The estimator underneath is
the same code either way, and it is that code this file exercises.

Written 2026-09-16 alongside §11 deviation 21, which records an unblinded run of
the real store made that day, outside the registered schedule, to answer the
question this file now answers safely.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(ROOT))

from neff import analysis, h1, h2, h3, h4, h5, h6  # noqa: E402
from neff.config import DATA_FREEZE  # noqa: E402

MODELS = ["claude_haiku", "gpt_mid", "llama", "qwen"]


def _load_script():
    spec = importlib.util.spec_from_file_location("analyze_script", ROOT / "scripts" / "analyze.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


@pytest.fixture
def made_up_store(tmp_path):
    """A small store whose outcomes are fabricated, so unblinding it reveals nothing."""
    obs, tasks, res = tmp_path / "obs.jsonl", tmp_path / "tasks.jsonl", tmp_path / "res.jsonl"
    o_rows, t_rows, r_rows = [], [], []
    start = date(2026, 9, 1)
    for i in range(24):
        tid = f"t{i:03d}"
        asked = (start + timedelta(days=i % 8)).isoformat()
        t_rows.append({
            "task_id": tid, "kind": "event", "prompt": "Q?", "resolves_after": "2026-11-01T00:00:00Z",
            "source": "kalshi", "source_ref": f"KXMADEUP-26NOV-T{i % 6}", "outcome_kind": "binary",
            "market_implied": None, "arm": "ws1_prospective",
            "state": {"asked_on": asked, "ladder_distance": (i % 5) / 5.0,
                      "vix_level": 14.0 + (i % 7), "realized_vol_20d": 0.04 + (i % 5) / 100.0,
                      "treasury_10y": 4.5, "yield_curve_10y2y": 0.4, "fed_funds": 3.6,
                      "days_out": 30.0 + i, "series": "KXMADEUP", "strike": float(i % 6)},
        })
        # Outcomes alternate; they are not anyone's data and mean nothing.
        r_rows.append({"task_id": tid, "outcome": float(i % 2), "source": "made-up",
                       "note": "fabricated in tests/test_unblinded_path.py", "schema": "v1"})
        for j, model in enumerate(MODELS):
            o_rows.append({
                "obs_id": f"{tid}-{model}", "task_id": tid, "model_key": model,
                "provider": "test", "model_id_returned": model, "prompt_variant": 0,
                "arm": "ws1_prospective", "forecast": round(0.15 + ((i + j) % 7) / 10.0, 3),
                "direction": "yes", "confidence": 0.6,
                "created_at": f"{asked}T13:10:00+00:00",
            })
    for path, rows in ((obs, o_rows), (tasks, t_rows), (res, r_rows)):
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return {"obs_path": obs, "tasks_path": tasks, "resolutions_path": res}


class TestTheGateHolds:
    """Nothing may unblind the real store before the freeze has passed."""

    @pytest.mark.parametrize("offset", [-120, -30, -1, 0])
    def test_it_refuses_on_or_before_the_freeze(self, offset, monkeypatch):
        script = _load_script()
        when = date.fromisoformat(DATA_FREEZE) + timedelta(days=offset)

        class _Frozen(script.datetime):
            @classmethod
            def now(cls, tz=None):
                return script.datetime(when.year, when.month, when.day, 12, 0, tzinfo=tz)

        monkeypatch.setattr(script, "datetime", _Frozen)
        with pytest.raises(SystemExit) as caught:
            script.main(["--unblind", "--n-boot", "2"])
        assert "REFUSING to unblind" in str(caught.value)

    def test_the_freeze_date_is_the_registered_one(self):
        # A gate that drifts from the registered date is not a gate.
        assert DATA_FREEZE == "2026-12-11"


class TestTheDecemberPathRuns:
    """Every registered analysis completes with blind=False, on made-up outcomes."""

    def test_the_primary_estimator(self, made_up_store):
        out = analysis.run(blind=False, n_boot=5, model_keys=MODELS, **made_up_store)
        assert out["n_tasks"] > 0 and out["n_models"] == len(MODELS)
        assert out["rho_bar"] is not None

    @pytest.mark.parametrize("module", [h1, h2, h3, h4, h5, h6])
    def test_every_hypothesis(self, module, made_up_store, monkeypatch):
        if module is h4:
            monkeypatch.setattr(h4, "HORIZONS", (1,))
            monkeypatch.setattr(h4, "HUMAN_DRAWS", 5)
        kwargs = dict(blind=False, model_keys=MODELS, **made_up_store)
        if module is not h6:          # h6 takes no resample count
            kwargs["n_boot"] = 5
        out = module.run(**kwargs)
        assert out["blind"] is False, f"{module.__name__} ignored blind=False"

    def test_blind_is_the_only_difference(self, made_up_store):
        """blind=True permutes the outcomes; nothing else about the run changes.

        This is what licenses the rest of the file: if the two runs differ only
        by the permutation, then exercising the estimator here exercises the one
        that runs in December.
        """
        shared = dict(n_boot=5, model_keys=MODELS, **made_up_store)
        blind = analysis.run(blind=True, seed=0, **shared)
        opened = analysis.run(blind=False, seed=0, **shared)
        assert blind["n_tasks"] == opened["n_tasks"]
        assert blind["n_models"] == opened["n_models"]
        assert blind["models_excluded"] == opened["models_excluded"]

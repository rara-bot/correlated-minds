"""A retired member is judged where it was asked, and not after (deviation 24).

From 2026-10-23 no host serves `gpt_small`, so it is not asked. Two things follow,
and both are pinned here on stores made up inside the test:

  1. THE DAILY CHECK DOES NOT JUDGE IT. A member that is no longer asked has no rows
     in the coverage window; judged anyway it would sit under the 80% floor, and
     under "watching", every day to the freeze. `scripts/check_days.py` reports it
     as retired instead -- and still judges a member that is asked and failing,
     because its failures are rows.

  2. THE REGISTERED SENSITIVITY KEEPS IT. On the whole panel 5.6 removes a member
     that answered only half the task-days. Deviation 24 registers the primary
     estimate, H3 and H6 again on the task-days asked before the retirement, with
     the registered exclusions applied to THAT sub-panel -- so the restriction must
     come before 5.6, not after it, or the whole-panel verdict would carry over and
     the sensitivity would drop the member it exists to keep. Both orders are
     tested; only the registered one keeps it. The unblinded path is exercised on
     made-up outcomes only, as in tests/test_unblinded_path.py.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from neff import analysis, config, h3, h6
from neff.store import observation_id
from scripts import check_days

MODELS = ["claude_haiku", "gpt_mid", "gpt_small", "llama"]
START = date(2026, 9, 1)
DAYS = 8
CUT = (START + timedelta(days=4)).isoformat()     # the made-up retirement: first day not asked


@pytest.fixture
def store(tmp_path):
    """24 made-up task-days over 8 days; gpt_small answers only those asked before CUT."""
    obs, tasks, res = tmp_path / "obs.jsonl", tmp_path / "tasks.jsonl", tmp_path / "res.jsonl"
    o_rows, t_rows, r_rows = [], [], []
    for i in range(24):
        tid = f"t{i:03d}"
        asked = (START + timedelta(days=i % DAYS)).isoformat()
        t_rows.append({
            "task_id": tid, "kind": "event", "prompt": "Q?", "resolves_after": "2026-11-01T00:00:00Z",
            "source": "kalshi", "source_ref": f"KXMADEUP-26NOV-T{i}", "outcome_kind": "binary",
            "market_implied": None, "arm": config.PRIMARY_ARM,
            "state": {"asked_on": asked, "ladder_distance": (i % 5) / 5.0, "vix_level": 14.0 + (i % 7),
                      "realized_vol_20d": 0.05, "days_out": 30.0}})
        # Outcomes alternate; they are nobody's data and mean nothing.
        r_rows.append({"task_id": tid, "outcome": float(i % 2), "source": "made-up",
                       "note": "fabricated in tests/test_retirement.py", "schema": "v1"})
        for j, model in enumerate(MODELS):
            if model == "gpt_small" and asked >= CUT:
                continue
            o_rows.append({"obs_id": observation_id(tid, model, 0), "task_id": tid, "model_key": model,
                           "provider": "test", "model_id_returned": model, "prompt_variant": 0,
                           "arm": config.PRIMARY_ARM, "forecast": round(0.15 + ((i + j) % 7) / 10.0, 3),
                           "direction": "yes", "confidence": 0.6, "created_at": f"{asked}T17:00:00+00:00"})
    for path, rows in ((obs, o_rows), (tasks, t_rows), (res, r_rows)):
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return {"obs_path": obs, "tasks_path": tasks, "resolutions_path": res}


class TestTheSensitivityKeepsTheRetiredMember:
    def test_on_the_whole_panel_5_6_removes_it(self, store):
        out = analysis.run(blind=True, n_boot=5, model_keys=MODELS, **store)
        assert "gpt_small" in out["models_excluded"]

    def test_before_its_retirement_it_is_complete_and_kept(self, store):
        out = analysis.run(blind=True, n_boot=5, model_keys=MODELS, asked_before_day=CUT, **store)
        assert out["models_excluded"] == {} and out["n_models"] == len(MODELS)
        assert out["asked_before"] == CUT
        assert out["n_tasks"] == sum(1 for i in range(24) if (START + timedelta(days=i % DAYS)).isoformat() < CUT)

    def test_restricting_after_the_exclusions_would_have_dropped_it(self, store):
        # The order is the whole point: the same restriction applied to the panel 5.6
        # has already judged loses the member the sensitivity exists to keep.
        whole, _ = analysis.apply_registered_exclusions(analysis.load_panel(model_keys=MODELS, **store))
        late = analysis.asked_before(whole, CUT)
        assert "gpt_small" not in late.model_keys
        early, excluded = analysis.apply_registered_exclusions(
            analysis.asked_before(analysis.load_panel(model_keys=MODELS, **store), CUT))
        assert "gpt_small" in early.model_keys and excluded["models_below_coverage_floor"] == {}

    def test_h6_takes_the_same_restriction(self, store):
        out = h6.run(blind=True, asked_before_day=CUT, model_keys=MODELS, **store)
        assert "gpt_small" in out["models"] and out["asked_before"] == CUT
        assert "gpt_small" not in h6.run(blind=True, model_keys=MODELS, **store)["models"]

    def test_h3_takes_the_same_restriction(self, store):
        out = h3.run(blind=True, asked_before_day=CUT, start=START.isoformat(), model_keys=MODELS, **store)
        assert out["asked_before"] == CUT and "gpt_small" in out["models"]

    def test_no_restriction_is_no_restriction(self, store):
        p = analysis.load_panel(model_keys=MODELS, **store)
        assert analysis.asked_before(p, None) is p

    def test_the_december_path_runs_it_unblinded_on_made_up_outcomes(self, store):
        blind = analysis.run(blind=True, seed=0, n_boot=5, model_keys=MODELS, asked_before_day=CUT, **store)
        seen = analysis.run(blind=False, seed=0, n_boot=5, model_keys=MODELS, asked_before_day=CUT, **store)
        assert seen["blind"] is False and seen["n_models"] == blind["n_models"] == len(MODELS)
        assert seen["rho_bar"] is not None


class TestTheDailyCheckDoesNotJudgeIt:
    def _run(self, tmp_path, monkeypatch, capsys, small_fails=False):
        obs, tasks = tmp_path / "o.jsonl", tmp_path / "t.jsonl"
        rows, trows = [], []
        for d in range(12):
            day = (START + timedelta(days=d)).isoformat()
            for n in range(3):
                tid = f"t{d}-{n}"
                trows.append({"task_id": tid, "arm": config.PRIMARY_ARM, "state": {"asked_on": day}})
                created = f"{day}T17:00:00+00:00"
                rows.append({"obs_id": f"{tid}-h", "task_id": tid, "model_key": "claude_haiku",
                             "prompt_variant": 0, "forecast": 0.4, "created_at": created})
                if d < 3 or small_fails:
                    rows.append({"obs_id": f"{tid}-s", "task_id": tid, "model_key": "gpt_small",
                                 "prompt_variant": 0, "forecast": None if small_fails else 0.4,
                                 "error": "HTTP 404: model not found" if small_fails else None,
                                 "created_at": created})
        obs.write_text("".join(json.dumps(r) + "\n" for r in rows))
        tasks.write_text("".join(json.dumps(r) + "\n" for r in trows))
        monkeypatch.setattr(check_days, "OBSERVATIONS", obs)
        monkeypatch.setattr(check_days, "TASKS", tasks)
        check_days.main()
        return capsys.readouterr().out

    def test_a_member_no_longer_asked_is_reported_as_retired_not_as_failing(self, tmp_path, monkeypatch, capsys):
        out = self._run(tmp_path, monkeypatch, capsys)
        line = next(ln for ln in out.splitlines() if ln.strip().startswith("gpt_small"))
        assert "not asked since 2026-09-03" in line and "retired" in line
        assert "gpt_small" not in out.split("coverage --")[1].split("market state")[0].replace(line, "")

    def test_a_member_that_is_asked_and_failing_is_still_judged(self, tmp_path, monkeypatch, capsys):
        out = self._run(tmp_path, monkeypatch, capsys, small_fails=True)
        assert "BELOW COVERAGE FLOOR AND STILL FAILING: gpt_small" in out
        assert "not asked since" not in out

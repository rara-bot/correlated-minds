"""A panel member no host serves any more is retired on its day (deviations 23 and 24).

OpenAI shuts `gpt-4.1-nano-2025-04-14` -- `gpt_small` -- down on 2026-10-23.
Deviation 23 (19 Sep) moved it that day to Azure's copy of the snapshot, which
Microsoft's schedule then kept until 2027-04-14, and opened a BRIDGE: every
question of the day also asked through Azure, at a reserved variant, so the change
of host would be measured before it was made. On 23 Sep Microsoft moved Azure's
retirement of the snapshot to 2026-10-14, before the move. Deviation 24 (30 Sep):
no member changes host; `gpt_small` is asked through OpenAI up to 2026-10-22 and
not at all from 2026-10-23; the bridge keeps measuring through 2026-10-13, the
last day Azure serves the model.

Pinned here: nothing moves host; `gpt_small` is retired on the registered day and
every other model is untouched; the bridge runs on exactly its registered days,
pinned to one host with no fallback, for the primary arm, and reaches no estimate,
no coverage alarm, no drift alarm and no logprob count; a retired member is not
judged against the coverage floor; and the sensitivity deviation 24 registers
keeps the retired member where it was asked, by restricting BEFORE the exclusions.
"""
import json
from argparse import Namespace
from datetime import date

import numpy as np
import pytest

from neff import collect, config, panel, providers, report, tasks
from neff.config import (BRIDGE_END, BRIDGE_ROUTES, BRIDGE_START, BRIDGE_VARIANT, H3_VARIANTS,
                         REPLICATE_VARIANT, RETIREMENTS, SERVING_ROUTES, RunConfig, bridge_spec,
                         mock_sandbox, panel_by_key, retired, routed)
from neff.store import Task, observation_id
from scripts import check_days

SMALL = panel_by_key()["gpt_small"]
ROUTE = BRIDGE_ROUTES["gpt_small"]
BRIDGE_DAY = date(2026, 9, 25)
AFTER_BRIDGE_DAY = date(2026, 10, 20)
RETIRED_DAY = date(2026, 10, 26)
MOVE_DAY = "2026-10-23"          # the move deviation 23 registered and deviation 24 withdrew


# --- 1. what changes, and what does not ------------------------------------------------

class TestTheRetirement:
    def test_no_member_changes_host_any_more(self):
        assert SERVING_ROUTES == {}
        for spec in config.PANEL:
            for day in ("2026-09-20", MOVE_DAY, "2026-12-11"):
                assert routed(spec, day) is spec

    def test_gpt_small_is_asked_through_its_last_day_and_not_after(self):
        # OpenAI deprecations, "2026-04-22: Legacy GPT model snapshots": gpt-4.1-nano-2025-04-14,
        # shutdown October 23, 2026. Azure's schedule, updated 2026-09-23: retirement 2026-10-14.
        assert RETIREMENTS == {"gpt_small": "2026-10-23"}
        assert not retired(SMALL, "2026-10-22") and retired(SMALL, "2026-10-23")
        assert retired("gpt_small", "2026-12-07")

    def test_no_other_model_retires(self):
        for spec in config.PANEL:
            if spec.key == "gpt_small":
                continue
            for day in ("2026-09-20", MOVE_DAY, "2026-12-11"):
                assert not retired(spec, day)
                assert bridge_spec(spec, day) is None

    def test_the_registered_roster_is_untouched(self):
        # Retirement is applied when a day is collected; the roster the plan
        # registers (3.1) and tests/test_roster.py pins is what it was.
        assert (SMALL.provider, SMALL.model_id) == ("openai", "gpt-4.1-nano-2025-04-14")


class TestTheBridge:
    @pytest.mark.parametrize("day,expected", [
        ("2026-09-19", False), (BRIDGE_START, True), ("2026-10-13", True),
        ("2026-10-14", False), ("2026-10-22", False), (MOVE_DAY, False), ("2026-12-11", False),
    ])
    def test_it_runs_from_its_start_to_the_day_before_azure_retires_the_model(self, day, expected):
        assert BRIDGE_END == "2026-10-13"
        assert (bridge_spec(SMALL, day) is not None) is expected

    def test_it_asks_on_exactly_the_route_it_measures_and_changes_nothing_else(self):
        bridge = bridge_spec(SMALL, BRIDGE_START)
        assert (bridge.provider, bridge.model_id) == ("openrouter_azure", "openai/gpt-4.1-nano")
        assert bridge.supports_logprobs is False            # the route serves none
        for name in ("key", "family", "tier", "price", "primary", "enabled", "thinking_budget"):
            assert getattr(bridge, name) == getattr(SMALL, name), name

    def test_its_variant_is_no_other_variant(self):
        assert BRIDGE_VARIANT not in (0, REPLICATE_VARIANT, *range(1, H3_VARIANTS))

    def test_it_is_not_a_prompt_variant(self):
        # A bridge row carries the variant-0 prompt, byte for byte.
        with pytest.raises(ValueError):
            tasks.variant_prompt("You are producing a calibrated forecast", BRIDGE_VARIANT)

    def test_the_continuity_check_knows_the_same_variant(self):
        assert check_days.BRIDGE_VARIANT == BRIDGE_VARIANT


# --- 2. the provider ---------------------------------------------------------------------

class TestTheAzureProvider:
    PROVIDER = providers.PROVIDERS["openrouter_azure"]

    def test_it_is_registered_and_is_openrouter(self):
        assert isinstance(self.PROVIDER, providers.OpenRouterProvider)
        assert self.PROVIDER.KEY_NAMES == ("OPENROUTER_API_KEY",)
        assert self.PROVIDER.UPSTREAM_FIELD == "provider"

    def test_it_is_pinned_to_azure_with_no_fallback(self):
        body = self.PROVIDER._body(bridge_spec(SMALL, BRIDGE_START), "Q?", 1000, False)
        assert body["provider"] == {"order": ["Azure"], "allow_fallbacks": False,
                                    "require_parameters": True}
        assert body["model"] == "openai/gpt-4.1-nano"
        assert body["temperature"] == config.TEMPERATURE == 0.0
        assert "logprobs" not in body

    def test_the_general_openrouter_routing_is_unchanged(self):
        # Deviation 4: free routing for the open-weight models, one host ignored.
        assert providers.PROVIDERS["openrouter"].EXTRA_BODY == {
            "provider": {"require_parameters": True, "allow_fallbacks": True, "ignore": ["Novita"]}}

    def test_the_host_that_answered_is_recorded(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        sent = {}

        class Reply:
            status_code = 200
            text = ""

            def json(self):
                return {"model": "openai/gpt-4.1-nano", "provider": "Azure",
                        "choices": [{"message": {"content": '{"probability": 0.4}'}}],
                        "usage": {"prompt_tokens": 100, "completion_tokens": 20}}

        def fake_post(url, headers, json, timeout):
            sent.update(url=url, body=json)
            return Reply()

        monkeypatch.setattr(providers.httpx, "post", fake_post)
        done = self.PROVIDER.complete(bridge_spec(SMALL, BRIDGE_START), "Q?", 1000, 30)
        assert sent["url"] == providers.OpenRouterProvider.URL
        assert (done.model_id, done.upstream_provider, done.logprobs) == (
            "openai/gpt-4.1-nano", "Azure", None)


# --- 3. collection --------------------------------------------------------------------

def _task(n, day):
    return Task(
        task_id=f"sr-t{n}-{day}", kind="event",
        prompt=tasks.build_prompt(title=f"Will series {n} print above 2.5%?",
                                  resolution_criteria="Resolves YES if it does.",
                                  close_time="2026-11-15T12:30:00Z", context="- VIX: 15.00",
                                  as_of=day, variant=0),
        resolves_after="", source="kalshi", source_ref=f"KXTEST-26NOV-T{n}",
        outcome_kind="binary",
        state={"asked_on": day.isoformat(), "ladder_distance": 0.2, "vix_level": 15.0,
               "realized_vol_20d": 0.05, "days_out": 30.0},
    )


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "TASKS_PATH", tmp_path / "tasks.jsonl")
    monkeypatch.setattr(collect, "OBS_PATH", tmp_path / "observations.jsonl")
    monkeypatch.setattr(collect, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    state = {"day": BRIDGE_DAY}
    monkeypatch.setattr(collect, "build_daily_tasks",
                        lambda **kw: [_task(i, state["day"]) for i in range(3)])
    return mock_sandbox(tmp_path / "observations.jsonl"), state


def _run(day, bridge=True, models=("gpt_small", "claude_haiku")):
    return collect.run_day(
        config=RunConfig(arm="pilot", tasks_per_day=3, replicates_per_day=0,
                         model_keys=list(models), bridge=bridge),
        as_of=day, use_mock=True)


def _rows(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


class TestCollection:
    def test_a_bridge_day_asks_every_question_on_both_routes(self, sandbox, capsys):
        obs, state = sandbox
        summary = _run(BRIDGE_DAY)
        rows = _rows(obs)
        small = {(r["task_id"], r["prompt_variant"]): r for r in rows if r["model_key"] == "gpt_small"}
        tids = {r["task_id"] for r in rows}
        assert set(small) == {(t, v) for t in tids for v in (0, BRIDGE_VARIANT)}
        assert all(small[(t, 0)]["model_id_returned"].startswith("gpt-4.1-nano-2025-04-14") for t in tids)
        assert all(small[(t, BRIDGE_VARIANT)]["model_id_returned"].startswith("openai/gpt-4.1-nano")
                   for t in tids)
        # Only the rerouted model is bridged, and the bridge is not an H3 variant.
        assert {r["prompt_variant"] for r in rows if r["model_key"] != "gpt_small"} == {0}
        assert summary["bridge"] == 3 and summary["h3_variants"] == 0
        # The bridge row answers to its own route's id: no false drift alarm.
        assert summary["drift"] == []
        assert "MODEL ID DRIFT" not in capsys.readouterr().out

    def test_the_bridge_prompt_is_the_primary_prompt(self, sandbox, monkeypatch):
        obs, state = sandbox
        asked = []
        real_ask = collect.ask

        def spy(**kw):
            asked.append((kw["spec"].key, kw["prompt_variant"], kw["prompt"]))
            return real_ask(**kw)

        monkeypatch.setattr(collect, "ask", spy)
        _run(BRIDGE_DAY)
        by = {}
        for key, variant, prompt in asked:
            by.setdefault(key, {}).setdefault(variant, set()).add(prompt)
        assert by["gpt_small"][BRIDGE_VARIANT] == by["gpt_small"][0]

    def test_a_rerun_of_the_day_adds_no_bridge_rows(self, sandbox):
        obs, state = sandbox
        _run(BRIDGE_DAY)
        before = len(_rows(obs))
        _run(BRIDGE_DAY)
        assert len(_rows(obs)) == before

    def test_after_the_bridge_ends_only_openai_is_asked(self, sandbox):
        obs, state = sandbox
        state["day"] = AFTER_BRIDGE_DAY
        summary = _run(AFTER_BRIDGE_DAY)
        small = [r for r in _rows(obs) if r["model_key"] == "gpt_small"]
        assert small and {r["prompt_variant"] for r in small} == {0}
        assert all(r["model_id_returned"].startswith("gpt-4.1-nano-2025-04-14") for r in small)
        assert summary["bridge"] == 0 and summary["drift"] == []

    def test_from_its_retirement_it_is_not_asked_at_all(self, sandbox, capsys):
        obs, state = sandbox
        state["day"] = RETIRED_DAY
        _run(RETIRED_DAY)
        rows = _rows(obs)
        assert rows and not [r for r in rows if r["model_key"] == "gpt_small"]
        assert {r["model_key"] for r in rows} == {"claude_haiku"}
        assert "not asked, retired (deviation 24): gpt_small" in capsys.readouterr().out

    def test_off_for_every_arm_but_the_primary(self, sandbox):
        obs, state = sandbox
        _run(BRIDGE_DAY, bridge=False)
        assert {r["prompt_variant"] for r in _rows(obs)} == {0}

    def test_the_daily_command_turns_it_on_for_the_primary_arm_only(self):
        args = dict(dry_run=False, concurrency=4, variants=1, models=None, tasks=None, no_h3=False)
        assert collect.config_from_args(Namespace(arm=config.PRIMARY_ARM, **args)).bridge is True
        assert collect.config_from_args(Namespace(arm="pilot", **args)).bridge is False

    def test_a_dry_run_prices_the_bridge_and_writes_nothing(self, sandbox):
        obs, state = sandbox
        summary = collect.run_day(
            config=RunConfig(arm="pilot", tasks_per_day=3, replicates_per_day=0,
                             model_keys=["gpt_small"], bridge=True, dry_run=True),
            as_of=BRIDGE_DAY, use_mock=True)
        assert summary["dry_run"] is True and summary["estimated_usd"] > 0
        assert not obs.exists()


class TestNoLogprobAlarmFromTheBridge:
    def test_bridge_rows_are_not_counted_as_logprobs_missing(self):
        from neff.store import Observation

        spec = SMALL
        primary = Observation(obs_id="a", task_id="t", model_key="gpt_small", model_id_returned=spec.model_id,
                              provider="openai", prompt_variant=0, forecast=0.4, direction="no",
                              confidence=0.5, logprobs=[{"token": "4", "logprob": -0.1, "top": []}])
        bridge = Observation(obs_id="b", task_id="t", model_key="gpt_small",
                             model_id_returned="openai/gpt-4.1-nano", provider="openrouter_azure",
                             prompt_variant=BRIDGE_VARIANT, forecast=0.4, direction="no",
                             confidence=0.5, upstream_provider="Azure", logprobs=None)
        report_ = collect.logprobs_coverage([primary, bridge], [spec])
        assert report_["gpt_small"] == {"answered": 1, "carried": 1, "hosts_without": {}}


# --- 4. the bridge reaches no estimate and no coverage alarm -------------------------------

def _obs(task, model, variant, forecast, created="2026-09-25T17:00:00+00:00", error=None):
    return {"obs_id": observation_id(task, model, variant), "task_id": task, "model_key": model,
            "provider": "test", "model_id_returned": model, "prompt_variant": variant,
            "arm": config.PRIMARY_ARM, "forecast": forecast, "direction": "yes",
            "confidence": 0.5, "error": error, "created_at": created}


class TestTheBridgeReachesNoEstimate:
    def test_the_panel_reads_variant_zero_only(self, tmp_path):
        obs, tasks_path, res = tmp_path / "o.jsonl", tmp_path / "t.jsonl", tmp_path / "r.jsonl"
        rows, trows, rrows = [], [], []
        for i in range(4):
            tid = f"t{i}"
            trows.append({"task_id": tid, "kind": "event", "source_ref": f"KXA-26OCT-T{i}",
                          "arm": config.PRIMARY_ARM, "resolves_after": "2026-10-01T00:00:00Z",
                          "state": {"asked_on": "2026-09-25"}})
            rrows.append({"task_id": tid, "outcome": float(i % 2)})
            for m in ("gpt_small", "claude_haiku"):
                rows.append(_obs(tid, m, 0, 0.3 + 0.1 * i))
            rows.append(_obs(tid, "gpt_small", BRIDGE_VARIANT, 0.99))
        for path, rs in ((obs, rows), (tasks_path, trows), (res, rrows)):
            path.write_text("".join(json.dumps(r) + "\n" for r in rs))
        p = panel.load_panel(obs_path=obs, resolutions_path=res, tasks_path=tasks_path,
                             model_keys=["gpt_small", "claude_haiku"])
        column = p.model_keys.index("gpt_small")
        assert 0.99 not in set(p.forecasts[:, column])

    def test_the_bridge_report_pairs_the_routes_and_sets_them_beside_the_noise(self, tmp_path):
        obs = tmp_path / "o.jsonl"
        rows = []
        for i in range(6):
            tid = f"t{i}"
            rows.append(_obs(tid, "gpt_small", 0, 0.2 + 0.1 * i))
            rows.append(_obs(tid, "gpt_small", BRIDGE_VARIANT, 0.2 + 0.1 * i + (0.05 if i == 5 else 0)))
            if i < 4:
                rows.append(_obs(tid, "gpt_small", REPLICATE_VARIANT, 0.2 + 0.1 * i))
        obs.write_text("".join(json.dumps(r) + "\n" for r in rows))
        out = panel.bridge_report(obs_path=obs)
        assert set(out) == {"gpt_small"}
        across = out["gpt_small"]["across_routes"]
        assert across["n"] == 6
        assert across["identical_share"] == pytest.approx(5 / 6)
        assert across["mean_abs_difference"] == pytest.approx(0.05 / 6)
        assert out["gpt_small"]["own_replicates"]["n"] == 4
        # The replicate reader is unchanged by the generalisation.
        assert panel.load_replicate_pairs(obs_path=obs)["gpt_small"]["second"] == pytest.approx(
            [0.2, 0.3, 0.4, 0.5])

    def test_a_failing_bridge_does_not_pull_the_model_under_the_floor(self, tmp_path, monkeypatch, capsys):
        obs, tasks_path = tmp_path / "o.jsonl", tmp_path / "t.jsonl"
        rows, trows = [], []
        for d in range(1, 8):
            day = f"2026-09-{20 + d:02d}"
            for n in range(5):
                tid = f"t{d}-{n}"
                trows.append({"task_id": tid, "arm": config.PRIMARY_ARM,
                              "state": {"asked_on": day}})
                created = f"{day}T17:00:00+00:00"
                rows.append(_obs(tid, "gpt_small", 0, 0.4, created))
                rows.append(_obs(tid, "gpt_small", BRIDGE_VARIANT, None, created, error="HTTP 503"))
        obs.write_text("".join(json.dumps(r) + "\n" for r in rows))
        tasks_path.write_text("".join(json.dumps(r) + "\n" for r in trows))
        monkeypatch.setattr(check_days, "OBSERVATIONS", obs)
        monkeypatch.setattr(check_days, "TASKS", tasks_path)
        check_days.main()
        out = capsys.readouterr().out
        assert "BELOW COVERAGE FLOOR" not in out
        assert "bridge (deviations 23-24): gpt_small through its second host answered 0/5" in out


# --- 5. the registered sensitivity ------------------------------------------------------

class TestTheSensitivity:
    def _panel(self):
        days = ["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"]
        forecasts = np.array([[0.2, 0.3], [0.4, 0.5], [0.6, 0.7], [0.8, 0.9]])
        outcomes = np.array([0.0, 1.0, 0.0, 1.0])
        return panel.Panel(forecasts=forecasts, outcomes=outcomes,
                           errors=forecasts - outcomes[:, None], task_ids=list("abcd"),
                           model_keys=["gpt_small", "claude_haiku"],
                           market_implied=np.full(4, np.nan), state=[{} for _ in days],
                           question_ids=list("abcd"), asked_on=days)

    def test_it_removes_exactly_the_rerouted_cells(self):
        p = self._panel()
        out = report.without_route(p, "gpt_small", MOVE_DAY)
        assert np.isnan(out.forecasts[2:, 0]).all() and np.isnan(out.errors[2:, 0]).all()
        np.testing.assert_array_equal(out.forecasts[:2, 0], p.forecasts[:2, 0])
        np.testing.assert_array_equal(out.forecasts[:, 1], p.forecasts[:, 1])
        assert out.n_tasks == p.n_tasks and out.model_keys == p.model_keys
        assert not np.isnan(p.forecasts).any()          # the input is not modified

    def test_a_panel_without_the_model_is_returned_as_it_is(self):
        p = self._panel().subset_by_models(["claude_haiku"])
        assert report.without_route(p, "gpt_small", MOVE_DAY) is p

    def test_the_withdrawn_route_is_no_longer_reported(self):
        # Deviation 24 withdrew the move, so nothing is ever asked on the route and
        # deviation 23's sensitivity has nothing to remove.
        sens = report.strata(self._panel(), n_boot=0)["sensitivity"]
        assert not [k for k in sens if k.startswith("without_gpt_small_from_")]


# --- 6. a failing bridge raises the daily alarm, and says no day is at risk ------------------

def _alarm_script() -> str:
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "daily.yml").read_text()
    step = text[text.index("      - name: Raise an alarm if a day is at risk"):]
    body = step[step.index("python - <<'PY' > alarm.txt"):]
    code = body[body.index("\n") + 1: body.index("\n          PY\n")]
    return "\n".join(line[10:] for line in code.split("\n"))


def _alarm(tmp_path, monkeypatch, continuity):
    import subprocess
    import sys
    (tmp_path / "continuity.json").write_text(json.dumps(continuity))
    done = subprocess.run([sys.executable, "-c", _alarm_script()], cwd=tmp_path,
                          env={"JOB_STATUS": "success", "PATH": ""}, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


class TestTheAlarm:
    BASE = {"today": "2026-09-25", "today_state": "pending", "today_collected": True,
            "missing_days": [], "below_floor": [], "window_days": 7, "coverage_window": {},
            "bridge_day": "2026-09-25"}

    def test_a_failing_bridge_raises_it(self, tmp_path, monkeypatch):
        out = _alarm(tmp_path, monkeypatch, {**self.BASE, "bridge_latest": {
            "gpt_small": {"answered": 3, "asked": 25}}})
        assert "the bridge that asks `gpt_small` through a second host" in out and "3/25" in out
        assert "no day is at risk" in out and "moves to" not in out

    def test_a_healthy_one_is_silent(self, tmp_path, monkeypatch):
        out = _alarm(tmp_path, monkeypatch, {**self.BASE, "bridge_latest": {
            "gpt_small": {"answered": 25, "asked": 25}}})
        assert out == ""

    def test_no_bridge_is_silent(self, tmp_path, monkeypatch):
        assert _alarm(tmp_path, monkeypatch, dict(self.BASE)) == ""

    def test_check_days_hands_the_alarm_what_it_reads(self, tmp_path, monkeypatch):
        obs, tasks_path = tmp_path / "o.jsonl", tmp_path / "t.jsonl"
        rows, trows = [], []
        for n in range(4):
            tid = f"t{n}"
            trows.append({"task_id": tid, "arm": config.PRIMARY_ARM, "state": {"asked_on": "2026-09-25"}})
            rows.append(_obs(tid, "gpt_small", 0, 0.4))
            rows.append(_obs(tid, "gpt_small", BRIDGE_VARIANT, 0.4 if n else None,
                             error=None if n else "HTTP 503"))
        obs.write_text("".join(json.dumps(r) + "\n" for r in rows))
        tasks_path.write_text("".join(json.dumps(r) + "\n" for r in trows))
        monkeypatch.setattr(check_days, "OBSERVATIONS", obs)
        monkeypatch.setattr(check_days, "TASKS", tasks_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(check_days.sys, "argv", ["check_days.py", "--json"])
        check_days.main()
        written = json.loads((tmp_path / "continuity.json").read_text())
        assert written["bridge_day"] == "2026-09-25"
        assert written["bridge_latest"] == {"gpt_small": {"answered": 3, "asked": 4}}

"""H3's intra-model arm: one model, five registered prompt variants.

PREREGISTRATION.md 4 H3 (a) registers "N_eff for one model under 5 prompt
variants". The five framings were in `tasks.PROMPT_VARIANTS` from before the
freeze, and nothing ever asked one: the daily run collected variant 0 only, and
the generic `--variants` path re-sent the variant-0 prompt under each new label
-- identical questions, identical framing, stored as though they were variants.
A registered hypothesis had no data for its first 13 collection days
(deviation 14).

These hold the three properties that matter: a variant differs from variant 0 in
its framing and in nothing else, the arm collects exactly one model's variants
1-4, and none of it can reach the primary panel.
"""

import json
from argparse import Namespace
from datetime import date

import pytest

from neff import collect, config, panel, tasks
from neff.config import H3_VARIANT_MODEL, H3_VARIANTS, RunConfig, mock_sandbox
from neff.store import Task

QUESTION = dict(
    resolution_criteria="Resolves YES if the release exceeds 2.5%.",
    close_time="2026-10-15T12:30:00Z",
    context="- VIX: 15.00",
    as_of=date(2026, 9, 14),
)


def _prompt(n, variant=0):
    return tasks.build_prompt(
        title=f"Will series {n} print above 2.5%?", variant=variant, **QUESTION
    )


def _task(n):
    return Task(
        task_id=f"h3-t{n}", kind="event", prompt=_prompt(n), resolves_after="",
        source="kalshi", source_ref=f"KXTEST-26OCT-T{n}", outcome_kind="binary",
        state={"asked_on": "2026-09-14", "ladder_distance": 0.2, "vix_level": 15.0,
               "realized_vol_20d": 0.05, "days_out": 30.0},
    )


class TestAVariantIsTheSameQuestionFramedDifferently:
    @pytest.mark.parametrize("variant", range(H3_VARIANTS))
    def test_matches_building_the_prompt_as_that_variant(self, variant):
        """The stored prompt is variant 0. Building the question as variant v
        from its source must give exactly what `variant_prompt` gives."""
        assert tasks.variant_prompt(_prompt(1), variant) == _prompt(1, variant)

    def test_every_variant_is_distinct(self):
        prompts = {tasks.variant_prompt(_prompt(1), v) for v in range(H3_VARIANTS)}
        assert len(prompts) == H3_VARIANTS

    def test_only_the_framing_changes(self):
        base = _prompt(1)
        for v in range(1, H3_VARIANTS):
            varied = tasks.variant_prompt(base, v)
            assert varied.endswith(base)
            assert varied[: len(varied) - len(base)] == tasks.PROMPT_VARIANTS[v]

    def test_variant_zero_is_the_stored_prompt_untouched(self):
        assert tasks.variant_prompt("anything at all", 0) == "anything at all"

    def test_an_unregistered_variant_is_refused(self):
        with pytest.raises(ValueError):
            tasks.variant_prompt(_prompt(1), H3_VARIANTS)

    def test_the_replicate_variant_is_not_a_prompt_variant(self):
        with pytest.raises(ValueError):
            tasks.variant_prompt(_prompt(1), config.REPLICATE_VARIANT)

    def test_a_prompt_without_the_instructions_is_refused_not_guessed(self):
        with pytest.raises(ValueError):
            tasks.variant_prompt("Will X happen?", 2)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "TASKS_PATH", tmp_path / "tasks.jsonl")
    monkeypatch.setattr(collect, "OBS_PATH", tmp_path / "observations.jsonl")
    monkeypatch.setattr(collect, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(collect, "build_daily_tasks",
                        lambda **kw: [_task(i) for i in range(3)])
    # `use_mock=True` below, so collection lands in the mock sandbox beside these.
    return mock_sandbox(tmp_path / "observations.jsonl")


def _run(h3=H3_VARIANT_MODEL, models=None, dry_run=False, as_of=date(2026, 9, 14)):
    return collect.run_day(
        config=RunConfig(arm="pilot", tasks_per_day=3, replicates_per_day=0,
                         model_keys=models or [H3_VARIANT_MODEL, "claude_haiku"],
                         h3_variant_model=h3, dry_run=dry_run),
        as_of=as_of,
        use_mock=True,
    )


def _rows(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


class TestTheArmCollectsOneModelsVariants:
    def test_variants_one_to_four_for_the_h3_model_only(self, sandbox):
        _run()
        seen = {(r["model_key"], r["prompt_variant"]) for r in _rows(sandbox)}
        assert {(H3_VARIANT_MODEL, v) for v in range(H3_VARIANTS)} <= seen
        assert {v for model, v in seen if model != H3_VARIANT_MODEL} == {0}

    def test_every_task_gets_every_variant(self, sandbox):
        _run()
        per_task = {}
        for r in _rows(sandbox):
            if r["model_key"] == H3_VARIANT_MODEL:
                per_task.setdefault(r["task_id"], set()).add(r["prompt_variant"])
        assert len(per_task) == 3
        assert all(v == set(range(H3_VARIANTS)) for v in per_task.values())

    def test_each_variant_was_sent_its_own_prompt(self, sandbox, monkeypatch):
        """The defect this arm replaces: the label changed and the prompt did not."""
        sent = {}
        real_ask = collect.ask

        def spy(**kw):
            sent[(kw["task_id"], kw["spec"].key, kw["prompt_variant"])] = kw["prompt"]
            return real_ask(**kw)

        monkeypatch.setattr(collect, "ask", spy)
        _run()
        for n in range(3):
            prompts = {sent[(f"h3-t{n}", H3_VARIANT_MODEL, v)] for v in range(H3_VARIANTS)}
            assert len(prompts) == H3_VARIANTS
            assert sent[(f"h3-t{n}", H3_VARIANT_MODEL, 0)] == _prompt(n)

    def test_a_rerun_adds_nothing(self, sandbox):
        _run()
        first = len(_rows(sandbox))
        _run()
        assert len(_rows(sandbox)) == first

    def test_off_means_off(self, sandbox):
        _run(h3=None)
        assert {r["prompt_variant"] for r in _rows(sandbox)} == {0}

    def test_nothing_before_the_registered_start(self, sandbox):
        """Deviation 14 registers the arm from 2026-09-14. The evening re-run of
        the 13th runs whatever code has landed by then, and must add no variant."""
        summary = _run(as_of=date(2026, 9, 13))
        assert summary["observations"] == 6          # variant 0, both models
        assert {r["prompt_variant"] for r in _rows(sandbox)} == {0}

    def test_a_model_outside_the_roster_skips_the_arm_not_the_day(self, sandbox):
        summary = _run(models=["claude_haiku"])
        assert summary["observations"] == 3
        assert {r["prompt_variant"] for r in _rows(sandbox)} == {0}

    def test_the_summary_counts_the_arm(self, sandbox):
        assert _run()["h3_variants"] == 3 * (H3_VARIANTS - 1)

    def test_a_dry_run_prices_the_arm(self, sandbox):
        assert _run(dry_run=True)["estimated_usd"] > _run(h3=None, dry_run=True)["estimated_usd"]

    def test_an_unbuildable_prompt_costs_the_variant_not_the_day(self, sandbox, monkeypatch):
        bare = Task(task_id="bare", kind="event", prompt="Will X happen?",
                    resolves_after="", source="kalshi", source_ref="BARE-1",
                    outcome_kind="binary", state={"asked_on": "2026-09-14"})
        monkeypatch.setattr(collect, "build_daily_tasks", lambda **kw: [bare])
        summary = _run()
        assert summary["observations"] == 2          # variant 0, both models
        assert {r["prompt_variant"] for r in _rows(sandbox)} == {0}


class TestTheArmNeverReachesThePrimaryPanel:
    def test_the_panel_holds_variant_zero_only(self, sandbox, tmp_path):
        """A variant leaking in would not lengthen the matrix -- it would
        OVERWRITE the model's primary answer, as a leaked replicate would."""
        _run()
        p = panel.load_panel(
            obs_path=sandbox, tasks_path=mock_sandbox(tmp_path / "tasks.jsonl"),
            resolutions_path=tmp_path / "none.jsonl",
            model_keys=[H3_VARIANT_MODEL, "claude_haiku"],
            require_resolved=False, include_mock=True, arm="pilot",
        )
        assert p.n_tasks == 3
        primary = {r["task_id"]: r["forecast"] for r in _rows(sandbox)
                   if r["prompt_variant"] == 0 and r["model_key"] == H3_VARIANT_MODEL}
        col = p.model_keys.index(H3_VARIANT_MODEL)
        for i, task_id in enumerate(p.task_ids):
            assert p.forecasts[i, col] == pytest.approx(primary[task_id])

    def test_variant_ids_stay_inside_the_registered_range(self):
        assert H3_VARIANTS == 5 == len(tasks.PROMPT_VARIANTS)
        assert config.REPLICATE_VARIANT >= H3_VARIANTS


class TestTheWorkflowTurnsItOn:
    def _args(self, **overrides):
        values = dict(arm=config.PRIMARY_ARM, dry_run=False, mock=False, tasks=None,
                      concurrency=4, variants=1, models=None, no_resolve=False,
                      no_h3=False)
        values.update(overrides)
        return Namespace(**values)

    def test_on_for_the_primary_arm(self):
        assert collect.config_from_args(self._args()).h3_variant_model == H3_VARIANT_MODEL

    def test_off_for_any_other_arm(self):
        assert collect.config_from_args(self._args(arm="pilot")).h3_variant_model is None

    def test_can_be_switched_off(self):
        assert collect.config_from_args(self._args(no_h3=True)).h3_variant_model is None

    def test_the_workflow_reaches_it_through_the_command_line(self):
        workflow = (config.ROOT / ".github" / "workflows" / "daily.yml").read_text()
        assert "python -m neff.collect" in workflow
        assert "--arm ws1_prospective" in workflow
        assert "--no-h3" not in workflow

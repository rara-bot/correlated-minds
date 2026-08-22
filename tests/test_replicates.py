"""Measure the sampling noise the registered temperature=0 does not remove.

§9 registers `TEMPERATURE = 0.0`, and `config.py` gives the reason: *"we want
each model's modal judgement"*, so cross-model differences reflect the models
rather than our sampling.

Measured on 22 Aug 2026, 3 prompts x 4 repetitions, that holds for **five of ten
models**. The others move their probability on an IDENTICAL prompt:

    claude_sonnet .033   gpt_small .033   gemini_flash_pro .033
    llama .040           gemini_flash .093        (mean spread)

Which models move shifts between runs, so it is infrastructure -- batched
inference, and backend routing on OpenRouter -- not a property of any model, and
no setting removes it.

The consequence runs one way, and that is what makes it registrable rather than
merely embarrassing. Sampling noise is IDIOSYNCRATIC: uncorrelated across models
by construction, it dilutes every pairwise correlation and inflates apparent
independence -- rho_bar too low, N_eff too high. That biases against this study's
own hypothesis. Safe direction, unknown size.

So a few questions each day go to every model twice, identically. The spread
between the answers is each model's noise floor, which converts "probably small"
into a measured reliability coefficient.

These tests hold the two properties that matter: the replicates must be measured
correctly, and they must never leak into the primary panel.
"""

import json
from datetime import date

import pytest

from neff import collect, panel
from neff.config import REPLICATE_VARIANT, REPLICATES_PER_DAY, RunConfig
from neff.stats import disattenuate, noise_floor
from neff.stats import test_retest_reliability as reliability
from neff.store import Task, observation_id


class TestReliabilityMath:
    def test_identical_answers_are_perfectly_reliable(self):
        assert reliability([0.1, 0.5, 0.9], [0.1, 0.5, 0.9]) == 1.0

    def test_a_constant_answer_is_reliable_not_undefined(self):
        """No variance to explain, but also no noise. Must not be NaN."""
        assert reliability([0.5] * 4, [0.5] * 4) == 1.0

    def test_small_wobble_stays_high(self):
        r = reliability([0.1, 0.5, 0.9], [0.15, 0.45, 0.95])
        assert 0.95 < r < 1.0

    def test_shuffled_answers_are_unreliable(self):
        assert reliability([0.1, 0.5, 0.9], [0.9, 0.1, 0.5]) < 0.2

    def test_clipped_to_unit_interval(self):
        for a, b in [([0.1, 0.9], [0.9, 0.1]), ([0.2, 0.3], [0.25, 0.28])]:
            assert 0.0 <= reliability(a, b) <= 1.0

    def test_too_few_pairs_is_nan_not_a_guess(self):
        import math

        assert math.isnan(reliability([0.5], [0.5]))

    def test_noise_floor_is_in_probability_units(self):
        """Directly interpretable: 'this model wobbles by about +/- X'."""
        sd = noise_floor([0.1, 0.5, 0.9], [0.2, 0.6, 1.0])
        assert sd == pytest.approx(0.0, abs=1e-9)  # constant offset, no spread
        sd2 = noise_floor([0.5, 0.5, 0.5], [0.4, 0.6, 0.5])
        assert 0.0 < sd2 < 0.2


class TestDisattenuation:
    def test_correction_raises_the_correlation(self):
        assert disattenuate(0.80, 0.9, 0.9) == pytest.approx(0.80 / 0.9)

    def test_perfect_reliability_is_a_no_op(self):
        assert disattenuate(0.73, 1.0, 1.0) == pytest.approx(0.73)

    def test_never_exceeds_one(self):
        assert disattenuate(0.95, 0.5, 0.5) <= 1.0

    def test_zero_reliability_is_nan_not_infinity(self):
        import math

        assert math.isnan(disattenuate(0.8, 0.0, 0.9))

    def test_correction_moves_toward_our_own_hypothesis(self):
        """Which is exactly why it must be reported alongside the raw value and
        never instead of it."""
        raw = 0.70
        corrected = disattenuate(raw, 0.85, 0.85)
        assert corrected > raw


def _task(n):
    return Task(
        task_id=f"task{n}", kind="event", prompt=f"Q{n}?", resolves_after="",
        source="kalshi", source_ref=f"T{n}", outcome_kind="binary",
        market_implied=None,
        state={"ladder_distance": 0.2, "vix_level": 15.0,
               "realized_vol_20d": 0.06, "days_out": 30.0, "asked_on": "2026-08-24"},
    )


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "TASKS_PATH", tmp_path / "tasks.jsonl")
    monkeypatch.setattr(collect, "OBS_PATH", tmp_path / "obs.jsonl")
    monkeypatch.setattr(collect, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(collect, "build_daily_tasks", lambda **kw: [_task(i) for i in range(6)])
    return tmp_path / "obs.jsonl"


def _run(obs_path, replicates=REPLICATES_PER_DAY):
    collect.run_day(
        config=RunConfig(arm="pilot", tasks_per_day=6, replicates_per_day=replicates),
        as_of=date(2026, 8, 24),
        use_mock=True,
    )
    return [json.loads(l) for l in obs_path.read_text().splitlines() if l.strip()]


class TestReplicatesAreCollected:
    def test_replicates_appear_at_the_reserved_variant(self, sandbox):
        rows = _run(sandbox)
        reps = [r for r in rows if r["prompt_variant"] == REPLICATE_VARIANT]
        assert reps, "no replicates collected"

    def test_exactly_the_configured_number_of_tasks_is_replicated(self, sandbox):
        rows = _run(sandbox)
        reps = [r for r in rows if r["prompt_variant"] == REPLICATE_VARIANT]
        assert len({r["task_id"] for r in reps}) == REPLICATES_PER_DAY

    def test_every_model_answers_the_replicated_task(self, sandbox):
        """A reliability estimate for only some of the panel would leave the
        correction undefined for exactly the pairs it is needed on."""
        rows = _run(sandbox)
        primary = {r["model_key"] for r in rows if r["prompt_variant"] == 0}
        reps = {r["model_key"] for r in rows if r["prompt_variant"] == REPLICATE_VARIANT}
        assert reps == primary

    def test_replicate_ids_do_not_collide_with_the_primary(self, sandbox):
        a = observation_id("task0", "llama", 0)
        b = observation_id("task0", "llama", REPLICATE_VARIANT)
        assert a != b

    def test_can_be_switched_off(self, sandbox):
        rows = _run(sandbox, replicates=0)
        assert not [r for r in rows if r["prompt_variant"] == REPLICATE_VARIANT]

    def test_selection_is_seeded_and_repeatable(self, sandbox):
        """Registered analyses cannot depend on an unrecorded random draw."""
        first = {r["task_id"] for r in _run(sandbox) if r["prompt_variant"] == REPLICATE_VARIANT}
        sandbox.unlink()
        second = {r["task_id"] for r in _run(sandbox) if r["prompt_variant"] == REPLICATE_VARIANT}
        assert first == second

    def test_a_dry_run_collects_no_replicates(self, sandbox):
        collect.run_day(
            config=RunConfig(arm="pilot", dry_run=True, tasks_per_day=6),
            as_of=date(2026, 8, 24),
        )
        assert not sandbox.exists() or sandbox.read_text() == ""


class TestReplicatesNeverReachThePrimaryPanel:
    """The whole design rests on this. A replicate leaking into the panel would
    double-count one question for one model and corrupt the very correlations it
    exists to correct."""

    def test_panel_uses_the_primary_answer_not_the_replicate(self, tmp_path):
        """The real failure mode, which is subtler than an extra row.

        The panel is keyed by (task, model), so a leaked replicate does not
        lengthen the matrix -- it OVERWRITES the primary answer with the second
        draw. Silent, and it substitutes exactly the noisy re-sample the
        replicate exists to measure. Distinguishable only by the value itself.
        """
        import json as _json

        obs = tmp_path / "obs.jsonl"
        rows = [
            {"obs_id": "a", "task_id": "t1", "model_key": "llama", "provider": "openrouter",
             "model_id_returned": "meta-llama/llama-3.3-70b-instruct", "prompt_variant": 0,
             "forecast": 0.20, "direction": "no", "confidence": 0.5,
             "created_at": "2026-08-24T13:10:00+00:00"},
            {"obs_id": "b", "task_id": "t1", "model_key": "llama", "provider": "openrouter",
             "model_id_returned": "meta-llama/llama-3.3-70b-instruct",
             "prompt_variant": REPLICATE_VARIANT,
             "forecast": 0.80, "direction": "yes", "confidence": 0.5,
             "created_at": "2026-08-24T13:11:00+00:00"},
            {"obs_id": "c", "task_id": "t1", "model_key": "qwen", "provider": "openrouter",
             "model_id_returned": "qwen/qwen-2.5-72b-instruct", "prompt_variant": 0,
             "forecast": 0.30, "direction": "no", "confidence": 0.5,
             "created_at": "2026-08-24T13:10:00+00:00"},
        ]
        obs.write_text("\n".join(_json.dumps(r) for r in rows) + "\n")
        tasks = tmp_path / "tasks.jsonl"
        tasks.write_text(_json.dumps({
            "task_id": "t1", "kind": "event", "prompt": "Q?", "resolves_after": "",
            "source": "kalshi", "source_ref": "T1", "outcome_kind": "binary",
            "market_implied": None,
            "state": {"asked_on": "2026-08-24", "ladder_distance": 0.2,
                      "vix_level": 15.0, "realized_vol_20d": 0.06, "days_out": 30.0},
        }) + "\n")

        p = panel.load_panel(
            obs_path=obs, tasks_path=tasks, resolutions_path=tmp_path / "none.jsonl",
            model_keys=["llama", "qwen"], require_resolved=False, min_models_per_task=1,
        )
        llama_col = list(p.model_keys).index("llama")
        value = p.forecasts[0][llama_col]
        assert value == pytest.approx(0.20), (
            f"panel took {value} -- the REPLICATE (0.80) overwrote the primary "
            f"answer (0.20)"
        )

    def test_replicate_variant_is_outside_the_h3_range(self):
        """H3 registers five prompt variants, 0-4. The reserved id must not
        collide with them."""
        assert REPLICATE_VARIANT > 4

    def test_pairs_are_aligned_by_task(self, sandbox, monkeypatch):
        _run(sandbox)
        pairs = panel.load_replicate_pairs(obs_path=sandbox, include_mock=True)
        assert pairs
        for model, bucket in pairs.items():
            assert len(bucket["first"]) == len(bucket["second"])
            assert len(bucket["first"]) == REPLICATES_PER_DAY

    def test_reliability_report_covers_every_model(self, sandbox, monkeypatch):
        _run(sandbox)
        monkeypatch.setattr(panel, "OBS_PATH", sandbox)
        rep = panel.reliability_report(obs_path=sandbox, include_mock=True)
        assert rep
        for model, stats in rep.items():
            assert stats["n_replicates"] == REPLICATES_PER_DAY
            assert 0.0 <= stats["reliability"] <= 1.0 or stats["reliability"] != stats["reliability"]


class TestCostOfTheArm:
    def test_replicates_are_a_small_fraction_of_the_day(self):
        """Two extra tasks against a 25-task battery: ~8%, roughly $4 over the
        study. Cheap enough that the measurement is worth having."""
        from neff.config import TASKS_PER_DAY, MEASURED_DAILY_USD, collection_days

        overhead = REPLICATES_PER_DAY / TASKS_PER_DAY
        assert overhead <= 0.10
        extra = MEASURED_DAILY_USD * overhead * collection_days()
        assert extra < 6.0

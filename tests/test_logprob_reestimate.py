"""The 5.4(a) re-estimate on logprob-derived probabilities, which nothing ran until 2026-09-14.

Deviation 19 decided which logprobs are valid and what probability they imply;
deviation 20 fixes the comparison. These tests check that the cells are the ones the
panel reads, that a source is judged on everything it returned, and that the
comparison differs from the emitted estimate only where the probabilities do.
"""

import json
import math

import numpy as np
import pytest

from neff import logprobs, report
from neff.analysis import apply_registered_exclusions
from neff.panel import Panel, load_panel

FAST = 30
EXPECTED = (math.exp(-0.1) * 0.35 + math.exp(-2.5) * 0.40) / (math.exp(-0.1) + math.exp(-2.5))


def _row(task, model, host=None, good=True, variant=0, error=None, forecast=0.35):
    top = [["35", -0.1], ["40", -2.5]] if good else [["40", -0.1], ["35", -2.0]]
    return {"arm": "ws1_prospective", "task_id": task, "model_key": model, "prompt_variant": variant,
            "forecast": forecast, "error": error, "provider": "openrouter" if host else "openai",
            "upstream_provider": host, "model_id_returned": "served",
            "raw_response": '{"probability": 0.35}',
            "logprobs": [{"t": "0", "lp": 0.0, "top": [["0", 0.0]]},
                         {"t": "35", "lp": -0.1 if good else -2.0, "top": top}]}


def _store(tmp_path, rows):
    path = tmp_path / "observations.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def _panel(forecasts, y):
    n, m = forecasts.shape
    return Panel(forecasts=forecasts, outcomes=y, errors=forecasts - y[:, None],
                 task_ids=[f"t{i}" for i in range(n)], model_keys=[f"m{j}" for j in range(m)],
                 market_implied=np.full(n, np.nan), state=[{} for _ in range(n)],
                 question_ids=[f"KXS{i % 30}-26OCT{i % 12:02d}-T{i}" for i in range(n)],
                 asked_on=[f"2026-09-{1 + i % 28:02d}" for i in range(n)])


class TestTheCells:
    def test_a_usable_source_gives_the_expectation_over_its_alternatives(self, tmp_path):
        out = logprobs.derived_forecasts(["t1"], ["gpt_mid"], obs_path=_store(tmp_path, [_row("t1", "gpt_mid")]))
        assert out[0, 0] == pytest.approx(EXPECTED)

    def test_one_inconsistent_row_in_any_variant_condemns_its_host(self, tmp_path):
        rows = [_row("t1", "llama", host="H"), _row("t2", "llama", host="H", good=False, variant=3),
                _row("t1", "gpt_small")]
        out = logprobs.derived_forecasts(["t1", "t2"], ["llama", "gpt_small"],
                                         obs_path=_store(tmp_path, rows))
        assert np.isnan(out[:, 0]).all() and out[0, 1] == pytest.approx(EXPECTED)

    def test_the_cell_is_the_row_the_panel_keeps(self, tmp_path):
        rows = [_row("t1", "gpt_mid"), _row("t1", "gpt_mid", error="HTTP 500", forecast=None),
                dict(_row("t1", "gpt_mid"), arm="pilot"), dict(_row("t2", "gpt_mid"), provider="mock")]
        out = logprobs.derived_forecasts(["t1", "t2"], ["gpt_mid"], obs_path=_store(tmp_path, rows))
        assert out[0, 0] == pytest.approx(EXPECTED) and np.isnan(out[1, 0])

    def test_on_the_committed_store_the_leg_sits_inside_the_panel(self):
        panel, _ = apply_registered_exclusions(load_panel())
        has = np.isfinite(logprobs.derived_forecasts(panel.task_ids, panel.model_keys))
        assert np.isfinite(panel.forecasts[has]).all()
        if "deepseek" in panel.model_keys:
            assert not has[:, panel.model_keys.index("deepseek")].any()
        assert all(panel.asked_on[i] >= "2026-09-09" for i in np.nonzero(has.any(axis=1))[0])


class TestTheComparison:
    def setup_method(self):
        rng = np.random.default_rng(3)
        y = (rng.uniform(size=80) < 0.5).astype(float)
        self.panel = _panel(np.clip(0.5 + 0.2 * (y - 0.5)[:, None] + rng.normal(0, 0.1, (80, 4)), 0, 1), y)

    def test_identical_probabilities_differ_by_nothing(self):
        out = report.logprob_leg(self.panel, self.panel.forecasts.copy(), n_boot=FAST)
        assert all(v["point"] == 0.0 for v in out["derived_minus_emitted"].values())
        assert out["mean_abs_shift"] == 0.0

    def test_a_cell_without_a_derived_value_leaves_both_estimates(self):
        derived = self.panel.forecasts.copy()
        derived[:40, 3] = np.nan
        out = report.logprob_leg(self.panel, derived, n_boot=FAST)
        assert out["cells"] == 80 * 4 - 40
        assert out["derived_minus_emitted"]["rho_bar"]["point"] == 0.0

    def test_a_model_without_any_derived_value_is_left_out_and_two_are_needed(self):
        derived = self.panel.forecasts.copy()
        derived[:, 2:] = np.nan
        assert report.logprob_leg(self.panel, derived, n_boot=FAST)["models"] == ["m0", "m1"]
        derived[:, 1] = np.nan
        assert "why_not" in report.logprob_leg(self.panel, derived, n_boot=FAST)

"""H3 had no implementation, and its intra-model arm no data, until September 2026.

Deviation 14 collects `gpt_mid`'s prompt variants from 2026-09-14; deviation 20 fixes
how the three arms are formed, matched, compared and permuted. These tests pin the arms
at the registered panel, check the verdict recovers structure planted in synthetic
data, and check the variant columns are read the way the primary panel reads its own.
"""

import math

import numpy as np
import pytest

from neff import h3
from neff.analysis import apply_registered_exclusions
from neff.config import H3_VARIANT_START, primary_panel
from neff.panel import Panel, load_panel

FAST = 40
FAMILY = {"a1": "A", "a2": "A", "b1": "B", "b2": "B", "c1": "C", "c2": "C"}


def _wide(intra, cross, family_share=0.0, n=150, seed=0):
    rng = np.random.default_rng(seed)
    shared = rng.normal(size=n)
    factor = {f: rng.normal(size=n) for f in "ABC"}
    own = 1.0 - cross - family_share
    columns = [math.sqrt(cross) * shared + math.sqrt(family_share) * factor[FAMILY[k]]
               + math.sqrt(own) * rng.normal(size=n) for k in FAMILY]
    base = rng.normal(size=n)
    columns += [math.sqrt(intra) * base + math.sqrt(1.0 - intra) * rng.normal(size=n)
                for _ in range(5)]
    errors = np.column_stack(columns)
    return Panel(forecasts=errors, outcomes=np.zeros(n), errors=errors,
                 task_ids=[f"t{i}" for i in range(n)],
                 model_keys=list(FAMILY) + [h3.variant_key(v, "m") for v in range(5)],
                 market_implied=np.full(n, np.nan), state=[{} for _ in range(n)],
                 question_ids=[f"KXS{i % 30}-26OCT{i % 15:02d}-T{i}" for i in range(n)],
                 asked_on=[f"2026-10-{1 + i % 30:02d}" for i in range(n)])


class TestTheArms:
    def test_the_registered_nine_give_ten_three_and_twelve_pairs(self):
        family = {m.key: m.family for m in primary_panel()}
        keys = list(family) + [h3.variant_key(v) for v in range(5)]
        pairs = h3.arm_pairs(keys, family)
        assert [len(pairs[arm]) for arm in h3.ARMS] == [10, 3, 12]
        within = {tuple(sorted((keys[i], keys[j]))) for i, j in pairs["within_family"]}
        assert within == {("claude_haiku", "claude_sonnet"), ("gpt_mid", "gpt_small"),
                          ("gemini_flash", "gemini_flash_pro")}

    def test_a_family_that_loses_a_member_leaves_both_family_arms(self):
        family = {m.key: m.family for m in primary_panel()}
        keys = [k for k in family if k != "gemini_flash"] + [h3.variant_key(v) for v in range(5)]
        pairs = h3.arm_pairs(keys, family)
        assert [len(pairs[arm]) for arm in h3.ARMS] == [10, 2, 4]


class TestTheVerdict:
    def test_variants_that_move_together_buy_less_independence_than_families(self):
        out = h3.evaluate(_wide(intra=0.9, cross=0.1), FAMILY, n_boot=FAST, model="m")
        assert out["n_eff"]["intra_model"] < out["n_eff"]["cross_family_matched"]
        assert out["separation"]["claimed"] == -1 and out["verdict"] == "supports H3"

    def test_overlapping_intervals_falsify_it_as_registered(self):
        out = h3.evaluate(_wide(intra=0.3, cross=0.3), FAMILY, n_boot=FAST, model="m")
        assert out["separation"]["claimed"] == 0 and out["verdict"].startswith("falsified")

    def test_separation_is_read_from_both_bounds(self):
        assert h3.separation({"lo": 1.0, "hi": 1.2}, {"lo": 1.5, "hi": 1.9}) == -1
        assert h3.separation({"lo": 2.0, "hi": 2.2}, {"lo": 1.5, "hi": 1.9}) == 1
        assert h3.separation({"lo": 1.0, "hi": 1.6}, {"lo": 1.5, "hi": 1.9}) == 0
        assert h3.separation({"lo": None, "hi": 1.6}, {"lo": 1.5, "hi": 1.9}) is None

    def test_without_variant_columns_it_is_untested_not_null(self):
        out = h3.evaluate(_wide(intra=0.9, cross=0.1), FAMILY, n_boot=FAST, model="nobody")
        assert out["verdict"] == "untested" and "intra_model" in out["why_not"]


class TestThePermutation:
    def test_planted_family_structure_takes_the_smallest_p_the_labels_allow(self):
        panel = _wide(intra=0.5, cross=0.0, family_share=0.6)
        out = h3.family_permutation(panel.errors, panel.model_keys, FAMILY)
        assert out["labelings"] == 15
        assert out["p_one_sided"] == pytest.approx(1 / 15)


class TestTheStore:
    def test_variant_zero_is_the_primary_answer(self):
        panel, _ = apply_registered_exclusions(load_panel())
        wide = h3.attach_variants(panel)
        primary = wide.forecasts[:, wide.model_keys.index("gpt_mid")]
        zero = wide.forecasts[:, wide.model_keys.index(h3.variant_key(0))]
        assert np.array_equal(primary, zero, equal_nan=True)

    def test_the_driver_runs_blind_from_the_registered_start(self):
        out = h3.run(n_boot=5)
        assert out["blind"] is True and out["variants_from"] == H3_VARIANT_START
        assert "verdict" in out

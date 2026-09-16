"""H6 had no implementation until 2026-09-14.

PREREGISTRATION.md 3.1 refuses the cluster-robust t-statistic for the family contrast
and registers an exact permutation over family labels; deviation 20 fixes the rest.
These tests pin the permutation's size at the registered panel, and check that planted
lineage survives the capability terms while a panel without it is falsified.
"""

import math
from collections import Counter

import numpy as np

from neff import h6
from neff.config import primary_panel
from neff.panel import Panel
from neff.stats import family_partitions

REGISTERED = [m.family for m in primary_panel()]
FAMILY = {m.key: m.family for m in primary_panel()}


def _canonical(assignment):
    return frozenset(frozenset(i for i, g in enumerate(assignment) if g == k) for k in set(assignment))


def _lineage(share, n=200, seed=4):
    rng = np.random.default_rng(seed)
    models = primary_panel()
    y = (rng.uniform(size=n) < 0.5).astype(float)
    factor = {m.family: rng.normal(size=n) for m in models}
    scale = rng.permutation(np.linspace(0.15, 0.4, len(models)))
    errors = np.column_stack([
        scale[k] * (math.sqrt(share) * factor[m.family] + math.sqrt(1.0 - share) * rng.normal(size=n))
        for k, m in enumerate(models)])
    return Panel(forecasts=y[:, None] + errors, outcomes=y, errors=errors,
                 task_ids=[f"t{i}" for i in range(n)], model_keys=[m.key for m in models],
                 market_implied=np.full(n, np.nan), state=[{} for _ in range(n)],
                 question_ids=[f"KXS{i % 40}-26OCT{i % 16:02d}-T{i}" for i in range(n)],
                 asked_on=[f"2026-09-{1 + i % 30:02d}" for i in range(n)])


class TestTheLabelings:
    def test_the_registered_nine_admit_exactly_1260_distinct_labelings(self):
        parts = family_partitions(REGISTERED)
        canonical = {_canonical(p) for p in parts}
        assert len(parts) == 1260 == len(canonical)
        assert _canonical(REGISTERED) in canonical

    def test_every_labeling_keeps_the_family_sizes(self):
        sizes = sorted(Counter(REGISTERED).values())
        assert all(sorted(Counter(p).values()) == sizes for p in family_partitions(REGISTERED))

    def test_losing_a_single_model_family_leaves_420(self):
        assert len(family_partitions([m.family for m in primary_panel() if m.key != "qwen"])) == 420


class TestTheVerdict:
    def test_planted_lineage_survives_the_capability_terms(self):
        out = h6.evaluate(_lineage(0.6), FAMILY)
        assert out["with_capability_terms"]["coefficient"] > 0
        assert out["with_capability_terms"]["p_two_sided"] < 0.01
        assert out["verdict"].startswith("supports H6")

    def test_a_panel_without_family_structure_is_falsified(self):
        out = h6.evaluate(_lineage(0.0), FAMILY)
        assert out["verdict"].startswith("falsified")

    def test_each_same_family_pair_meets_its_nearest_cross_family_pair(self):
        table = {"pairs": [(0, 1), (0, 2), (1, 2), (2, 3)], "rho": np.array([0.5, 0.1, 0.2, 0.3]),
                 "mean_skill": np.array([0.30, 0.31, 0.10, 0.50]),
                 "skill_gap": np.array([0.02, 0.03, 0.2, 0.0])}
        out = h6.matched_pairs(table, ["A", "A", "B", "C"], ["a", "b", "c", "d"])
        assert out["matches"] == {"a~b": "a~c"}
        assert out["same_family_rho"] == 0.5 and out["matched_cross_family_rho"] == 0.1

    def test_the_driver_runs_blind_on_the_committed_store(self):
        out = h6.run()
        assert out["blind"] is True and out["with_capability_terms"]["partitions"] > 0

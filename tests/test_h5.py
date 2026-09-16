"""H5's interval on the Type A minus Type B difference, and the resampling H2 to H6 share.

Until 2026-09-14 the two headrooms were reported and the interval on their difference
was not. Deviation 20 fixes it, and fixes in one place what every hypothesis after H1
means by a resample and by a claimed sign.
"""

import numpy as np

from neff import analysis, h5
from neff.panel import Panel

FAST = 40
FILED = {"last_reported_end": "2026-06-30"}


def _panel(errors, states):
    errors = np.asarray(errors, dtype=float)
    n, m = errors.shape
    return Panel(forecasts=errors, outcomes=np.zeros(n), errors=errors,
                 task_ids=[f"t{i}" for i in range(n)], model_keys=[f"m{j}" for j in range(m)],
                 market_implied=np.full(n, np.nan), state=states,
                 question_ids=[f"KXS{i % 40}-26OCT{i % 16:02d}-T{i}" for i in range(n)],
                 asked_on=[f"2026-09-{1 + i % 30:02d}" for i in range(n)])


class TestTheDifference:
    def test_independent_macro_errors_and_shared_filing_errors_put_it_above_zero(self):
        rng = np.random.default_rng(2)
        n, m = 240, 5
        filing = np.arange(n) % 2 == 1
        errors = rng.normal(0, 0.2, (n, m))
        k = int(filing.sum())
        errors[filing] = rng.normal(0, 0.2, (k, 1)) + rng.normal(0, 0.03, (k, m))
        out = h5.evaluate(_panel(errors, [FILED if f else {} for f in filing]), n_boot=FAST)
        assert (out["task_days_type_a"], out["task_days_type_b"]) == (120, 120)
        assert out["difference_a_minus_b"]["headroom_pearson"] > 2
        for label in analysis.RESAMPLINGS:
            assert analysis.sign_of(out["intervals"]["headroom_pearson"][label]) == 1
            assert out["interval_holds_zero"]["headroom_pearson"][label] is False

    def test_the_same_errors_in_both_formats_hold_zero(self):
        rng = np.random.default_rng(7)
        n = 240
        errors = 0.7 * rng.normal(0, 0.2, (n, 1)) + rng.normal(0, 0.2, (n, 5))
        out = h5.evaluate(_panel(errors, [FILED if i % 2 else {} for i in range(n)]), n_boot=FAST)
        assert out["interval_holds_zero"]["headroom_pearson"][analysis.GOVERNING] is True

    def test_the_driver_runs_blind_on_the_committed_store(self):
        out = h5.run(n_boot=5)
        assert out["blind"] is True and set(out["intervals"]) == set(h5.SCALES)


class TestTheSharedResampling:
    def test_every_registered_resampling_is_drawn_and_vectors_keep_their_shape(self):
        panel = _panel(np.random.default_rng(1).normal(size=(60, 3)), [{}] * 60)
        draws = analysis.resampled(panel, lambda idx: [float(len(idx)), 1.0], n_boot=7)
        assert set(draws) == set(analysis.RESAMPLINGS)
        assert all(d.shape == (7, 2) for d in draws.values())

    def test_undefined_draws_are_counted(self):
        out = analysis.percentile_interval(np.array([np.nan, 1.0, 2.0, 3.0]))
        assert out["undefined_draws"] == 1 and out["lo"] is not None

    def test_a_sign_is_claimed_only_where_the_settlement_clustered_interval_agrees(self):
        below, holds = {"lo": -2.0, "hi": -1.0}, {"lo": -1.0, "hi": 1.0}
        settlement = "event_clustered_settlement"
        assert analysis.claimed_sign({analysis.GOVERNING: below, settlement: below}) == -1
        assert analysis.claimed_sign({analysis.GOVERNING: below, settlement: holds}) == 0
        assert analysis.claimed_sign({analysis.GOVERNING: below}) is None

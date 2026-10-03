"""The Week-5 prediction, made mechanical before anyone could see what it would say.

PREREGISTRATION.md 5.3 registers the date, the fit and the shape of the sentence,
and leaves every operational choice open: what a macro release is, what its
surprise is, which task-days make up its panel, how X and Y come out of the fit,
and what happens if no qualifying release arrives. Deviation 18 fixes them on
2026-09-13. These tests hold the rules that could otherwise be bent on 2 Oct:
X and Y can only be as strict as the calibration medians or stricter, the
holdout sees only task-days asked after the prediction, and a miss is a miss.
"""

import math
from datetime import datetime, timezone

import numpy as np
import pytest

from neff import prediction
from neff.panel import Panel
from neff.stats import mean_pairwise_correlation, n_eff

UTC = timezone.utc


def build(spec, m=6, seed=0):
    """spec: (event, task_days, ask_days, shared) -- shared near 1 means one common error."""
    rng = np.random.default_rng(seed)
    errors, refs, days = [], [], []
    for event, n, ask_days, shared in spec:
        common = rng.normal(size=n)
        errors.append(shared * common[:, None] + (1 - shared) * rng.normal(size=(n, m)))
        refs += [f"{event}-T{k}" for k in range(n)]
        days += [ask_days[k % len(ask_days)] for k in range(n)]
    e = np.vstack(errors)
    n = e.shape[0]
    return Panel(forecasts=e, outcomes=np.zeros(n), errors=e,
                 task_ids=[f"t{i}" for i in range(n)], model_keys=[f"m{j}" for j in range(m)],
                 market_implied=np.full(n, np.nan), state=[{} for _ in range(n)],
                 question_ids=refs, asked_on=days)


SEPT = ["2026-09-02", "2026-09-05", "2026-09-09"]
OCT = ["2026-10-05", "2026-10-08"]


def close(month, day):
    return datetime(2026, month, day, 12, 29, tzinfo=UTC)


class TestOneReleasesPanel:
    def test_too_few_task_days_is_not_eligible(self):
        p = build([("KXCPIYOY-26AUG", 4, SEPT, 0.5)])
        record = prediction.event_metrics(p, range(4), "KXCPIYOY-26AUG", close(9, 11), 0.1)
        assert record["eligible"] is False and "task-day" in record["why_not"]

    def test_uses_the_registered_estimator(self):
        p = build([("KXCPIYOY-26AUG", 12, SEPT, 0.6)])
        record = prediction.event_metrics(p, range(12), "KXCPIYOY-26AUG", close(9, 11), 0.1)
        rho = mean_pairwise_correlation(p.errors)
        assert record["rho_bar"] == pytest.approx(rho)
        assert record["headroom"] == pytest.approx(n_eff(rho, 6) - 1.0)


class TestCalibration:
    def test_medians_when_there_are_too_few_releases_for_a_fit(self):
        spec = [("KXCPIYOY-26AUG", 10, SEPT, 0.2), ("KXUSPPI-26SEP10", 10, SEPT, 0.5),
                ("KXPAYROLLS-26SEP", 10, SEPT, 0.8)]
        closes = {"KXCPIYOY-26AUG": close(9, 11), "KXUSPPI-26SEP10": close(9, 10),
                  "KXPAYROLLS-26SEP": close(10, 2)}
        cal = prediction.calibrate(build(spec), closes, {e: 0.1 for e in closes}, p80=0.2)
        assert cal["made"] and cal["fit"] is None and cal["eligible"] == 3
        heads = [e["headroom"] for e in cal["events"]]
        rhos = [e["rho_bar"] for e in cal["events"]]
        assert cal["X"] == pytest.approx(np.median(heads))
        assert cal["Y"] == pytest.approx(np.median(rhos))

    def _four(self, h1_direction):
        events = ["KXCPIYOY-26AUG", "KXUSPPI-26SEP10", "KXUSPPIYOY-26SEP10", "KXPAYROLLS-26SEP"]
        surprises = [0.02, 0.05, 0.08, 0.11]
        shared = [0.2, 0.4, 0.6, 0.8] if h1_direction else [0.8, 0.6, 0.4, 0.2]
        spec = [(e, 30, SEPT, s) for e, s in zip(events, shared)]
        closes = {e: close(9, 20) for e in events}
        return build(spec), closes, dict(zip(events, surprises))

    def test_a_fit_in_the_h1_direction_makes_the_prediction_stricter(self):
        panel, closes, surprises = self._four(h1_direction=True)
        cal = prediction.calibrate(panel, closes, surprises, p80=0.15)
        assert cal["fit"] is not None
        assert cal["X"] < cal["median_headroom"] and cal["Y"] > cal["median_rho_bar"]

    def test_a_fit_against_h1_can_never_make_it_easier(self):
        panel, closes, surprises = self._four(h1_direction=False)
        cal = prediction.calibrate(panel, closes, surprises, p80=0.15)
        assert cal["X"] == pytest.approx(cal["median_headroom"])
        assert cal["Y"] == pytest.approx(cal["median_rho_bar"])

    def test_only_releases_closing_in_week_five_and_task_days_asked_by_then(self):
        spec = [("KXCPIYOY-26AUG", 10, SEPT, 0.5), ("KXCPIYOY-26SEP", 10, SEPT, 0.5),
                ("KXU3-26OCT", 10, OCT, 0.5)]
        closes = {"KXCPIYOY-26AUG": close(9, 11), "KXCPIYOY-26SEP": close(10, 14),
                  "KXU3-26OCT": close(10, 2)}
        cal = prediction.calibrate(build(spec), closes, {}, p80=0.2)
        assert [e["event"] for e in cal["events"]] == ["KXCPIYOY-26AUG"]

    def test_a_decision_or_a_commodity_is_not_a_release(self):
        spec = [("KXFEDDECISION-26SEP", 10, SEPT, 0.5), ("KXAAAGASWNJ-26SEP07", 10, SEPT, 0.5)]
        closes = {"KXFEDDECISION-26SEP": close(9, 16), "KXAAAGASWNJ-26SEP07": close(9, 7)}
        cal = prediction.calibrate(build(spec), closes, {}, p80=0.2)
        assert cal["made"] is False and cal["events"] == []

    def test_the_statement_carries_every_number(self):
        text = prediction.statement(0.123456, 0.05, 0.9)
        assert "0.123456" in text and "0.050000" in text and "0.900000" in text
        assert prediction.HOLDOUT_FIRST_ASK in text

    def test_the_threshold_prints_exactly_as_registered(self):
        """Deviation 18 registers 0.2425625; six decimals would print 0.242562."""
        assert "0.2425625" in prediction.statement(prediction.REGISTERED_P80, 0.1, 0.9)


class TestEvaluation:
    PRED = {"threshold_p80": 0.20, "X": 0.30, "Y": 0.50}

    def test_the_first_qualifying_release_decides(self):
        spec = [("KXCPIYOY-26SEP", 12, OCT, 0.95), ("KXU3-26OCT", 12, OCT, 0.05)]
        closes = {"KXCPIYOY-26SEP": close(10, 14), "KXU3-26OCT": close(11, 6)}
        out = prediction.evaluate(build(spec), closes,
                                  {"KXCPIYOY-26SEP": 0.25, "KXU3-26OCT": 0.30}, self.PRED)
        assert out["deciding_event"]["event"] == "KXCPIYOY-26SEP"
        assert out["verdict"] == "HIT"

    def test_a_miss_is_a_miss(self):
        spec = [("KXCPIYOY-26SEP", 12, OCT, 0.05)]
        out = prediction.evaluate(build(spec), {"KXCPIYOY-26SEP": close(10, 14)},
                                  {"KXCPIYOY-26SEP": 0.25}, self.PRED)
        assert out["verdict"] == "MISS"

    def test_a_release_below_the_threshold_does_not_decide(self):
        spec = [("KXCPIYOY-26SEP", 12, OCT, 0.95)]
        out = prediction.evaluate(build(spec), {"KXCPIYOY-26SEP": close(10, 14)},
                                  {"KXCPIYOY-26SEP": 0.19}, self.PRED)
        assert out["verdict"] == "UNTESTED"

    def test_the_holdout_sees_only_task_days_asked_after_the_prediction(self):
        """A question asked in week 5 and settling in week 7 has an outcome nobody
        knew on 2 Oct -- but its week-5 forecasts are not the holdout."""
        spec = [("KXCPIYOY-26SEP", 12, SEPT, 0.95), ("KXCPIYOY-26SEP", 3, OCT, 0.95)]
        out = prediction.evaluate(build(spec), {"KXCPIYOY-26SEP": close(10, 14)},
                                  {"KXCPIYOY-26SEP": 0.25}, self.PRED)
        assert out["holdout_events"][0]["task_days"] == 3
        assert out["verdict"] == "UNTESTED"

    def test_a_release_after_the_freeze_is_too_late(self):
        spec = [("KXCPIYOY-26DEC", 12, OCT, 0.95)]
        out = prediction.evaluate(build(spec), {"KXCPIYOY-26DEC": datetime(2027, 1, 13, tzinfo=UTC)},
                                  {"KXCPIYOY-26DEC": 0.9}, self.PRED)
        assert out["verdict"] == "UNTESTED" and out["holdout_events"] == []


class TestTheRegisteredThreshold:
    def test_matches_the_recorded_reference_releases(self):
        from neff import h1, surprise
        from neff.store import JsonlStore

        rows = [r for r in JsonlStore(h1.RELEASE_SURPRISE_PATH).read() if r.get("role") == "reference"]
        if not rows or prediction.REGISTERED_P80 is None:
            pytest.skip("reference releases not recorded yet")
        recomputed = surprise.percentile_80(r.get("surprise") for r in rows)
        assert recomputed == pytest.approx(prediction.REGISTERED_P80, abs=1e-12)

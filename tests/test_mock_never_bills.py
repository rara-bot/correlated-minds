"""A mock call spends no money, so it must not book any.

This has now happened twice, and the second time is the reason this file exists.

The 17 Aug mock run booked $0.055 against the budget and was archived by hand in
commit 38ff332, "Reset ledger: archive phantom spend from the mock run". That
commit's own message identifies the cause -- "the mock provider still prices and
records its calls" -- and leaves it in place. So the 22 Aug mock run booked
another $0.0102 straight back into data/ledger.jsonl, where it stayed until a
pre-freeze reconciliation noticed the ledger held 228 rows against 180 stored
observations.

Why it is not merely untidy: `Ledger.check` RAISES rather than warns, and the arm
caps are hard stops. Spend that never happened still consumes that headroom, so
phantom rows bring forward the day collection halts -- and a halt in November is
unrecoverable, because every question is registered before its outcome exists.

Archiving is a cleanup. This is the fix.
"""

import json

import pytest

from neff import config
from neff.ledger import Ledger
from neff.providers import ask


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.jsonl", cap_usd=100.0,
                  arm_caps=dict(config.ARM_CAPS_USD))


@pytest.fixture
def spec():
    return config.primary_panel()[0]


class TestMockCallsDoNotBill:
    def test_a_mock_call_records_no_spend(self, ledger, spec):
        obs = ask(spec=spec, task_id="t1", prompt="Q?", ledger=ledger,
                  arm=config.PRE_REGISTRATION_ARM, use_mock=True)
        assert obs.error is None, obs.error
        assert ledger.spent == 0.0, "a mock call booked real spend"

    def test_a_mock_run_writes_no_ledger_rows(self, ledger, spec, tmp_path):
        for i in range(5):
            ask(spec=spec, task_id=f"t{i}", prompt="Q?", ledger=ledger,
                arm=config.PRE_REGISTRATION_ARM, use_mock=True)
        path = tmp_path / "ledger.jsonl"
        rows = [l for l in path.read_text().splitlines() if l.strip()] if path.exists() else []
        assert rows == [], f"mock run left {len(rows)} ledger rows"

    def test_the_observation_still_carries_a_notional_price(self, ledger, spec):
        """Mock observations are the input to day-pricing, so a synthetic row
        with no cost would understate a projected day. The distinction is that a
        notional price on an archived synthetic row is a projection, while a row
        in the ledger is a claim that money moved."""
        obs = ask(spec=spec, task_id="t1", prompt="Q?" * 50, ledger=ledger,
                  arm=config.PRE_REGISTRATION_ARM, use_mock=True)
        assert obs.usd > 0.0

    def test_mock_calls_do_not_consume_arm_headroom(self, ledger, spec):
        arm = config.PRE_REGISTRATION_ARM
        for i in range(20):
            ask(spec=spec, task_id=f"t{i}", prompt="Q?", ledger=ledger,
                arm=arm, use_mock=True)
        assert ledger.arm_spent(arm) == 0.0


class TestTheRealLedgerIsClean:
    """The committed ledger must contain only calls that actually happened."""

    def test_no_mock_shaped_rows_survive_in_the_ledger(self):
        rows = [json.loads(l) for l in
                open(config.LEDGER_PATH, encoding="utf-8") if l.strip()]
        mock_dir = config.LEDGER_PATH.parent / "pilot_mock"
        archived = set()
        for f in sorted(mock_dir.glob("ledger_mock_*.jsonl")):
            archived |= {json.dumps(json.loads(l), sort_keys=True)
                         for l in open(f, encoding="utf-8") if l.strip()}
        live = {json.dumps(r, sort_keys=True) for r in rows}
        assert not (live & archived), \
            "archived mock spend is back in the live ledger"

    def test_the_ledger_reconciles_against_what_was_actually_collected(self):
        """208 billed calls = 180 stored observations + 30 verification calls
        - 2 provider failures that were never billed.

        A reviewer can run this arithmetic from the public files, which is the
        point: PREREGISTRATION.md 3.5 states the pilot's exact extent, and a
        ledger that does not reconcile against it would be the first thing a
        skeptic finds.
        """
        led = [l for l in open(config.LEDGER_PATH, encoding="utf-8") if l.strip()]
        obs = [json.loads(l) for l in open(config.OBS_PATH, encoding="utf-8") if l.strip()]
        billed_failures = sum(1 for o in obs if o.get("error"))
        assert len(led) == len(obs) + 30 - 2, (
            f"ledger {len(led)} does not reconcile against {len(obs)} observations "
            f"({billed_failures} carried an error)"
        )

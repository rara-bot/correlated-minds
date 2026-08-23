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

    def test_every_call_that_reached_a_provider_was_billed(self):
        """The durable identity: ledger rows >= observations that got a response.

        A call bills when the API answers, even if parsing the answer then
        fails -- so an errored observation is usually still a billed one. Only a
        call that never got a response (timeout, dead key) goes unbilled, and it
        carries `input_tokens == 0`.

        THIS ASSERTION HAS TO SURVIVE 15 WEEKS OF COLLECTION, which an exact row
        count does not. The daily workflow runs this suite at step 5, BEFORE it
        collects at step 7, so a test that drifts out of true with the data files
        does not merely go red -- it halts collection, and a day not collected
        cannot be recollected because every question is registered before its
        outcome exists. An earlier version of this test asserted
        `len(ledger) == len(observations) + 30 - 2`, which held only for the
        pilot snapshot and would have failed permanently on the first unanswered
        call of the study.
        """
        led = [l for l in open(config.LEDGER_PATH, encoding="utf-8") if l.strip()]
        obs = [json.loads(l) for l in open(config.OBS_PATH, encoding="utf-8") if l.strip()]
        reached = [o for o in obs if (o.get("input_tokens") or 0) > 0]
        assert len(led) >= len(reached), (
            f"{len(reached)} observations reached a provider but the ledger holds "
            f"only {len(led)} rows -- real spend is going unrecorded"
        )

    def test_the_pilot_snapshot_still_matches_what_3_5_froze(self):
        """PREREGISTRATION.md 3.5 states the pilot's exact extent, and that
        statement is now hashed. Until collection starts, the files must still
        say what the frozen document says they say.

        Skips once collection begins: after that the files legitimately grow and
        3.5's numbers describe the pilot, not the current file length.
        """
        obs = [json.loads(l) for l in open(config.OBS_PATH, encoding="utf-8") if l.strip()]
        if any(o.get("arm") == config.PRIMARY_ARM for o in obs):
            pytest.skip("collection has started; 3.5 describes the pilot, not the file")
        led = [l for l in open(config.LEDGER_PATH, encoding="utf-8") if l.strip()]
        reached = [o for o in obs if (o.get("input_tokens") or 0) > 0]
        assert len(obs) == 180
        assert len(led) == 208
        assert len(reached) + 30 == len(led), "pilot reconciliation drifted"

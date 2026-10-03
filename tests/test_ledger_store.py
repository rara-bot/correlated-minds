"""Tests for cost enforcement and the append-only record.

These two modules protect the two things that cannot be recovered if lost:
the $200, and 15 weeks of forecasts.
"""

import json
import threading

import pytest

from neff.ledger import BudgetExceeded, Ledger, Price
from neff.store import (
    JsonlStore,
    Observation,
    Resolution,
    Task,
    observation_id,
)


# --- pricing ----------------------------------------------------------------

def test_price_basic_arithmetic():
    price = Price(input_per_mtok=3.0, output_per_mtok=15.0)
    # 1M input + 1M output = 3 + 15
    assert price.estimate(1_000_000, 1_000_000) == pytest.approx(18.0)


def test_cached_input_bills_at_reduced_rate():
    price = Price(input_per_mtok=10.0, output_per_mtok=0.0, cached_input_mult=0.1)
    full = price.estimate(1_000_000, 0)
    cached = price.estimate(1_000_000, 0, cached_input_tokens=1_000_000)
    assert full == pytest.approx(10.0)
    assert cached == pytest.approx(1.0)


def test_batch_halves_cost():
    price = Price(input_per_mtok=4.0, output_per_mtok=20.0, batch_mult=0.5)
    assert price.estimate(500_000, 100_000, batch=True) == pytest.approx(
        price.estimate(500_000, 100_000) * 0.5
    )


def test_cached_tokens_cannot_exceed_input():
    price = Price(1.0, 1.0)
    with pytest.raises(ValueError):
        price.estimate(100, 10, cached_input_tokens=200)


def test_realistic_per_call_cost_is_in_expected_range():
    """Sanity-check the budget model in BUDGET.md: a mid-tier structured call
    with a cached prefix should land near a tenth of a cent."""
    price = Price(input_per_mtok=0.75, output_per_mtok=3.40)
    usd = price.estimate(
        input_tokens=6000, output_tokens=200, cached_input_tokens=4000, batch=True
    )
    assert 0.0005 < usd < 0.005


# --- the hard cap -----------------------------------------------------------

def test_ledger_blocks_call_that_would_breach_cap(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl", cap_usd=1.0)
    ledger.record("m", "arm", 0, 0, usd=0.9)
    with pytest.raises(BudgetExceeded):
        ledger.record("m", "arm", 0, 0, usd=0.2)
    assert ledger.spent == pytest.approx(0.9)   # rejected spend not recorded


def test_check_does_not_record(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl", cap_usd=10.0)
    ledger.check(5.0)
    assert ledger.spent == 0.0


def test_per_arm_cap_enforced_independently(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl", cap_usd=100.0, arm_caps={"pilot": 1.0})
    ledger.record("m", "pilot", 0, 0, usd=0.9)
    with pytest.raises(BudgetExceeded):
        ledger.record("m", "pilot", 0, 0, usd=0.5)
    # a different arm is unaffected by the pilot sub-cap
    ledger.record("m", "ws1_prospective", 0, 0, usd=5.0)
    assert ledger.spent == pytest.approx(5.9)


def test_spend_survives_restart(tmp_path):
    """The realistic failure: a cron job restarts and forgets what it spent."""
    path = tmp_path / "l.jsonl"
    first = Ledger(path, cap_usd=10.0)
    first.record("m", "arm", 0, 0, usd=7.5)

    second = Ledger(path, cap_usd=10.0)
    assert second.spent == pytest.approx(7.5)
    assert second.remaining == pytest.approx(2.5)
    with pytest.raises(BudgetExceeded):
        second.record("m", "arm", 0, 0, usd=3.0)


def test_torn_final_line_does_not_prevent_startup(tmp_path):
    path = tmp_path / "l.jsonl"
    ledger = Ledger(path, cap_usd=10.0)
    ledger.record("m", "arm", 0, 0, usd=1.0)
    with path.open("a") as fh:
        fh.write('{"usd": 2.0, "arm": "arm"')   # interrupted write, no newline/close

    reloaded = Ledger(path, cap_usd=10.0)
    assert reloaded.spent == pytest.approx(1.0)


def test_concurrent_records_cannot_overspend(tmp_path):
    """Two threads must not both pass the check and jointly breach the cap."""
    ledger = Ledger(tmp_path / "l.jsonl", cap_usd=1.0)
    errors = []

    def worker():
        for _ in range(50):
            try:
                ledger.record("m", "arm", 0, 0, usd=0.01)
            except BudgetExceeded:
                pass
            except Exception as exc:      # pragma: no cover
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert ledger.spent <= 1.0 + 1e-9


def test_summary_reports_by_arm(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl", cap_usd=200.0)
    ledger.record("m", "pilot", 0, 0, usd=2.0)
    ledger.record("m", "ws1_prospective", 0, 0, usd=8.0)
    summary = ledger.summary()
    assert summary["spent_usd"] == pytest.approx(10.0)
    assert summary["remaining_usd"] == pytest.approx(190.0)
    assert summary["by_arm"]["pilot"] == pytest.approx(2.0)
    assert summary["pct_used"] == pytest.approx(5.0)


# --- the append-only record -------------------------------------------------

def test_observation_id_is_deterministic_and_distinct():
    a = observation_id("task1", "claude_sonnet", 0)
    b = observation_id("task1", "claude_sonnet", 0)
    c = observation_id("task1", "claude_sonnet", 1)
    d = observation_id("task1", "gemini_flash", 0)
    assert a == b
    assert len({a, c, d}) == 3


def test_store_roundtrip(tmp_path):
    store = JsonlStore(tmp_path / "obs.jsonl")
    task = Task(task_id="t1", kind="macro", prompt="Will CPI exceed 3%?")
    store.append(task)
    records = store.read_all()
    assert len(records) == 1
    assert records[0]["task_id"] == "t1"
    assert records[0]["kind"] == "macro"


def test_store_append_only_never_mutates(tmp_path):
    store = JsonlStore(tmp_path / "obs.jsonl")
    store.append(Task(task_id="t1", kind="macro", prompt="a"))
    store.append(Task(task_id="t1", kind="macro", prompt="revised"))
    records = store.read_all()
    assert len(records) == 2                 # both kept; nothing overwritten
    assert records[0]["prompt"] == "a"


def test_store_skips_malformed_line_by_default(tmp_path):
    path = tmp_path / "obs.jsonl"
    store = JsonlStore(path)
    store.append(Task(task_id="t1", kind="macro", prompt="a"))
    with path.open("a") as fh:
        fh.write("{not json\n")
    store.append(Task(task_id="t2", kind="macro", prompt="b"))

    assert len(store.read_all()) == 2
    with pytest.raises(ValueError):
        store.read_all(strict=True)


def test_existing_ids_enables_idempotent_rerun(tmp_path):
    store = JsonlStore(tmp_path / "obs.jsonl")
    for i in range(3):
        store.append(
            Observation(
                obs_id=observation_id(f"t{i}", "m", 0),
                task_id=f"t{i}",
                model_key="m",
                model_id_returned="m-1",
                provider="p",
                prompt_variant=0,
                forecast=0.5,
                direction="up",
                confidence=0.6,
            )
        )
    seen = store.existing_ids("obs_id")
    assert len(seen) == 3
    assert observation_id("t1", "m", 0) in seen


def test_append_many_writes_all(tmp_path):
    store = JsonlStore(tmp_path / "r.jsonl")
    written = store.append_many(
        [Resolution(task_id=f"t{i}", outcome=float(i)) for i in range(5)]
    )
    assert written == 5
    assert store.count() == 5


def test_integrity_report(tmp_path):
    path = tmp_path / "obs.jsonl"
    store = JsonlStore(path)
    store.append(Task(task_id="t1", kind="macro", prompt="a"))
    with path.open("a") as fh:
        fh.write("garbage\n")

    report = store.integrity_report()
    assert report["records"] == 2
    assert report["malformed"] == 1
    assert report["bytes"] > 0


def test_concurrent_appends_produce_valid_jsonl(tmp_path):
    """Interleaved writes from the concurrent collector must not tear lines."""
    store = JsonlStore(tmp_path / "obs.jsonl")

    def worker(worker_id: int):
        for i in range(40):
            store.append(Task(task_id=f"w{worker_id}-{i}", kind="macro", prompt="x"))

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    report = store.integrity_report()
    assert report["records"] == 240
    assert report["malformed"] == 0


def test_observation_records_model_id_returned(tmp_path):
    """Silent provider model swaps are the top data-integrity risk in a
    longitudinal panel, so the served id is a first-class field."""
    store = JsonlStore(tmp_path / "obs.jsonl")
    store.append(
        Observation(
            obs_id="x",
            task_id="t",
            model_key="claude_sonnet",
            model_id_returned="claude-sonnet-5-20260101",
            provider="anthropic",
            prompt_variant=0,
            forecast=0.7,
            direction="up",
            confidence=0.8,
        )
    )
    rec = store.read_all()[0]
    assert rec["model_id_returned"] == "claude-sonnet-5-20260101"
    assert rec["model_key"] == "claude_sonnet"

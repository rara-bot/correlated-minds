"""A dry run must not touch the study record.

`--dry-run` is documented as "price the day, ask nothing", and
`require_osf_before_real_collection` lets it past the pre-registration gate on
the explicit grounds that it "touches nothing real". It then appended that day's
questions to `data/tasks.jsonl`, the append-only registry that is part of the
public record.

Two ways that bites:

  * those rows can never acquire observations, because no model was asked. They
    are permanent orphans, and a reviewer counting tasks against observations
    finds a gap with no explanation in the log.
  * SETUP.md step 5 instructs the operator to smoke-test the GitHub workflow with
    `dry_run` ticked. The workflow ends with `git add -A data/` and a commit, so
    that rehearsal would have published a batch of questions to the public
    repository dated BEFORE the pre-registration was frozen -- against a study
    whose entire claim is that the plan came first.

The pricing arithmetic is unaffected; only the writing is.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from neff import collect
from neff.config import RunConfig
from neff.store import Task


def _task(n):
    close = datetime.now(timezone.utc) + timedelta(days=30)
    return Task(
        task_id=f"t{n}",
        kind="event",
        prompt="Will X happen?",
        resolves_after=close.isoformat(),
        source="kalshi",
        source_ref=f"TICKER-{n}",
        outcome_kind="binary",
        market_implied=None,
        state={"ladder_distance": 0.25, "vix_level": 15.0,
               "realized_vol_20d": 0.06, "days_out": 30.0,
               "asked_on": "2026-08-21"},
    )


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect every write path into a temp directory."""
    tasks = tmp_path / "tasks.jsonl"
    obs = tmp_path / "observations.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(collect, "TASKS_PATH", tasks)
    monkeypatch.setattr(collect, "OBS_PATH", obs)
    monkeypatch.setattr(collect, "LEDGER_PATH", ledger)
    monkeypatch.setattr(collect, "build_daily_tasks",
                        lambda **kw: [_task(i) for i in range(5)])
    return {"tasks": tasks, "obs": obs, "ledger": ledger}


def _run(dry_run):
    return collect.run_day(
        config=RunConfig(arm="pilot", dry_run=dry_run, tasks_per_day=5),
        as_of=date(2026, 8, 21),
    )


class TestDryRunWritesNothing:
    def test_task_registry_is_untouched(self, sandbox):
        _run(dry_run=True)
        assert not sandbox["tasks"].exists() or sandbox["tasks"].read_text() == "", (
            "a dry run appended to the append-only task registry"
        )

    def test_no_observations_are_written(self, sandbox):
        _run(dry_run=True)
        assert not sandbox["obs"].exists() or sandbox["obs"].read_text() == ""

    def test_nothing_is_charged(self, sandbox):
        _run(dry_run=True)
        assert not sandbox["ledger"].exists() or sandbox["ledger"].read_text() == ""

    def test_repeated_dry_runs_stay_clean(self, sandbox):
        """The workflow's dry_run input can be triggered any number of times."""
        for _ in range(3):
            _run(dry_run=True)
        assert not sandbox["tasks"].exists() or sandbox["tasks"].read_text() == ""


class TestDryRunStillPrices:
    """Not writing must not mean not working -- the estimate is the point."""

    def test_returns_a_positive_estimate(self, sandbox):
        out = _run(dry_run=True)
        assert out["dry_run"] is True
        assert out["estimated_usd"] > 0

    def test_counts_the_tasks_it_priced(self, sandbox):
        out = _run(dry_run=True)
        assert out["tasks"] == 5
        assert out["observations"] == 0

    def test_estimate_scales_with_the_panel(self, sandbox):
        """Ten models must be priced, not nine -- the collected roster is what
        the money is actually spent on."""
        from neff.config import enabled_panel

        out = _run(dry_run=True)
        one = collect.run_day(
            config=RunConfig(arm="pilot", dry_run=True, tasks_per_day=5,
                             model_keys=[enabled_panel()[0].key]),
            as_of=date(2026, 8, 21),
        )
        assert out["estimated_usd"] > one["estimated_usd"]


class TestRealRunStillRegisters:
    """The guard must be specific to dry runs. The task file existing before the
    observations is what makes 'the question predates the answer' checkable."""

    def test_mock_run_registers_tasks(self, sandbox):
        collect.run_day(
            config=RunConfig(arm="pilot", dry_run=False, tasks_per_day=5),
            as_of=date(2026, 8, 21),
            use_mock=True,
        )
        assert sandbox["tasks"].exists()
        assert len(sandbox["tasks"].read_text().strip().splitlines()) == 5

    def test_tasks_are_written_before_observations(self, sandbox):
        collect.run_day(
            config=RunConfig(arm="pilot", dry_run=False, tasks_per_day=5),
            as_of=date(2026, 8, 21),
            use_mock=True,
        )
        assert sandbox["tasks"].stat().st_mtime <= sandbox["obs"].stat().st_mtime

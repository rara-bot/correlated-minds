"""A second run on the same day finishes it. It must not extend it.

The 20:00 UTC backup run added on 3 Sep 2026 exists so that a day whose first
attempt died on something transient is not lost -- a lost day is unrecoverable,
because a forecast cannot honestly be back-dated.

It was safe on the assumption that `neff.collect` is idempotent. It is, at the
observation level: `observation_id` is content-addressed. It was NOT idempotent
at the task level. `build_daily_tasks` selects from live sources, so calling it
again hours later can return questions that did not exist the first time.

That is not hypothetical either. On 3 Sep 2026 the 17:04 run registered 25 tasks
and the 22:24 backup added 5 more -- five rungs of a Kalshi housing-starts
ladder that had appeared in between. The day closed with 30 tasks instead of 25,
the extra five carrying a market-state snapshot five hours removed from the rest
of the day. Nothing was lost and nothing was double-counted; the sampling design
simply changed underneath the study, on one day, silently.

So: if a day already has registered tasks, those tasks ARE the day.
"""

from datetime import datetime, timedelta, timezone

import pytest

from neff import collect
from neff.config import RunConfig, mock_sandbox
from neff.store import JsonlStore, Task

ARM = "pilot"


def _task(ref):
    close = datetime.now(timezone.utc) + timedelta(days=30)
    return Task(
        task_id=f"id-{ref}",
        kind="event",
        prompt="Will X happen?",
        resolves_after=close.isoformat(),
        source="kalshi",
        source_ref=ref,
        outcome_kind="binary",
        state={"ladder_distance": 0.25, "vix_level": 15.0,
               "realized_vol_20d": 0.06, "days_out": 30.0},
    )


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, "TASKS_PATH", tmp_path / "tasks.jsonl")
    monkeypatch.setattr(collect, "OBS_PATH", tmp_path / "observations.jsonl")
    monkeypatch.setattr(collect, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    # Every run below is `use_mock=True`, which writes to the mock sandbox beside
    # those paths, not to them.
    return mock_sandbox(tmp_path / "x").parent


def _serve(monkeypatch, refs, calls=None):
    def _build(**kw):
        if calls is not None:
            calls.append(list(refs))
        return [_task(r) for r in refs]
    monkeypatch.setattr(collect, "build_daily_tasks", _build)


def _run(**kw):
    return collect.run_day(
        config=RunConfig(arm=ARM, tasks_per_day=25, model_keys=["gpt_small"], replicates_per_day=0),
        use_mock=True,
        **kw,
    )


def _tasks_on_disk(sandbox):
    return JsonlStore(sandbox / "tasks.jsonl").read_all()


class TestASecondRunReusesTheDay:
    def test_new_questions_appearing_later_are_not_added(self, sandbox, monkeypatch):
        _serve(monkeypatch, ["A", "B", "C"])
        _run()
        assert len(_tasks_on_disk(sandbox)) == 3

        # The 22:24 case: the ladder has appeared since the morning run.
        _serve(monkeypatch, ["A", "B", "C", "LADDER-1", "LADDER-2"])
        _run()

        refs = {t["source_ref"] for t in _tasks_on_disk(sandbox)}
        assert refs == {"A", "B", "C"}, "a rerun extended the day"

    def test_the_selector_is_not_even_consulted_on_a_rerun(
        self, sandbox, monkeypatch
    ):
        """Selection hits live sources. A finished day must not re-roll it."""
        _serve(monkeypatch, ["A", "B"])
        _run()
        calls = []
        _serve(monkeypatch, ["A", "B", "C"], calls=calls)
        _run()
        assert calls == [], "build_daily_tasks was called on a rerun"

    def test_a_rerun_collects_no_duplicate_observations(self, sandbox, monkeypatch):
        _serve(monkeypatch, ["A", "B"])
        first = _run()
        _run()
        obs = JsonlStore(sandbox / "observations.jsonl").read_all()
        assert len(obs) == first["observations"]
        assert len({o["obs_id"] for o in obs}) == len(obs)


class TestTheBackupStillDoesItsJob:
    def test_a_day_with_nothing_registered_gets_a_fresh_selection(
        self, sandbox, monkeypatch
    ):
        """The whole point of the backup: the morning run died before writing."""
        _serve(monkeypatch, ["A", "B", "C"])
        _run()
        assert len(_tasks_on_disk(sandbox)) == 3

    def test_a_half_finished_day_is_completed_against_the_same_tasks(
        self, sandbox, monkeypatch
    ):
        """Observations missing, tasks present -- fill the gaps, add no questions."""
        _serve(monkeypatch, ["A", "B"])
        _run()
        obs_path = sandbox / "observations.jsonl"
        rows = JsonlStore(obs_path).read_all()
        kept = rows[: len(rows) // 2]
        obs_path.write_text(
            "".join(__import__("json").dumps(r) + "\n" for r in kept),
            encoding="utf-8",
        )

        _serve(monkeypatch, ["A", "B", "C"])
        summary = _run()

        assert summary["observations"] > 0, "the backup collected nothing"
        assert len(_tasks_on_disk(sandbox)) == 2, "the backup added questions"
        after = JsonlStore(obs_path).read_all()
        assert len(after) == len(rows)
        assert len({o["obs_id"] for o in after}) == len(after)

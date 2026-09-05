"""A mock run must not write to the study's files.

The sibling of `test_mock_never_bills.py`, and the same defect one layer out.
That file stopped fabricated calls from booking spend; this one stops fabricated
forecasts from landing in the record they would be read out of.

`--mock` used to append straight into `data/observations.jsonl` and
`data/tasks.jsonl` -- the append-only files whose contents ARE the evidence.
Everything protecting the study from that was downstream: rows carry
provider="mock", `panel.load_panel` filters them, `preflight` counts them. Each
of those is a reader remembering to exclude something, and none of them help the
reviewer who clones the repository and reads the file.

The failure mode is not hypothetical. A mock run has twice been mistaken for a
real one -- 140 fabricated forecasts sat in the study log on 17 Aug, and the
22 Aug run put $0.0102 of phantom spend into the ledger -- both times because
synthetic output was sitting exactly where real output lives.

It also has a deadline. The daily workflow ends with `git add -A data/` and a
push, so a mock run on the collection host does not merely dirty a local file; it
publishes fabricated forecasts to the public repository of a registered study.
"""

import json
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest

from neff import collect, config
from neff.config import RunConfig, mock_sandbox
from neff.store import JsonlStore, Task

LIVE_FILES = ("tasks.jsonl", "observations.jsonl", "ledger.jsonl", "resolutions.jsonl")


def _task(n):
    close = datetime.now(timezone.utc) + timedelta(days=30)
    return Task(
        task_id=f"mock-guard-{n}",
        kind="event",
        prompt="Will X happen?",
        resolves_after=close.isoformat(),
        source="kalshi",
        source_ref=f"REF-{n}",
        outcome_kind="binary",
        state={"ladder_distance": 0.25, "vix_level": 15.0,
               "realized_vol_20d": 0.06, "days_out": 30.0},
    )


@pytest.fixture
def record(tmp_path, monkeypatch):
    """A stand-in for data/, pre-seeded so any write to it is detectable.

    The real files are deliberately not used: a test that proves the guard by
    appending to data/observations.jsonl when the guard is broken would corrupt
    the study to report that the study can be corrupted.
    """
    live = tmp_path / "data"
    live.mkdir()
    seeded = {}
    for name in LIVE_FILES:
        path = live / name
        path.write_text('{"sentinel": true}\n', encoding="utf-8")
        seeded[name] = path.read_bytes()

    monkeypatch.setattr(collect, "TASKS_PATH", live / "tasks.jsonl")
    monkeypatch.setattr(collect, "OBS_PATH", live / "observations.jsonl")
    monkeypatch.setattr(collect, "LEDGER_PATH", live / "ledger.jsonl")
    monkeypatch.setattr(collect, "RESOLUTIONS_PATH", live / "resolutions.jsonl")
    monkeypatch.setattr(collect, "build_daily_tasks",
                        lambda **kw: [_task(i) for i in range(3)])
    return {"dir": live, "seeded": seeded, "mock": live / config.MOCK_DIRNAME}


def _run_mock():
    return collect.run_day(
        config=RunConfig(arm="pilot", tasks_per_day=3, replicates_per_day=0,
                         model_keys=[config.enabled_panel()[0].key]),
        as_of=date(2026, 8, 21),
        use_mock=True,
    )


def _unchanged(record):
    return {name: (record["dir"] / name).read_bytes() == blob
            for name, blob in record["seeded"].items()}


class TestAMockRunLeavesTheRecordAlone:
    def test_no_live_file_is_modified(self, record):
        _run_mock()
        changed = [name for name, same in _unchanged(record).items() if not same]
        assert changed == [], f"a mock run wrote to {changed}"

    def test_the_fabricated_rows_exist_in_the_sandbox(self, record):
        """Contained, not discarded -- `--mock` still has to be a usable rehearsal."""
        rows = JsonlStore(record["mock"] / "observations.jsonl").read_all()
        assert rows == []
        _run_mock()
        rows = JsonlStore(record["mock"] / "observations.jsonl").read_all()
        assert len(rows) == 3
        assert {r["provider"] for r in rows} == {"mock"}
        assert len(JsonlStore(record["mock"] / "tasks.jsonl").read_all()) == 3

    def test_a_repeated_mock_run_is_still_idempotent(self, record):
        """Containment must not cost the property the sandbox is a copy of."""
        _run_mock()
        _run_mock()
        rows = JsonlStore(record["mock"] / "observations.jsonl").read_all()
        assert len(rows) == 3, "a second mock run duplicated observations"
        assert all(same for same in _unchanged(record).values())

    def test_resolution_is_contained_too(self, record, monkeypatch):
        """`main` resolves after collecting, and a resolution is a write."""
        from neff.sources import kalshi

        monkeypatch.setattr(kalshi, "fetch_settlement", lambda ref: 1.0)
        _run_mock()
        out = collect.resolve_outcomes(use_mock=True)

        assert out["resolved"] == 3
        assert len(JsonlStore(record["mock"] / "resolutions.jsonl").read_all()) == 3
        assert _unchanged(record)["resolutions.jsonl"], \
            "a mock run appended to the real resolution record"

    def test_a_real_run_is_unaffected(self, record, monkeypatch):
        """The guard must be specific to mock. A study that stopped collecting
        would fail in exactly the same direction as one that collected junk."""
        from neff import providers

        monkeypatch.setattr(providers, "PROVIDERS",
                            {**providers.PROVIDERS,
                             config.enabled_panel()[0].provider: providers.MockProvider()})
        collect.run_day(
            config=RunConfig(arm="pilot", tasks_per_day=3, replicates_per_day=0,
                             model_keys=[config.enabled_panel()[0].key]),
            as_of=date(2026, 8, 21),
            use_mock=False,
        )
        obs = [r for r in JsonlStore(record["dir"] / "observations.jsonl").read_all()
               if r.get("obs_id")]          # the seeded sentinel has none
        assert len(obs) == 3, "a real run stopped writing to the study record"
        assert not (record["mock"] / "observations.jsonl").exists()


class TestTheSandboxIsWhereItSaysItIs:
    def test_it_is_beside_the_record_and_is_not_the_record(self):
        for path in (config.OBS_PATH, config.TASKS_PATH,
                     config.LEDGER_PATH, config.RESOLUTIONS_PATH):
            sandboxed = mock_sandbox(path)
            assert sandboxed != path
            assert sandboxed.parent == path.parent / config.MOCK_DIRNAME
            assert sandboxed.name == path.name

    def test_it_is_not_the_frozen_pilot_archive(self):
        """PREREGISTRATION.md 3.5 describes data/pilot_mock/ as the pilot's
        archived mock output, and `test_mock_never_bills` reads it to check the
        live ledger against it. It is a fixed record; nothing writes to it."""
        assert mock_sandbox(config.OBS_PATH).parent != config.DATA_DIR / "pilot_mock"

    def test_git_will_not_commit_it(self):
        """The last line of defence. The daily workflow ends in
        `git add -A data/`, so an unignored sandbox would publish fabricated
        forecasts to the repository of a registered study on the first mock run
        that happened on the collection host."""
        probe = mock_sandbox(config.OBS_PATH)
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(probe)],
            cwd=config.ROOT, capture_output=True,
        )
        assert result.returncode == 0, f"{probe} is not gitignored"


class TestTheRealRecordHasNoMockRows:
    def test_the_committed_observations_are_all_real(self):
        """The standing check on the actual file, not on a temp copy of it."""
        rows = [json.loads(l) for l in
                open(config.OBS_PATH, encoding="utf-8") if l.strip()]
        mock = [r for r in rows
                if str(r.get("provider", "")).lower() == "mock"
                or str(r.get("model_id_returned", "")).endswith("-mock")]
        assert mock == [], f"{len(mock)} fabricated observation(s) in the record"

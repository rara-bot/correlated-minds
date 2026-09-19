"""The Week-5 publisher refuses anything but the current record, and its registered look runs.

Two things are pinned here -- the same two `tests/test_unblinded_path.py` pins for
the December look, for the one that comes first:

  1. THE GATES HOLD. `--publish` refuses before 2026-10-02 20:00 UTC and a second
     time (PREREGISTRATION.md 11, deviation 18 (6)), and it refuses on a copy of
     the record that is not current (deviation 22): behind GitHub, 2 October not
     yet collected, a settlement Kalshi has published that the copy has not
     recorded, a calibration release closed but not settled, or settled in part
     so that its surprise cannot be recorded yet. Each refusal happens before
     anything is written or unblinded.

  2. THE PATH RUNS. On a store fabricated in `tmp_path`, `--publish` unblinds,
     calibrates, fits H1 and writes both files. It is exercised here because it
     runs exactly once, on a fixed evening, and a path that has never run is a
     path that might not.

Nothing here opens the real observations or resolutions: the `no_real_outcomes`
fixture fails any test that tries. The real record is never unblinded early --
see deviation 21 for why that rule is written down.
"""
from __future__ import annotations

import functools
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402

sys.path.insert(0, str(ROOT))

from neff import h1, prediction, surprise  # noqa: E402
from neff.config import PRIMARY_ARM  # noqa: E402
from neff.panel import load_panel  # noqa: E402
from neff.sources import kalshi  # noqa: E402
from neff.sources.http import FetchError  # noqa: E402
from neff.store import JsonlStore  # noqa: E402
from scripts import milestones, release_surprise  # noqa: E402
from scripts import week5_prediction as w5  # noqa: E402

UTC = timezone.utc
OPENS = datetime.fromisoformat(prediction.PUBLISH_NOT_BEFORE)
EVENING = OPENS + timedelta(minutes=30)                 # 2026-10-02 20:30 UTC
MODELS = ["claude_haiku", "gpt_mid", "llama", "qwen"]
REAL_OUTCOME_FILES = {(ROOT / "data" / n).resolve() for n in ("observations.jsonl", "resolutions.jsonl")}


@pytest.fixture(autouse=True)
def no_real_outcomes(monkeypatch):
    """Any read of the real observations or resolutions fails the test."""
    original = JsonlStore.read

    def guarded(self, strict=False):
        if Path(self.path).resolve() in REAL_OUTCOME_FILES:
            raise AssertionError(f"a test opened the real record: {self.path}")
        return original(self, strict=strict)

    monkeypatch.setattr(JsonlStore, "read", guarded)


def test_the_guard_itself_trips_before_a_line_is_read():
    for path in REAL_OUTCOME_FILES:
        with pytest.raises(AssertionError, match="opened the real record"):
            next(JsonlStore(path).read())


# --- git, answered from a script rather than a repository --------------------------

class FakeGit:
    """Answers the git calls the publisher makes, as a clean, current copy would."""

    def __init__(self, fetch_ok=True, behind=0, diff="", status="", show=b""):
        self.fetch_ok, self.behind, self.diff, self.status, self.show = (
            fetch_ok, behind, diff, status, show)
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        cmd = args[0]

        def done(rc=0, out=b"", err=b""):
            return subprocess.CompletedProcess(("git",) + args, rc, out, err)

        if cmd == "fetch":
            return done(0) if self.fetch_ok else done(128, err=b"fatal: unable to access github.com")
        if cmd == "merge-base":
            return done(0 if not self.behind else 1)
        if cmd == "rev-list":
            return done(out=str(self.behind).encode())
        if cmd == "diff":
            return done(out=self.diff.encode())
        if cmd == "status":
            return done(out=self.status.encode())
        if cmd == "show":
            return done(0, self.show) if self.show is not None else done(128)
        if cmd == "rev-parse":
            return done(out=b"0f" * 20)
        if cmd == "log":
            return done(out=b"da" * 20)
        raise AssertionError(f"unexpected git call: {args}")


@pytest.fixture
def clean_git(monkeypatch):
    fake = FakeGit()
    monkeypatch.setattr(w5, "_run_git", fake)
    return fake


# --- a small record of questions, fabricated -----------------------------------------

def _task(tid, ref, asked, close, kind="event"):
    return {"task_id": tid, "kind": kind, "prompt": "Q?", "source": "kalshi",
            "source_ref": ref, "asked_at": f"{asked}T17:00:00+00:00",
            "resolves_after": close, "outcome_kind": "binary", "market_implied": None,
            "arm": PRIMARY_ARM, "schema": "v1", "state": {"asked_on": asked}}


PAYROLLS = "KXPAYROLLS-26SEP-T50000"
PAYROLLS_CLOSE = "2026-10-02T12:29:00Z"


# --- 1. the registered refusals --------------------------------------------------------

class TestTheRegisteredRefusals:
    def test_it_refuses_before_the_window(self):
        with pytest.raises(SystemExit) as caught:
            w5.publish(now=OPENS - timedelta(minutes=1))
        assert "on or after" in str(caught.value)

    def test_it_refuses_a_second_time(self, tmp_path, monkeypatch):
        existing = tmp_path / "week5-prediction.json"
        existing.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(w5, "PREDICTION_FILE", existing)
        with pytest.raises(SystemExit) as caught:
            w5.publish(now=EVENING)
        assert "never revised" in str(caught.value)

    def test_a_copy_that_is_not_ready_is_refused_before_anything_is_unblinded(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(w5, "PREDICTION_FILE", tmp_path / "week5-prediction.json")
        monkeypatch.setattr(w5, "readiness", lambda now: {
            "ready": False, "problems": ["this copy is 3 commit(s) behind GitHub"], "notes": []})

        def must_not_run(*a, **k):
            raise AssertionError("ran past a refusal")

        monkeypatch.setattr(w5, "_record_settled_surprises", must_not_run)
        monkeypatch.setattr(w5, "_inputs", must_not_run)
        monkeypatch.setattr(h1, "run", must_not_run)
        with pytest.raises(SystemExit) as caught:
            w5.publish(now=EVENING)
        assert "not ready to publish" in str(caught.value)
        assert "3 commit(s) behind" in str(caught.value)
        assert not (tmp_path / "week5-prediction.json").exists()


# --- 2. the copy must be GitHub's record ------------------------------------------------

class TestTheCopyMustBeGitHubs:
    def test_github_unreachable_is_not_assumed_current(self, monkeypatch):
        monkeypatch.setattr(w5, "_run_git", FakeGit(fetch_ok=False))
        [problem] = w5.git_problems()
        assert "could not reach GitHub" in problem

    def test_a_copy_behind_github_is_told_to_pull(self, monkeypatch):
        monkeypatch.setattr(w5, "_run_git", FakeGit(behind=3))
        [problem] = w5.git_problems()
        assert "3 commit(s) behind" in problem and "git pull --ff-only" in problem

    def test_an_altered_data_file_is_refused(self, monkeypatch):
        monkeypatch.setattr(w5, "_run_git", FakeGit(diff="data/observations.jsonl\n"))
        [problem] = w5.git_problems()
        assert problem.startswith("data/observations.jsonl differs")

    def test_rows_this_script_appended_on_an_earlier_attempt_are_allowed(self, tmp_path, monkeypatch):
        upstream = b'{"kalshi_event": "KXCPIYOY-26AUG"}\n'
        (tmp_path / "data").mkdir()
        (tmp_path / w5.SELF_WRITTEN).write_bytes(upstream + b'{"kalshi_event": "KXPAYROLLS-26SEP"}\n')
        monkeypatch.setattr(w5, "ROOT", tmp_path)
        monkeypatch.setattr(w5, "_run_git", FakeGit(diff=w5.SELF_WRITTEN + "\n", show=upstream))
        assert w5.git_problems() == []

    def test_but_a_rewritten_row_is_not(self, tmp_path, monkeypatch):
        upstream = b'{"kalshi_event": "KXCPIYOY-26AUG", "surprise": 0.05}\n'
        (tmp_path / "data").mkdir()
        (tmp_path / w5.SELF_WRITTEN).write_bytes(b'{"kalshi_event": "KXCPIYOY-26AUG", "surprise": 0.5}\n')
        monkeypatch.setattr(w5, "ROOT", tmp_path)
        monkeypatch.setattr(w5, "_run_git", FakeGit(diff=w5.SELF_WRITTEN + "\n", show=upstream))
        [problem] = w5.git_problems()
        assert problem.startswith(w5.SELF_WRITTEN)

    def test_uncommitted_code_and_stray_data_are_refused(self, monkeypatch):
        status = " M neff/panel.py\n?? data/extra.jsonl\n M data/tasks.jsonl\n"
        monkeypatch.setattr(w5, "_run_git", FakeGit(status=status))
        problems = w5.git_problems()
        # The modified tracked data file is judged by the diff against GitHub,
        # which here is empty, so it is not reported twice.
        assert len(problems) == 2
        assert problems[0].startswith("neff/panel.py has uncommitted changes")
        assert problems[1].startswith("data/extra.jsonl is not part of GitHub's record")

    def test_the_first_status_line_keeps_its_leading_column(self, monkeypatch):
        # Porcelain output starts with a space for an unstaged change; a stripped
        # read of it once turned "neff/..." into "eff/...".
        monkeypatch.setattr(w5, "_run_git", FakeGit(status=" M neff/sources/kalshi.py\n"))
        [problem] = w5.git_problems()
        assert problem.startswith("neff/sources/kalshi.py ")

    def test_a_clean_current_copy_passes(self, clean_git):
        assert w5.git_problems() == []


# --- 3. weeks 1-5 end with 2 October's questions -----------------------------------------

class TestWeeksOneToFiveEndWithTheSecond:
    def test_on_the_second_it_waits_for_the_days_collection(self):
        tasks = [_task("a", PAYROLLS, "2026-10-01", PAYROLLS_CLOSE)]
        [problem] = w5.collection_problems(tasks, EVENING)
        assert "2026-10-02's collection is not in this copy" in problem

    def test_once_the_day_is_in_it_does_not(self):
        tasks = [_task("a", PAYROLLS, "2026-10-02", PAYROLLS_CLOSE)]
        assert w5.collection_problems(tasks, EVENING) == []

    def test_a_day_that_never_came_does_not_block_forever(self):
        tasks = [_task("a", PAYROLLS, "2026-10-01", PAYROLLS_CLOSE)]
        assert w5.collection_problems(tasks, datetime(2026, 10, 3, 9, 0, tzinfo=UTC)) == []


# --- 4. no settlement Kalshi has published may be missing ---------------------------------

def _market(status, result="", close=PAYROLLS_CLOSE):
    return {"status": status, "result": result, "close_time": close}


class TestNoPublishedSettlementIsMissing:
    TASKS = [
        _task("p1", PAYROLLS, "2026-10-01", PAYROLLS_CLOSE),
        _task("p2", PAYROLLS, "2026-10-02", PAYROLLS_CLOSE),
        _task("s1", "KXSBUXSAR-26OCT02-T5.13", "2026-09-06", "2026-10-02T03:59:00Z"),
        _task("late", "KXCPIYOY-26OCT-T3.0", "2026-10-02", "2026-10-14T12:29:00Z"),
        _task("f1", "edgar:320193:2026-06-27", "2026-10-02", "", kind="filing"),
    ]

    def _problems(self, now, markets, resolved=()):
        return w5.settlement_problems(self.TASKS, set(resolved), now,
                                      market=lambda ref: markets.get(ref))

    def test_a_settlement_the_copy_has_not_recorded_blocks(self):
        [problem] = self._problems(EVENING, {PAYROLLS: _market("finalized", "yes"),
                                             "KXSBUXSAR-26OCT02-T5.13": _market("active")})
        assert f"Kalshi has settled {PAYROLLS}" in problem

    def test_even_for_a_question_that_is_not_a_listed_release(self):
        # The H1 fit uses every resolved task-day of weeks 1-5, not only releases.
        problems = self._problems(EVENING, {PAYROLLS: _market("active"),
                                            "KXSBUXSAR-26OCT02-T5.13": _market("finalized", "no")})
        assert problems == [f"Kalshi has settled KXSBUXSAR-26OCT02-T5.13, but this copy of the "
                            f"record has not recorded it. The daily job records settlements: wait "
                            f"for its next run (or start it: GitHub -> Actions -> daily-collection "
                            f"-> Run workflow), then  git pull --ff-only  and retry."]

    def test_recorded_settlements_are_not_asked_about(self):
        asked = []
        w5.settlement_problems(self.TASKS, {"p1", "p2", "s1"}, EVENING,
                               market=lambda ref: asked.append(ref) or _market("active"))
        assert asked == []

    def test_a_listed_release_closed_but_unsettled_holds_publication(self):
        [problem] = self._problems(EVENING, {PAYROLLS: _market("closed"),
                                             "KXSBUXSAR-26OCT02-T5.13": _market("active")})
        assert "has not settled it yet" in problem

    def test_but_not_past_the_grace(self):
        later = OPENS + w5.SETTLEMENT_GRACE + timedelta(minutes=1)
        assert self._problems(later, {PAYROLLS: _market("closed"),
                                      "KXSBUXSAR-26OCT02-T5.13": _market("active")}) == []

    def test_an_unlisted_question_closed_but_unsettled_does_not_hold_it(self):
        assert self._problems(EVENING, {PAYROLLS: _market("active"),
                                        "KXSBUXSAR-26OCT02-T5.13": _market("closed")}) == []

    def test_a_release_whose_close_moved_out_of_the_window_is_not_calibration(self):
        moved = _market("closed", close="2026-10-09T12:29:00Z")
        assert self._problems(EVENING, {PAYROLLS: moved,
                                        "KXSBUXSAR-26OCT02-T5.13": _market("active")}) == []

    def test_a_listed_release_still_to_close_today_holds_publication(self):
        # Registered calibration runs to 23:59 UTC, so a release closing after the
        # moment of publication is still part of it.
        morning = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
        [problem] = self._problems(morning, {"KXSBUXSAR-26OCT02-T5.13": _market("active")})
        assert f"{PAYROLLS} closes at 2026-10-02 12:29 UTC" in problem

    def test_kalshi_unreachable_is_not_read_as_unsettled(self):
        problems = self._problems(EVENING, {})
        assert problems and all("could not read" in p for p in problems)

    def test_what_counts_as_settled_is_the_resolvers_rule(self):
        # "determined" is not a status the daily resolver records, so the record
        # is not behind; the release is simply not settled yet.
        [problem] = self._problems(EVENING, {PAYROLLS: _market("determined", "yes"),
                                             "KXSBUXSAR-26OCT02-T5.13": _market("active")})
        assert "has not settled it yet" in problem


class TestTheResolverAndTheCheckShareOneRule:
    @pytest.mark.parametrize("market", [
        {"status": "finalized", "result": "yes"}, {"status": "settled", "result": "no"},
        {"status": "closed", "result": "YES "}, {"status": "determined", "result": "yes"},
        {"status": "active", "result": ""}, {"status": "finalized", "result": "void"}, {},
    ])
    def test_fetch_settlement_is_settlement_of_the_fetched_market(self, market, monkeypatch):
        monkeypatch.setattr(kalshi, "get_json", lambda url, **k: {"market": market})
        assert kalshi.fetch_settlement("KXANY-26SEP-T1") == kalshi.settlement_of(market)

    def test_an_unreachable_market_is_unsettled(self, monkeypatch):
        def down(url, **k):
            raise FetchError("down")

        monkeypatch.setattr(kalshi, "get_json", down)
        assert kalshi.fetch_market("KXANY-26SEP-T1") is None
        assert kalshi.fetch_settlement("KXANY-26SEP-T1") is None


# --- 5. every settled calibration release carries its surprise ---------------------------

class TestEverySettledReleaseCarriesItsSurprise:
    TASKS = [_task("p1", PAYROLLS, "2026-10-01", PAYROLLS_CLOSE)]

    def test_a_release_settled_only_in_part_holds_publication(self):
        markets = [{"status": "finalized"}, {"status": "closed"}]
        [problem] = w5.surprise_problems(self.TASKS, {"p1"}, set(), EVENING,
                                         event_markets=lambda e: (markets, "live"))
        assert "KXPAYROLLS-26SEP has settled for this study's questions" in problem

    def test_a_fully_settled_one_is_left_for_publish_to_record(self):
        markets = [{"status": "finalized"}, {"status": "settled"}]
        assert w5.surprise_problems(self.TASKS, {"p1"}, set(), EVENING,
                                    event_markets=lambda e: (markets, "live")) == []

    def test_a_recorded_one_is_not_fetched(self):
        def must_not_fetch(event):
            raise AssertionError("fetched a release already recorded")

        assert w5.surprise_problems(self.TASKS, {"p1"}, {"KXPAYROLLS-26SEP"}, EVENING,
                                    event_markets=must_not_fetch) == []

    def test_unresolved_releases_are_the_settlement_checks_business(self):
        assert w5.surprise_problems(self.TASKS, set(), set(), EVENING,
                                    event_markets=lambda e: ([], "live")) == []

    def test_kalshi_unreachable_holds_publication(self):
        def down(event):
            raise FetchError("down")

        [problem] = w5.surprise_problems(self.TASKS, {"p1"}, set(), EVENING, event_markets=down)
        assert "could not read KXPAYROLLS-26SEP" in problem

    def test_not_past_the_grace(self):
        later = OPENS + w5.SETTLEMENT_GRACE + timedelta(minutes=1)
        assert w5.surprise_problems(self.TASKS, {"p1"}, set(), later,
                                    event_markets=lambda e: ([{"status": "closed"}], "live")) == []

    def test_fully_settled_is_the_recorders_rule(self):
        assert release_surprise.fully_settled([{"status": "Finalized"}, {"status": "settled"}])
        assert not release_surprise.fully_settled([{"status": "finalized"}, {"status": "determined"}])
        assert not release_surprise.fully_settled([])


# --- 6. --check says what --publish would do, and writes nothing -------------------------

class TestCheck:
    def test_ready_after_the_window_opens(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(w5, "PREDICTION_FILE", tmp_path / "week5-prediction.json")
        monkeypatch.setattr(w5, "readiness", lambda now: {"ready": True, "problems": [], "notes": []})
        assert w5.check(now=EVENING) == 0
        assert "READY: run" in capsys.readouterr().out
        assert list(tmp_path.iterdir()) == []

    def test_not_ready_names_what_to_wait_for(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(w5, "PREDICTION_FILE", tmp_path / "week5-prediction.json")
        monkeypatch.setattr(w5, "readiness", lambda now: {
            "ready": False, "problems": ["wait for the daily job"], "notes": []})
        assert w5.check(now=EVENING) == 1
        out = capsys.readouterr().out
        assert "NOT READY" in out and "wait for the daily job" in out

    def test_before_the_window_it_says_publish_would_refuse(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(w5, "PREDICTION_FILE", tmp_path / "week5-prediction.json")
        monkeypatch.setattr(w5, "readiness", lambda now: {"ready": True, "problems": [], "notes": []})
        assert w5.check(now=OPENS - timedelta(days=1)) == 1
        assert "window has not opened" in capsys.readouterr().out

    def test_the_reminder_pulls_and_checks_before_publishing(self):
        steps = milestones.week5(OPENS - timedelta(days=3)).how
        order = [next(i for i, s in enumerate(steps) if key in s)
                 for key in ("git pull --ff-only", "--check", "--publish", "git push")]
        assert order == sorted(order)


# --- 7. the path runs: 2 October on a fabricated store ------------------------------------

# Four listed releases settle inside the calibration window, as the real study's
# will if September payrolls settles on the 2nd; one question that is not a release
# feeds only the H1 fit. Outcomes and forecasts are made up and mean nothing.
RELEASES = {
    # event: (close, first ask day, ask days, surprise)
    "KXUSPPI-26SEP10": ("2026-09-10T12:29:00Z", "2026-09-01", 3, 0.05),
    "KXCPIYOY-26SEP": ("2026-09-11T12:29:00Z", "2026-09-02", 4, 0.12),
    "KXHOUSINGSTART-26SEP17": ("2026-09-17T12:29:00Z", "2026-09-08", 3, 0.31),
    "KXPAYROLLS-26SEP": ("2026-10-02T12:29:00Z", "2026-09-28", 5, 0.20),
    "KXMADEUP-26SEP25": ("2026-09-25T15:00:00Z", "2026-09-10", 5, None),
}


@pytest.fixture
def made_up_record(tmp_path):
    tasks, obs, res = [], [], []
    i = 0
    for event, (close, first, days, _) in RELEASES.items():
        start = date.fromisoformat(first)
        for d in range(days):
            asked = (start + timedelta(days=d)).isoformat()
            for rung in (1, 2):
                i += 1
                tid = f"t{i:03d}"
                task = _task(tid, f"{event}-T{rung}", asked, close)
                task["state"].update({
                    "ladder_distance": (i % 5) / 5.0, "vix_level": 14.0 + (i % 7),
                    "realized_vol_20d": 0.04 + (i % 5) / 100.0, "treasury_10y": 4.5,
                    "yield_curve_10y2y": 0.4, "fed_funds": 3.6, "days_out": 10.0 + i,
                    "series": event.split("-")[0], "strike": float(rung)})
                tasks.append(task)
                res.append({"task_id": tid, "outcome": float((i * 7 + rung) % 2),
                            "resolved_at": close, "source": f"kalshi:{event}-T{rung}",
                            "note": "fabricated in tests/test_week5_publish.py", "schema": "v1"})
                for j, model in enumerate(MODELS):
                    obs.append({"obs_id": f"{tid}-{model}", "task_id": tid, "model_key": model,
                                "provider": "test", "model_id_returned": model,
                                "prompt_variant": 0, "arm": PRIMARY_ARM,
                                "forecast": round(0.15 + ((i + 3 * j) % 7) / 10.0, 3),
                                "direction": "yes", "confidence": 0.6,
                                "created_at": f"{asked}T17:05:00+00:00"})
    reference = [json.loads(line) for line in
                 (ROOT / "data" / "release_surprise.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip() and json.loads(line).get("role") == "reference"]
    study = [{"kalshi_event": e, "surprise": s, "close_time": c, "role": "study"}
             for e, (c, _, _, s) in RELEASES.items() if s is not None]
    paths = {name: tmp_path / f"{name}.jsonl"
             for name in ("tasks", "observations", "resolutions", "surprise", "ladders")}
    for name, rows in (("tasks", tasks), ("observations", obs), ("resolutions", res),
                       ("surprise", reference + study), ("ladders", [])):
        paths[name].write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return paths


@pytest.fixture
def october_second(made_up_record, tmp_path, monkeypatch, clean_git):
    """Point every read the publisher makes at the fabricated record."""
    p = made_up_record
    out = tmp_path / "predictions"
    monkeypatch.setattr(w5, "OUT_DIR", out)
    monkeypatch.setattr(w5, "PREDICTION_FILE", out / "week5-prediction.json")
    monkeypatch.setattr(w5, "H1_FIT_FILE", out / "week5-h1-fit.json")
    monkeypatch.setattr(w5, "TASKS_PATH", p["tasks"])
    monkeypatch.setattr(w5, "RESOLUTIONS_PATH", p["resolutions"])
    monkeypatch.setattr(h1, "RELEASE_SURPRISE_PATH", p["surprise"])
    monkeypatch.setattr(w5, "load_panel", functools.partial(
        load_panel, obs_path=p["observations"], resolutions_path=p["resolutions"],
        tasks_path=p["tasks"], model_keys=MODELS))
    real_loader, real_run = h1.load_release_surprises, h1.run
    monkeypatch.setattr(h1, "load_release_surprises",
                        lambda path=p["surprise"]: real_loader(path))
    monkeypatch.setattr(h1, "run", functools.partial(
        real_run, n_boot=5, tasks_path=p["tasks"], ladders_path=p["ladders"],
        surprise_path=p["surprise"], obs_path=p["observations"],
        resolutions_path=p["resolutions"], model_keys=MODELS))
    monkeypatch.setattr(release_surprise, "study", lambda store, have: 0)
    monkeypatch.setattr(kalshi, "fetch_market", lambda ref: _market("active"))

    def must_not_fetch(event):
        raise AssertionError(f"every calibration release here has its surprise; fetched {event}")

    monkeypatch.setattr(surprise, "fetch_event_markets", must_not_fetch)
    return out


class TestTheOctoberPathRuns:
    def test_it_writes_the_registered_prediction_and_the_fit(self, october_second, capsys):
        assert w5.publish(now=EVENING) == 0
        record = json.loads((october_second / "week5-prediction.json").read_text(encoding="utf-8"))
        fit = json.loads((october_second / "week5-h1-fit.json").read_text(encoding="utf-8"))

        assert record["made"] is True
        assert record["threshold_p80"] == prediction.REGISTERED_P80
        assert "0.2425625" in record["statement"]
        assert record["registered_in"] == "PREREGISTRATION.md 5.3 and 11 (deviations 18 and 22)"
        assert record["record_checked_against"]["github_main"] == "0f" * 20
        # Four eligible releases with a surprise: the registered fit is used.
        assert record["eligible"] == 4 and record["fit"]["events"] == 4
        assert record["X"] <= record["median_headroom"] and record["Y"] >= record["median_rho_bar"]
        # The made-up question that is not a release feeds H1, never the calibration.
        assert all(e["event"] != "KXMADEUP-26SEP25" for e in record["events"])
        assert fit["blind"] is False and fit["asked_on_or_before"] == prediction.PREDICTION_DATE

        out = capsys.readouterr().out
        assert "SHA-256 of" in out and "git add predictions/" in out

    def test_and_then_refuses_to_run_again(self, october_second):
        assert w5.publish(now=EVENING) == 0
        with pytest.raises(SystemExit) as caught:
            w5.publish(now=EVENING + timedelta(hours=1))
        assert "never revised" in str(caught.value)

    def test_the_full_readiness_check_passes_on_a_current_copy(self, october_second):
        state = w5.readiness(EVENING)
        assert state["ready"] is True, state["problems"]
        assert state["notes"] == []

    def test_a_stale_copy_is_refused_on_the_same_evening(self, october_second, monkeypatch):
        monkeypatch.setattr(w5, "_run_git", FakeGit(behind=2))
        with pytest.raises(SystemExit) as caught:
            w5.publish(now=EVENING)
        assert "2 commit(s) behind" in str(caught.value)
        assert not (october_second / "week5-prediction.json").exists()

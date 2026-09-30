"""The health check checks what the check-ins checked -- and can never unblind or write the record.

`scripts/health_check.py` is every September check-in written down once: the
student asks "check everything, and fix what is wrong", and this is what runs.
Three things are pinned here, the third the one that matters most.

  1. IT CHECKS WHAT IT CLAIMS. Each check speaks up in the case it exists for --
     a diverged copy, a day short of the design, an out-of-credit account, a
     retirement row on a vendor page, a dropped scheduled run -- and stays quiet
     on a healthy record.

  2. ITS FIXES ARE THE SAFE ONES. It fast-forwards, replays unpushed local
     commits on top of GitHub's data commits, puts back anything written into
     data/ on this Mac, and quarantines stray files. It refuses to replay commits
     that touch data/, undoes a replay that conflicts, and with --no-fix changes
     nothing at all.

  3. IT CANNOT BE THE NEXT DEVIATION 21. Its runner refuses --unblind, --publish
     and --evaluate; no line of it reads an outcome or an error from a panel; and
     a full run over a record fabricated in tmp_path leaves every data file
     byte-identical and starts no process that could look at an outcome.

Everything runs offline, on repositories and records made up inside the tests.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neff import config, prediction  # noqa: E402
from scripts import health_check as hc  # noqa: E402

SOURCE = ROOT / "scripts" / "health_check.py"
PLAYBOOK = ROOT / "HEALTH-CHECK.md"
SKILL = ROOT / ".claude" / "skills" / "check" / "SKILL.md"
NOW = datetime(2026, 9, 29, 21, 0, tzinfo=timezone.utc)
GIT_ENV = {"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
           "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com"}


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    # CI runners have no git identity, and a replay (rebase) writes commits.
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


# --- helpers -------------------------------------------------------------------------

class FakeHttp:
    """The network, answered from a table. Anything not in it is 'offline'."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        for pattern, answer in self.routes.items():
            if pattern in url:
                if isinstance(answer, hc.Resp):
                    return answer
                status, body = answer
                return hc.Resp(status, body if isinstance(body, str) else json.dumps(body), {})
        return hc.Resp(0, "", {}, "no network in tests")


def git(cwd, *args):
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       env={**os.environ, **GIT_ENV})
    assert p.returncode == 0, f"git {' '.join(args)}: {p.stderr}"
    return p.stdout.strip()


def git_ok(cwd, *args) -> bool:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          env={**os.environ, **GIT_ENV}).returncode == 0


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def jsonl(path: Path, rows) -> None:
    write(path, "".join(json.dumps(r) + "\n" for r in rows))


def ctx_for(root: Path, tmp_path: Path, **kw) -> hc.Ctx:
    kw.setdefault("now", NOW)
    kw.setdefault("http", FakeHttp())
    return hc.Ctx(root, python=sys.executable, home=tmp_path / "home", state_dir=root / ".health", **kw)


def statuses(findings):
    return [f.status for f in hc._normalise(findings)]


@pytest.fixture
def repos(tmp_path):
    """A bare 'GitHub', this Mac's clone of it, and the daily job's clone."""
    origin, seed = tmp_path / "origin.git", tmp_path / "seed"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    git(tmp_path, "init", "-q", str(seed))
    git(seed, "symbolic-ref", "HEAD", "refs/heads/main")
    write(seed / "data" / "observations.jsonl", '{"obs_id": "a"}\n')
    write(seed / "data" / "ledger.jsonl", '{"ts": "2026-09-01", "model": "m", "arm": "pilot", "usd": 0.001}\n')
    write(seed / "scripts" / "tool.py", "print('v1')\n")
    write(seed / "README.md", "line one\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "start")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-q", "origin", "main")
    mac, job = tmp_path / "mac", tmp_path / "job"
    git(tmp_path, "clone", "-q", str(origin), str(mac))
    git(tmp_path, "clone", "-q", str(origin), str(job))
    return origin, mac, job


def daily_commit(job: Path, line: str = '{"obs_id": "b"}') -> None:
    git(job, "pull", "-q", "--ff-only")
    with (job / "data" / "observations.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    git(job, "commit", "-qam", "data: collection")
    git(job, "push", "-q", "origin", "main")


def sync(ctx):
    hc._repo_git(ctx)
    hc._repo_fetch(ctx)
    return hc._normalise(hc._repo_sync(ctx))


# --- 1. every check is written down ------------------------------------------------------

class TestEveryCheckIsWrittenDown:
    def test_ids_are_unique_and_live_in_their_group(self):
        ids = [c.id for c in hc.CHECKS]
        assert len(ids) == len(set(ids))
        for c in hc.CHECKS:
            assert c.group in dict(hc.GROUPS) and c.id.startswith(c.group + "."), c.id

    def test_every_check_says_which_check_in_it_came_from(self):
        assert all(c.origin.strip() and c.title.strip() for c in hc.CHECKS)

    def test_every_check_has_a_section_in_the_playbook(self):
        headings = [ln for ln in PLAYBOOK.read_text(encoding="utf-8").splitlines() if ln.startswith("#### ")]
        missing = [c.id for c in hc.CHECKS if not any(f"`{c.id}`" in h for h in headings)]
        assert not missing, f"no HEALTH-CHECK.md section for: {missing}"

    def test_every_pointer_into_the_playbook_leads_somewhere(self):
        headings = [ln for ln in PLAYBOOK.read_text(encoding="utf-8").splitlines() if ln.startswith("#### ")]
        refs = set(re.findall(r'playbook="([^"]+)"', SOURCE.read_text(encoding="utf-8")))
        assert refs
        assert not [r for r in refs if not any(f"`{r}`" in h for h in headings)]

    def test_every_acknowledgement_key_is_explained(self):
        text = PLAYBOOK.read_text(encoding="utf-8")
        assert not [k for k in hc.ACK_KEYS if f"`{k}`" not in text]

    def test_the_skill_runs_this_script_under_these_rules(self):
        text = SKILL.read_text(encoding="utf-8")
        assert text.startswith("---\nname: check\n")
        for needle in ("scripts/health_check.py", "HEALTH-CHECK.md", "Never unblind", "Push only",
                       "Never write `data/`", "Research-design choices"):
            assert needle in text, needle

    def test_the_list_names_every_check(self, capsys):
        assert hc.main(["--list"]) == 0
        out = capsys.readouterr().out
        assert all(c.id in out for c in hc.CHECKS)


# --- 3. it cannot unblind, and it cannot write the record ----------------------------------

class TestItCannotUnblind:
    @pytest.mark.parametrize("arg", ["--unblind", "--publish", "--evaluate"])
    def test_its_runner_refuses_every_argument_that_looks_at_outcomes(self, arg, tmp_path):
        ctx = hc.Ctx(ROOT, python=sys.executable, state_dir=tmp_path / ".health", http=FakeHttp())
        with pytest.raises(RuntimeError, match="never unblinds"):
            hc._script(ctx, "week5_prediction.py", arg)
        with pytest.raises(RuntimeError, match="never unblinds"):
            hc._script(ctx, "analyze.py", arg, background="x")

    def test_no_line_of_it_reads_an_outcome_or_an_error(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not {"outcomes", "errors", "_permute_outcomes"} & attributes, (
            "the health check may read which forecast cells are filled -- never an outcome or an error")
        drivers = {"analysis", "h1", "h2", "h3", "h4", "h5", "h6", "prediction", "report"}
        called = {(n.value.id, n.attr) for n in ast.walk(tree)
                  if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in drivers}
        assert not [c for c in called if c[1] in ("run", "calibrate", "evaluate", "estimate", "registered_report")], (
            "the analysis drivers run only as blind subprocesses, never in-process")
        keywords = [k for n in ast.walk(tree) if isinstance(n, ast.Call) for k in n.keywords]
        assert not [k for k in keywords if k.arg == "blind"]

    def test_the_forbidden_arguments_are_the_ones_the_scripts_unblind_with(self):
        analyze = (ROOT / "scripts" / "analyze.py").read_text(encoding="utf-8")
        week5 = (ROOT / "scripts" / "week5_prediction.py").read_text(encoding="utf-8")
        assert '"--unblind"' in analyze
        assert '"--publish"' in week5 and '"--evaluate"' in week5
        assert set(hc.FORBIDDEN_ARGS) == {"--unblind", "--publish", "--evaluate"}


# --- a fabricated study, for the checks that read a whole record ----------------------------

def fabricate(today: date, days: int = 6, drop=(), error_rows=None):
    """Tasks, answers, settlements and ledger in the registered design, all made up."""
    tasks, obs, res, ledger = [], [], [], []
    freeze = date.fromisoformat(config.DATA_FREEZE)
    spec_of = config.panel_by_key()
    for k in range(days):
        d = today - timedelta(days=days - 1 - k)
        day = d.isoformat()
        ids = []
        for i in range(config.TASKS_PER_DAY):
            tid = f"t{day}-{i:02d}"
            ids.append(tid)
            event = i < 15
            close = min(d + timedelta(days=20), freeze)
            tasks.append({
                "task_id": tid, "kind": "event" if event else "filing", "prompt": "Q?",
                "asked_at": f"{day}T17:00:00+00:00",
                "resolves_after": f"{close.isoformat()}T12:29:00+00:00" if event else "",
                "source": "kalshi" if event else "edgar",
                "source_ref": f"KXMADEUP-{i:02d}-T1" if event else f"edgar:{i}:2026-06-30",
                "outcome_kind": "binary", "market_implied": 0.5 if event else None,
                "state": {"asked_on": day, "vix_level": 16.0 if k == 0 else 15.0, "realized_vol_20d": 0.05,
                          "ladder_distance": 0.5, "days_out": 20.0},
                "arm": config.PRIMARY_ARM, "schema": "v1"})
        for (model, variant), count in hc.expected_rows(day, config.TASKS_PER_DAY).items():
            spec = spec_of[model]
            route = (config.bridge_spec(spec, day) if variant == config.BRIDGE_VARIANT
                     else config.routed(spec, day))
            for j in range(count):
                if (day, model, variant, j) in drop:
                    continue
                err = (error_rows or {}).get((day, model, variant, j))
                obs.append({
                    "obs_id": f"{ids[j]}-{model}-{variant}", "task_id": ids[j], "model_key": model,
                    "model_id_returned": route.model_id, "provider": route.provider,
                    "prompt_variant": variant, "forecast": None if err else 0.4,
                    "direction": "no", "confidence": 0.6,
                    "upstream_provider": {"openrouter_azure": "Azure", "openrouter": "DeepInfra"}.get(route.provider),
                    "logprobs": [{"t": "4", "lp": -0.1}] if route.supports_logprobs else None,
                    "usd": 0.001, "error": err, "arm": config.PRIMARY_ARM,
                    "created_at": f"{day}T17:05:00+00:00", "schema": "v1"})
                ledger.append({"ts": f"{day}T17:05:00+00:00", "model": model, "arm": config.PRIMARY_ARM,
                               "input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 0,
                               "batch": False, "usd": 0.001})
    for t in tasks[:10]:
        res.append({"task_id": t["task_id"], "outcome": 0.0, "resolved_at": "x",
                    "source": f"kalshi:{t['source_ref']}", "note": "made up in tests", "schema": "v1"})
    return tasks, obs, res, ledger


def make_study(tmp_path: Path, today: date, **kw) -> Path:
    """A repository with the study's code and plan and a record made up in the test."""
    root, origin = tmp_path / "study", tmp_path / "study-origin.git"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for name in ("neff", "scripts", ".github"):
        shutil.copytree(ROOT / name, root / name, ignore=ignore)
    for name in ("PREREGISTRATION.md", "OSF-ADDENDUM-1.md", "README.md", ".gitignore", "requirements.txt",
                 "constraints.txt", ".osf_url", ".env.example"):
        shutil.copy2(ROOT / name, root / name)
    write(root / "tests" / "__init__.py", "")
    tasks, obs, res, ledger = fabricate(today, **kw)
    data = root / "data"
    jsonl(data / "tasks.jsonl", tasks)
    jsonl(data / "observations.jsonl", obs)
    jsonl(data / "resolutions.jsonl", res)
    jsonl(data / "ledger.jsonl", ledger)
    jsonl(data / "release_surprise.jsonl", [])
    jsonl(data / "verification.jsonl", [
        {"checked_at": "2026-09-02T03:47:49+00:00", "model_key": m.key, "provider": m.provider,
         "model_id_pinned": m.model_id, "temperature": 0.0, "ok": True, "model_id_returned": m.model_id,
         "usd": 0.0003, "drift": False, "error": None} for m in config.enabled_panel()])
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    git(tmp_path, "init", "-q", str(root))
    git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    git(root, "add", "-A", "--", ".", ":!data")
    git(root, "commit", "-q", "-m", "the instrument")
    # The record is committed the way GitHub commits it: by the daily job.
    git(root, "add", "-A", "data")
    subprocess.run(["git", "commit", "-q", "-m", "data: collection"], cwd=str(root), check=True,
                   env={**os.environ, **GIT_ENV, "GIT_AUTHOR_NAME": hc.COLLECTOR,
                        "GIT_COMMITTER_NAME": hc.COLLECTOR})
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "-u", "origin", "main")
    return root


def digests(root: Path):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root / "data").glob("*.jsonl"))}


@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    """One whole run, offline and quick, over a made-up study -- watched from outside."""
    tmp = tmp_path_factory.mktemp("full")
    today = datetime.now(timezone.utc).date()
    root = make_study(tmp, today)
    before = digests(root)
    started = []
    real_run, real_start = hc._run, hc.Background.start

    def spy_run(argv, cwd, timeout=120, env=None):
        started.append([str(a) for a in argv])
        return real_run(argv, cwd, timeout=timeout, env=env)

    def spy_start(self, name, argv, cwd, env=None, timeout=900):
        started.append([str(a) for a in argv])
        return real_start(self, name, argv, cwd, env=env, timeout=timeout)

    with pytest.MonkeyPatch.context() as mp:
        for key, value in GIT_ENV.items():
            mp.setenv(key, value)
        mp.setenv("HOME", str(tmp / "home"))
        mp.setattr(hc, "_run", spy_run)
        mp.setattr(hc.Background, "start", spy_start)
        code = hc.main(["--root", str(root), "--offline", "--quick"])
    report = json.loads((root / ".health" / "last-report.json").read_text(encoding="utf-8"))
    return {"root": root, "before": before, "started": started, "code": code, "report": report}


class TestAWholeRunOverAMadeUpStudy:
    def test_every_data_file_is_byte_identical_afterwards(self, full_run):
        assert digests(full_run["root"]) == full_run["before"]

    def test_it_leaves_nothing_for_git_to_see(self, full_run):
        assert git(full_run["root"], "status", "--porcelain", "--untracked-files=all") == ""
        assert git_ok(full_run["root"], "check-ignore", "-q", ".health/state.json")

    def test_no_process_it_starts_can_look_at_an_outcome(self, full_run):
        assert full_run["started"]
        for argv in full_run["started"]:
            assert not set(argv) & set(hc.FORBIDDEN_ARGS), argv
            assert not any("blind=False" in a or "unblind" in a for a in argv), argv

    def test_no_check_crashes_on_a_healthy_record(self, full_run):
        errors = [f for f in full_run["report"]["findings"] if f["status"] == "error"]
        assert not errors, errors

    def test_a_healthy_record_raises_nothing_serious(self, full_run):
        # Only the groups that judge the record itself: the calendar groups (dates, the
        # Week-5 milestone, the student's to-dos) rightly change with the day the suite
        # runs, and the suite runs every day -- a date-dependent assertion here would
        # fail the daily job's own test step on the one day that matters.
        record_groups = ("repo", "record", "panel", "resolve", "plan", "money", "local")
        serious = [f for f in full_run["report"]["findings"]
                   if f["group"] in record_groups and f["status"] in ("claude", "you")
                   and f["severity"] in ("high", "critical")]
        assert not serious, serious

    def test_the_core_checks_pass_on_it(self, full_run):
        by_check = {}
        for f in full_run["report"]["findings"]:
            by_check.setdefault(f["check"], []).append(f["status"])
        for check in ("record.continuity", "record.day_shape", "record.integrity", "record.served_ids",
                      "record.parse", "plan.freeze", "resolve.integrity", "repo.secrets"):
            assert by_check.get(check, [None])[0] == "ok", (check, by_check.get(check))

    def test_the_report_carries_what_the_reply_and_memory_need(self, full_run):
        r = full_run["report"]
        assert r["schema"] == 1 and set(r["verdict"]) >= {"level", "headline", "exit_code"}
        assert r["facts"]["summary_line"].startswith(datetime.now(timezone.utc).date().isoformat())
        assert r["facts"]["days_collected"] == 6
        assert (full_run["root"] / ".health" / "last-report.md").exists()
        assert (full_run["root"] / ".health" / "history.jsonl").read_text().count("\n") == 1


# --- 2. its fixes are the safe ones ---------------------------------------------------------

class TestTheCopyIsKeptInStepWithGitHub:
    def test_a_copy_that_is_only_behind_is_fast_forwarded(self, repos, tmp_path):
        origin, mac, job = repos
        daily_commit(job)
        got = sync(ctx_for(mac, tmp_path))
        assert [f.status for f in got] == [hc.FIXED]
        assert git(mac, "rev-parse", "HEAD") == git(origin, "rev-parse", "main")

    def test_a_diverged_copy_gets_its_commits_replayed_on_top_then_asks_to_push(self, repos, tmp_path):
        origin, mac, job = repos
        write(mac / "scripts" / "tool.py", "print('v2')\n")
        git(mac, "commit", "-qam", "Improve the tool")
        daily_commit(job)
        daily_commit(job, '{"obs_id": "c"}')
        old = git(mac, "rev-parse", "--short", "HEAD")
        got = sync(ctx_for(mac, tmp_path))
        assert [f.status for f in got] == [hc.FIXED, hc.YOU]
        assert git_ok(mac, "merge-base", "--is-ancestor", "origin/main", "HEAD")
        assert git(mac, "log", "-1", "--format=%s") == "Improve the tool"
        assert (mac / "data" / "observations.jsonl").read_text().count("obs_id") == 3
        assert f"git reset --hard {old}" in " ".join(got[0].detail)
        push = got[1]
        assert push.severity == "high" and "push" in " ".join(push.steps)

    def test_a_replay_that_conflicts_is_undone(self, repos, tmp_path):
        origin, mac, job = repos
        write(mac / "README.md", "line one, as the Mac has it\n")
        git(mac, "commit", "-qam", "Edit the README here")
        git(job, "pull", "-q")
        write(job / "README.md", "line one, as GitHub has it\n")
        git(job, "commit", "-qam", "Edit the README there")
        git(job, "push", "-q", "origin", "main")
        before = git(mac, "rev-parse", "HEAD")
        got = sync(ctx_for(mac, tmp_path))
        assert got[0].status == hc.CLAUDE and got[0].severity == "high"
        assert git(mac, "rev-parse", "HEAD") == before
        assert not (mac / ".git" / "rebase-merge").exists() and not (mac / ".git" / "rebase-apply").exists()

    def test_local_commits_that_touch_the_record_are_never_replayed(self, repos, tmp_path):
        origin, mac, job = repos
        with (mac / "data" / "observations.jsonl").open("a") as fh:
            fh.write('{"obs_id": "written on the Mac"}\n')
        git(mac, "commit", "-qam", "A row written by hand")
        daily_commit(job)
        before = git(mac, "rev-parse", "HEAD")
        got = sync(ctx_for(mac, tmp_path))
        assert got[0].status == hc.CLAUDE and "data/" in got[0].summary
        assert git(mac, "rev-parse", "HEAD") == before

    def test_uncommitted_code_stops_the_replay_and_is_kept(self, repos, tmp_path):
        origin, mac, job = repos
        write(mac / "scripts" / "tool.py", "print('v2')\n")
        git(mac, "commit", "-qam", "Improve the tool")
        write(mac / "scripts" / "tool.py", "print('v3, unfinished')\n")
        daily_commit(job)
        before = git(mac, "rev-parse", "HEAD")
        got = sync(ctx_for(mac, tmp_path))
        assert got[0].status == hc.CLAUDE
        assert git(mac, "rev-parse", "HEAD") == before
        assert "unfinished" in (mac / "scripts" / "tool.py").read_text()

    def test_report_only_changes_nothing(self, repos, tmp_path):
        origin, mac, job = repos
        daily_commit(job)
        before = git(mac, "rev-parse", "HEAD")
        got = sync(ctx_for(mac, tmp_path, fix=False))
        assert got[0].status == hc.CLAUDE
        assert git(mac, "rev-parse", "HEAD") == before

    def test_an_identical_copy_is_simply_fine(self, repos, tmp_path):
        origin, mac, job = repos
        assert statuses(sync(ctx_for(mac, tmp_path))) == [hc.OK]


class TestNothingWrittenIntoDataOnThisMacSurvives:
    def test_a_changed_record_file_is_put_back_and_the_change_kept(self, repos, tmp_path):
        origin, mac, job = repos
        with (mac / "data" / "observations.jsonl").open("a") as fh:
            fh.write('{"obs_id": "stray row"}\n')
        ctx = ctx_for(mac, tmp_path)
        got = hc._normalise(hc._repo_worktree(ctx))
        assert [f.status for f in got] == [hc.FIXED]
        assert "stray row" not in (mac / "data" / "observations.jsonl").read_text()
        patches = list((mac / ".health" / "backups").glob("*-data.patch"))
        assert len(patches) == 1 and "stray row" in patches[0].read_text()

    def test_a_stray_file_in_data_is_quarantined(self, repos, tmp_path):
        origin, mac, job = repos
        write(mac / "data" / "extra.jsonl", "{}\n")
        got = hc._normalise(hc._repo_worktree(ctx_for(mac, tmp_path)))
        assert [f.status for f in got] == [hc.FIXED]
        assert not (mac / "data" / "extra.jsonl").exists()
        assert list((mac / ".health" / "quarantine").rglob("extra.jsonl"))

    def test_receipts_of_a_live_verify_run_are_not_thrown_away(self, repos, tmp_path):
        origin, mac, job = repos
        row = '{"ts": "2026-09-29", "model": "gpt_mid", "arm": "pilot", "usd": 0.0002}\n'
        with (mac / "data" / "ledger.jsonl").open("a") as fh:
            fh.write(row)
        got = hc._normalise(hc._repo_worktree(ctx_for(mac, tmp_path)))
        assert [f.status for f in got] == [hc.CLAUDE]
        assert row in (mac / "data" / "ledger.jsonl").read_text()

    def test_uncommitted_code_is_reported_and_left_alone(self, repos, tmp_path):
        origin, mac, job = repos
        write(mac / "scripts" / "tool.py", "print('work in progress')\n")
        got = hc._normalise(hc._repo_worktree(ctx_for(mac, tmp_path)))
        assert [f.status for f in got] == [hc.CLAUDE]
        assert "work in progress" in (mac / "scripts" / "tool.py").read_text()

    def test_report_only_leaves_data_alone_too(self, repos, tmp_path):
        origin, mac, job = repos
        with (mac / "data" / "observations.jsonl").open("a") as fh:
            fh.write('{"obs_id": "stray row"}\n')
        got = hc._normalise(hc._repo_worktree(ctx_for(mac, tmp_path, fix=False)))
        assert got[0].status == hc.CLAUDE
        assert "stray row" in (mac / "data" / "observations.jsonl").read_text()


class TestTheStateStaysOnThisMac:
    def test_the_state_folder_ignores_itself(self, repos, tmp_path):
        origin, mac, job = repos
        hc._ensure_state_dir(mac / ".health")
        write(mac / ".health" / "state.json", "{}")
        assert git(mac, "status", "--porcelain", "--untracked-files=all") == ""

    def test_acknowledgements_and_balances_are_recorded(self, repos, tmp_path):
        origin, mac, job = repos
        assert hc.main(["--root", str(mac), "--ack", "you.isef", "forms", "signed"]) == 0
        assert hc.main(["--root", str(mac), "--balance", "anthropic=17.37", "openai=$8.83",
                        "--as-of", "2026-09-22T03:12:00Z"]) == 0
        state = json.loads((mac / ".health" / "state.json").read_text())
        assert state["acks"]["you.isef"]["note"] == "forms signed"
        assert state["balances"]["openai"]["usd"] == 8.83
        assert state["balances"]["anthropic"]["as_of"].startswith("2026-09-22T03:12")
        assert hc.main(["--root", str(mac), "--unack", "you.isef"]) == 0
        assert "you.isef" not in json.loads((mac / ".health" / "state.json").read_text())["acks"]

    def test_an_unknown_key_is_refused(self, repos, tmp_path):
        origin, mac, job = repos
        with pytest.raises(SystemExit):
            hc.main(["--root", str(mac), "--ack", "you.everything"])

    def test_a_recurring_acknowledgement_expires(self, tmp_path):
        ctx = hc.Ctx(ROOT, now=NOW, http=FakeHttp(), state_dir=tmp_path / ".health")
        ctx.state = {"acks": {"you.prompt_log_backup": {"at": (NOW - timedelta(days=8)).isoformat()},
                              "you.isef": {"at": (NOW - timedelta(days=80)).isoformat()}}}
        assert ctx.ack("you.prompt_log_backup") is None
        assert ctx.ack("you.isef") is not None


# --- 1. each check speaks up in the case it exists for -----------------------------------------

@pytest.mark.parametrize("message, category", [
    ('failed after 3 attempts: ProviderError: openrouter HTTP 429: {"error":{"message":"Provider returned '
     'error","code":429,"metadata":{"raw":"qwen/qwen-2.5-72b-instruct is temporarily rate-limited upstream."}}}',
     "rate_limit"),
    ('failed after 3 attempts: ProviderError: openai HTTP 429: {"error": {"type": "insufficient_quota"}}', "quota"),
    ("ProviderError: anthropic HTTP 400: Your credit balance is too low to access the Anthropic API", "quota"),
    ("ProviderError: openrouter HTTP 402: Insufficient credits", "quota"),
    ("FREE-TIER DAILY QUOTA: 20 requests/day for gemini-3.5-flash-lite", "quota"),
    ("ProviderError: anthropic HTTP 401: invalid x-api-key", "auth"),
    ("ANTHROPIC_API_KEY not set", "auth"),
    ("ProviderError: openai HTTP 404: The model `gpt-4.1-nano-2025-04-14` does not exist", "retired"),
    (" | unparseable response", "parse"),
    (" | truncated at max_tokens=1000 (1000 output tokens billed, no JSON reached)", "parse"),
    ("failed after 3 attempts: ReadTimeout: timed out", "server"),
    ("ProviderError: google HTTP 503: the model is overloaded", "server"),
    ("something nobody has seen before", "other"),
])
def test_a_failed_answer_is_sorted_by_who_can_act(message, category):
    assert hc.classify_error(message) == category


class TestTheDesignOfADay:
    @pytest.mark.parametrize("day, rows", [
        ("2026-09-01", 270),      # 25 questions x 10 models + 2 replicates each
        ("2026-09-14", 370),      # + the H3 arm: gpt_mid, variants 1-4
        ("2026-09-20", 395),      # + the bridge: gpt_small asked through Azure as well
        ("2026-10-13", 395),      # the bridge's last day (deviation 24)
        ("2026-10-14", 370),      # Azure has retired the model: no bridge
        ("2026-10-22", 370),      # gpt_small's last day
        ("2026-10-23", 343),      # retired: no host serves it (25 answers + 2 replicates fewer)
    ])
    def test_rows_owed_on_the_registered_dates(self, day, rows):
        assert sum(hc.expected_rows(day, config.TASKS_PER_DAY).values()) == rows

    def test_a_missing_answer_is_reported(self, tmp_path):
        today = NOW.date()
        root = tmp_path / "r"
        tasks, obs, res, ledger = fabricate(today, days=3, drop={((today - timedelta(days=1)).isoformat(), "qwen", 0, 4)})
        for name, rows in (("tasks", tasks), ("observations", obs), ("resolutions", res), ("ledger", ledger)):
            jsonl(root / "data" / f"{name}.jsonl", rows)
        got = hc._normalise(hc._record_day_shape(ctx_for(root, tmp_path)))
        assert got[0].status == hc.WATCH
        assert any("qwen variant 0 has 24 of 25" in d for d in got[0].detail)


class TestFailedAnswers:
    def test_an_empty_account_goes_to_you_at_once(self, tmp_path):
        today = NOW.date()
        root = tmp_path / "r"
        errors = {(today.isoformat(), "claude_haiku", 0, j): "ProviderError: anthropic HTTP 400: Your credit "
                  "balance is too low" for j in range(25)}
        tasks, obs, res, ledger = fabricate(today, days=3, error_rows=errors)
        for name, rows in (("tasks", tasks), ("observations", obs)):
            jsonl(root / "data" / f"{name}.jsonl", rows)
        got = hc._normalise(hc._record_errors(ctx_for(root, tmp_path)))
        you = [f for f in got if f.status == hc.YOU]
        assert you and you[0].severity == "critical" and "Anthropic" in you[0].summary
        assert any("platform.claude.com" in s for s in you[0].steps)

    def test_a_rate_limit_that_recovered_is_known_not_raised(self, tmp_path):
        today = NOW.date()
        root = tmp_path / "r"
        errors = {((today - timedelta(days=1)).isoformat(), "qwen", 0, j): "openrouter HTTP 429: rate-limited"
                  for j in range(6)}
        tasks, obs, res, ledger = fabricate(today, days=3, error_rows=errors)
        for name, rows in (("tasks", tasks), ("observations", obs)):
            jsonl(root / "data" / f"{name}.jsonl", rows)
        got = hc._normalise(hc._record_errors(ctx_for(root, tmp_path)))
        assert [f.status for f in got] == [hc.KNOWN]


class TestAFailingBridge:
    """Since deviation 24 the bridge carries gpt_small nowhere: its failing puts no day at risk."""

    def _continuity(self, tmp_path, monkeypatch, answered):
        c = {"today": "2026-10-05", "today_state": "done", "today_collected": True, "missing_days": [],
             "below_floor": [], "window_days": 7, "coverage_window": {"gpt_small": 0.99},
             "bridge_day": "2026-10-05", "bridge_latest": {"gpt_small": {"answered": answered, "asked": 25}}}

        def check_days(ctx, name, *args, cwd=None, **kw):
            assert name == "check_days.py"
            (cwd / "continuity.json").write_text(json.dumps(c), encoding="utf-8")
            return hc.Proc(0)
        monkeypatch.setattr(hc, "_script", check_days)
        root = tmp_path / "r"
        jsonl(root / "data" / "tasks.jsonl", [])
        jsonl(root / "data" / "observations.jsonl", [])
        got = hc._normalise(hc._record_continuity(ctx_for(root, tmp_path)))
        return [f for f in got if "bridge" in f.summary]

    def test_is_for_claude_to_record_not_an_emergency(self, tmp_path, monkeypatch):
        got = self._continuity(tmp_path, monkeypatch, answered=0)
        assert [(f.status, f.severity) for f in got] == [(hc.CLAUDE, "medium")]
        assert "moves to" not in got[0].summary and "0/25" in got[0].summary
        assert "no day is at risk" in " ".join(got[0].detail).lower()

    def test_a_healthy_one_says_nothing(self, tmp_path, monkeypatch):
        assert self._continuity(tmp_path, monkeypatch, answered=25) == []


class TestTheFloorIsWatchedAhead:
    def test_a_model_on_the_floor_gets_a_projection_and_nothing_reads_an_outcome(self, tmp_path, monkeypatch):
        today = NOW.date()
        root = tmp_path / "r"
        drop = {((today - timedelta(days=5)).isoformat(), "qwen", 0, j) for j in range(2)}
        tasks, obs, res, ledger = fabricate(today, days=6, drop=drop)
        for name, rows in (("tasks", tasks), ("observations", obs), ("resolutions", res), ("ledger", ledger)):
            jsonl(root / "data" / f"{name}.jsonl", rows)
        from neff import analysis
        monkeypatch.setattr(analysis, "_permute_outcomes",
                            lambda *a, **k: pytest.fail("the coverage check touched outcomes"))
        got = hc._normalise(hc._panel_coverage(ctx_for(root, tmp_path)))
        watch = [f for f in got if f.status == hc.WATCH]
        assert watch and "qwen" in watch[0].summary
        assert "already-asked questions" in " ".join(watch[0].detail)


class TestVendorPages:
    FREEZE_PAGE = {
        "anthropic": ("Model Status Deprecated date Retirement date claude-sonnet-4-6 Active N/A Not sooner than "
                      "February 17, 2027 claude-haiku-4-5-20251001 Active N/A Not sooner than October 15, 2026 "
                      "claude-3-haiku-20240307 Retired February 19, 2026 April 20, 2026 Deprecation history "
                      "April 20, 2026 claude-3-haiku-20240307 claude-haiku-4-5-20251001"),
        "openai": ("Shutdown date Model snapshot Substitute model October 23, 2026 gpt-4.1-nano | "
                   "gpt-4.1-nano-2025-04-14 gpt-5.6-luna October 23, 2026 gpt-4o-2024-05-13 gpt-5.6-sol "
                   "Fine-tuned models October 23, 2026 ft:gpt-4.1-nano-2025-04-14 gpt-5.6-luna "
                   "2026-03-26 gpt-4-0314 gpt-5 or gpt-4.1* *For tasks that are latency sensitive"),
        "google": ("Model Release date Shutdown date gemini-3.6-flash July 21, 2026 No shutdown date announced "
                   "gemini-3.5-flash-lite July 21, 2026 No shutdown date announced gemini-3.5-flash May 19, 2026 "
                   "No shutdown date announced gemini-3.1-flash-lite May 7, 2026 May 7, 2027 gemini-3.5-flash-lite "
                   "Preview models"),
        "azure": ("Model Version Lifecycle Retirement date Replacement gpt-4.1 2025-04-14 Deprecated 2027-04-14 — "
                  "gpt-4.1-nano 2025-04-14 Deprecated 2026-10-14 — gpt-4o 2024-05-13 Deprecated 2026-12-09 "
                  "gpt-5.6-sol Fine-tuned models gpt-4.1-nano 2025-04-14 No earlier than 2027-04-14 1 2027-10-14"),
    }

    def _assess(self, vendor, key, model_id, handled=None, page=None):
        ctx = hc.Ctx(ROOT, now=NOW, http=FakeHttp())
        rows = hc.retirement_rows(vendor, page or self.FREEZE_PAGE[vendor], model_id)
        return hc.assess_retirement(ctx, vendor, key, model_id, rows, handled)

    def test_an_active_model_guaranteed_only_into_the_window_is_watched(self):
        got = self._assess("anthropic", "claude_haiku", "claude-haiku-4-5-20251001")
        assert [f.status for f in got] == [hc.WATCH]
        assert "no notice yet" in got[0].summary

    def test_a_model_guaranteed_past_the_freeze_is_fine(self):
        assert statuses(self._assess("anthropic", "claude_sonnet", "claude-sonnet-4-6")) == [hc.OK]

    def test_a_deprecation_notice_is_critical(self):
        page = self.FREEZE_PAGE["anthropic"].replace(
            "claude-haiku-4-5-20251001 Active N/A Not sooner than October 15, 2026",
            "claude-haiku-4-5-20251001 Deprecated October 1, 2026 December 1, 2026")
        got = self._assess("anthropic", "claude_haiku", "claude-haiku-4-5-20251001", page=page)
        assert got[0].status == hc.CLAUDE and got[0].severity == "critical"

    def test_a_shutdown_the_registered_route_handles_is_known(self):
        got = self._assess("openai", "gpt_small", "gpt-4.1-nano-2025-04-14", handled=date(2026, 10, 23))
        assert statuses(got) == [hc.KNOWN]

    def test_the_same_shutdown_without_a_route_is_critical(self):
        got = self._assess("openai", "gpt_small", "gpt-4.1-nano-2025-04-14")
        assert got[0].status == hc.CLAUDE and got[0].severity == "critical"

    def test_being_named_as_a_replacement_is_not_a_retirement(self):
        assert statuses(self._assess("openai", "gpt_frontier", "gpt-4.1-2025-04-14")) == [hc.OK]
        assert statuses(self._assess("google", "gemini_flash", "gemini-3.5-flash-lite")) == [hc.OK]
        assert statuses(self._assess("anthropic", "x", "claude-3-haiku-20240307"))[0] == hc.CLAUDE

    def test_no_shutdown_announced_is_fine(self):
        assert statuses(self._assess("google", "gemini_flash_pro", "gemini-3.5-flash")) == [hc.OK]

    def test_the_route_s_own_host_retiring_first_is_critical(self):
        # 29 Sep 2026: Azure moved gpt-4.1-nano's retirement from 2027-04-14 to 2026-10-14 -- before the
        # 23 Oct switch that deviation 23 registers. The fine-tuned table below it is not about this.
        got = self._assess("azure", "gpt_small route", "openai/gpt-4.1-nano")
        assert [f.status for f in got] == [hc.CLAUDE] and "14 Oct 2026" in got[0].summary

    def _http(self):
        return FakeHttp({"platform.claude.com": (200, self.FREEZE_PAGE["anthropic"] + " " * 3000),
                         "developers.openai.com": (200, self.FREEZE_PAGE["openai"] + " " * 3000),
                         "ai.google.dev": (200, self.FREEZE_PAGE["google"] + " " * 3000),
                         "learn.microsoft.com": (200, self.FREEZE_PAGE["azure"] + " " * 3000)})

    def test_with_deviation_24_both_shutdowns_are_handled(self, tmp_path):
        ctx = hc.Ctx(ROOT, now=NOW, http=self._http(), state_dir=tmp_path / ".health")
        got = hc._normalise(hc._vendors_retirements(ctx))
        assert not [f for f in got if f.severity == "critical"], got
        known = [f.summary for f in got if f.status == hc.KNOWN]
        assert any(k.startswith("gpt_small (") and "not asked from 2026-10-23" in k for k in known)
        assert any(k.startswith("gpt_small bridge") and "2026-10-13" in k for k in known)
        assert len([f for f in got if f.summary.startswith("gpt_small (")]) == 1   # one row, not one per mention

    def test_a_shutdown_is_not_handled_by_a_route_that_retires_first(self, tmp_path, monkeypatch):
        # Deviation 23 as it stood on 29 Sep: a route to Azure from 23 Oct, whose host then
        # moved the model's retirement to 14 Oct. The route handles nothing, and says so once.
        route = config.ServingRoute(starts="2026-10-23", provider="openrouter_azure",
                                    model_id="openai/gpt-4.1-nano", supports_logprobs=False)
        monkeypatch.setattr(config, "SERVING_ROUTES", {"gpt_small": route})
        monkeypatch.setattr(config, "RETIREMENTS", {})
        monkeypatch.setattr(config, "BRIDGE_ROUTES", {})
        ctx = hc.Ctx(ROOT, now=NOW, http=self._http(), state_dir=tmp_path / ".health")
        got = hc._normalise(hc._vendors_retirements(ctx))
        small = [f for f in got if f.summary.startswith("gpt_small (")]
        assert len(small) == 1 and small[0].status == hc.INFO and "retires first" in small[0].summary
        critical = [f for f in got if f.severity == "critical"]
        assert len(critical) == 1 and critical[0].summary.startswith("gpt_small route")

    def test_a_row_that_changes_between_runs_is_raised(self, tmp_path):
        http = FakeHttp({"platform.claude.com": (200, self.FREEZE_PAGE["anthropic"] + " " * 3000),
                         "developers.openai.com": (200, self.FREEZE_PAGE["openai"] + " " * 3000),
                         "ai.google.dev": (200, self.FREEZE_PAGE["google"] + " " * 3000),
                         "learn.microsoft.com": (200, self.FREEZE_PAGE["azure"] + " " * 3000)})
        ctx = hc.Ctx(ROOT, now=NOW, http=http, state_dir=tmp_path / ".health")
        first = hc._normalise(hc._vendors_retirements(ctx))
        assert not [f for f in first if "changed" in f.summary]
        http.routes["platform.claude.com"] = (200, self.FREEZE_PAGE["anthropic"].replace(
            "Not sooner than February 17, 2027", "Not sooner than March 1, 2027") + " " * 3000)
        second = hc._normalise(hc._vendors_retirements(ctx))
        changed = [f for f in second if "changed" in f.summary]
        assert len(changed) == 1 and "claude-sonnet-4-6" in changed[0].summary


class TestGitHubActions:
    def _ctx(self, tmp_path, runs):
        http = FakeHttp({"/actions/runs?": (200, {"workflow_runs": runs})})
        return hc.Ctx(ROOT, now=NOW, http=http, state_dir=tmp_path / ".health")

    @staticmethod
    def _run(n, when, conclusion="success", name="daily-collection", event="schedule"):
        return {"id": n, "run_number": n, "name": name, "event": event, "status": "completed",
                "conclusion": conclusion, "created_at": when, "html_url": f"https://x/{n}", "head_sha": "abc1234"}

    def test_a_failed_run_with_no_later_success_is_high(self, tmp_path):
        got = hc._normalise(hc._ci_runs(self._ctx(tmp_path, [
            self._run(3, "2026-09-29T18:00:00Z", "failure"), self._run(2, "2026-09-29T02:00:00Z")])))
        assert got[0].status == hc.CLAUDE and got[0].severity == "high"

    def test_a_failed_run_followed_by_a_success_is_medium(self, tmp_path):
        got = hc._normalise(hc._ci_runs(self._ctx(tmp_path, [
            self._run(3, "2026-09-29T18:00:00Z"), self._run(2, "2026-09-29T13:30:00Z", "failure")])))
        assert got[0].status == hc.CLAUDE and got[0].severity == "medium"

    def test_thirty_hours_without_a_successful_run_is_urgent_and_yours(self, tmp_path):
        got = hc._normalise(hc._ci_runs(self._ctx(tmp_path, [self._run(2, "2026-09-28T13:30:00Z")])))
        you = [f for f in got if f.status == hc.YOU]
        assert you and you[0].severity == "critical" and "Run workflow" in " ".join(you[0].steps)

    def test_githubs_rate_limit_is_not_an_error(self, tmp_path):
        http = FakeHttp({"api.github.com": hc.Resp(403, "{}", {"x-ratelimit-remaining": "0",
                                                                "x-ratelimit-reset": "1790000000"})})
        ctx = hc.Ctx(ROOT, now=NOW, http=http, state_dir=tmp_path / ".health")
        got = hc._normalise(hc._ci_runs(ctx))
        assert got[0].status == hc.WATCH and "allowance" in got[0].summary

    def test_a_day_with_one_chance_to_run_is_watched(self, tmp_path):
        runs = []
        for k in range(1, 12):
            d = NOW.date() - timedelta(days=k)
            runs.append(self._run(100 + k, f"{d}T17:30:00Z"))
            if d != date(2026, 9, 28):
                runs.append(self._run(200 + k, f"{d}T22:45:00Z"))
        runs.append(self._run(300, "2026-09-29T00:15:00Z"))
        got = hc._normalise(hc._ci_schedule(self._ctx(tmp_path, runs)))
        assert got[0].status == hc.WATCH and "28 Sep" in got[0].summary
        assert any("NEXT day" in d for d in got[0].detail)


def test_a_partial_run_leaves_the_last_full_report_alone(repos, tmp_path):
    origin, mac, job = repos
    state = mac / ".health"
    hc._ensure_state_dir(state)
    (state / "last-report.json").write_text('{"full": true}')
    ctx = ctx_for(mac, tmp_path)
    findings = hc.run_checks(ctx, ["repo.gitignore"])
    hc.write_reports(ctx, findings, hc.verdict(findings), partial=True)
    assert json.loads((state / "last-report.json").read_text()) == {"full": True}
    assert json.loads((state / "last-partial.json").read_text())["partial"] is True


def test_the_schedule_is_read_the_way_github_runs_it():
    text = 'on:\n  schedule:\n    - cron: "10 13 * * *"\n    - cron: "0 20 * * *"\n    - cron: \'41 16 * * *\'\n'
    assert hc.cron_slots(text) == [(13, 10), (16, 41), (20, 0)]
    assert hc.cron_slots("no schedule here") == []


class TestTheWeek5Check:
    def test_before_the_window_the_two_expected_reasons_are_known(self):
        text = ("NOT READY:\n  - 2026-10-02's collection is not in this copy yet, and weeks 1-5 end with it.\n"
                "  - KXPAYROLLS-26SEP-T-25000 closes at 2026-10-02 12:29 UTC, inside the calibration window. "
                "Publish after it has settled.\n")
        got, flags = hc.week5_findings(text, 1, NOW)
        assert statuses(got) == [hc.KNOWN] and not flags

    def test_a_copy_behind_github_is_a_real_problem(self):
        text = "NOT READY:\n  - this copy is 7 commit(s) behind GitHub, so it is missing data\n"
        got, _ = hc.week5_findings(text, 1, NOW)
        assert got[0].status == hc.CLAUDE

    def test_ready_in_the_window_is_urgent_and_yours(self):
        opens = datetime.fromisoformat(prediction.PUBLISH_NOT_BEFORE)
        got, flags = hc.week5_findings("READY: run  ./.venv/bin/python scripts/week5_prediction.py --publish",
                                       0, opens + timedelta(minutes=5))
        assert got[0].status == hc.YOU and got[0].severity == "critical" and flags == {"ready": True}

    def test_published_is_done(self):
        got, flags = hc.week5_findings("already published: predictions/week5-prediction.json exists", 1, NOW)
        assert statuses(got) == [hc.OK] and flags == {"done": True}


class TestIssues:
    def test_old_alarms_close_new_ones_are_read_and_the_reminder_stays(self):
        issues = [
            {"number": 6, "title": "collection at risk: 2026-09-29", "user": {"login": "github-actions[bot]"}},
            {"number": 5, "title": "needs a person: dated commitment due", "user": {"login": "github-actions[bot]"}},
            {"number": 4, "title": "collection at risk: 2026-09-07", "user": {"login": "github-actions[bot]"}},
            {"number": 1, "title": "A second dataset for you", "user": {"login": "someone"}},
            {"number": 7, "title": "a pull request", "pull_request": {}},
        ]
        got = hc.issue_findings(issues, NOW.date(), missing_days=[])
        kinds = {f.status: f for f in got}
        assert "#6" in kinds[hc.CLAUDE].summary
        assert {"#4", "#1"} == {d.split()[0] for d in kinds[hc.YOU].detail}
        assert "#5" in kinds[hc.INFO].summary and "#7" not in json.dumps([f.as_dict() for f in got])


class TestMoney:
    def test_the_spend_follows_the_registered_design_day_by_day(self):
        rate = {("gpt_small", False): 1.0, ("gpt_small", True): 0.5}
        bridged = hc.vendor_need(rate, [date(2026, 10, 13)])
        after_bridge = hc.vendor_need(rate, [date(2026, 10, 14)])
        retired = hc.vendor_need(rate, [date(2026, 10, 23)])
        assert bridged.get("openai") == 1.0 and bridged.get("openrouter") == 0.5
        assert after_bridge.get("openai") == 1.0 and not after_bridge.get("openrouter")
        assert not retired.get("openai") and not retired.get("openrouter")

    def test_a_balance_you_read_is_drawn_down_by_the_study_and_warns_in_time(self, tmp_path):
        today = NOW.date()
        root = tmp_path / "r"
        tasks, obs, res, ledger = fabricate(today, days=8)
        for name, rows in (("tasks", tasks), ("observations", obs), ("ledger", ledger)):
            jsonl(root / "data" / f"{name}.jsonl", rows)
        ctx = ctx_for(root, tmp_path)
        ctx.state = {"balances": {v: {"usd": 100.0, "as_of": "2026-09-01T00:00:00+00:00"}
                                  for v in ("anthropic", "openai", "google", "openrouter")}}
        ctx.state["balances"]["anthropic"]["usd"] = 1.0
        got = hc._normalise(hc._money_balances(ctx))
        short = [f for f in got if f.status == hc.YOU]
        assert len(short) == 1 and "Anthropic" in short[0].summary and short[0].severity == "high"


class TestSecretsAreFoundAndNeverShown:
    # Assembled at run time: a literal would itself be a key-shaped string in a committed
    # file, and tests/test_no_secrets_committed.py (rightly) fails on that.
    FAKE = "ghp" + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"

    def test_a_key_in_a_committed_file_is_critical_and_not_printed(self, repos, tmp_path):
        origin, mac, job = repos
        write(mac / "notes.md", f"token: {self.FAKE}\n")
        git(mac, "add", "notes.md")
        git(mac, "commit", "-qm", "oops")
        got = hc._normalise(hc._repo_secrets(ctx_for(mac, tmp_path)))
        assert got[0].status == hc.CLAUDE and got[0].severity == "critical"
        assert self.FAKE not in json.dumps([f.as_dict() for f in got])

    def test_a_secret_in_the_prompt_log_is_yours_and_not_printed(self, tmp_path):
        ctx = hc.Ctx(ROOT, now=NOW, http=FakeHttp(), home=tmp_path / "home", state_dir=tmp_path / ".health")
        folder = hc._transcripts_dir(ctx)
        write(folder / "session.jsonl", json.dumps({"message": f"Here is the token: {self.FAKE}"}) + "\n")
        got = hc._normalise(hc._you_prompt_log(ctx))
        you = [f for f in got if f.status == hc.YOU and "secrets" in f.summary]
        assert you and you[0].severity == "high"
        assert self.FAKE not in json.dumps([f.as_dict() for f in got])


class TestLeftovers:
    def test_only_links_into_deleted_scratch_folders_are_removed(self, tmp_path):
        home = tmp_path / "home"
        bin_dir = home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        stale = bin_dir / "python3.11"
        stale.symlink_to("/private/tmp/claude-501/-Users-x/abc/scratchpad/uvpy/bin/python3.11")
        keep = bin_dir / "mytool"
        (tmp_path / "somewhere-real").write_text("")
        keep.symlink_to(tmp_path / "somewhere-real")
        gone = bin_dir / "old-tool"
        gone.symlink_to(tmp_path / "deleted-long-ago")          # dangling, but not ours to judge
        ctx = hc.Ctx(ROOT, now=NOW, http=FakeHttp(), home=home, state_dir=tmp_path / ".health")
        got = hc._normalise(hc._local_leftovers(ctx))
        assert statuses(got) == [hc.FIXED]
        assert not os.path.lexists(stale) and os.path.lexists(keep) and os.path.lexists(gone)


class TestTheVerdict:
    @pytest.mark.parametrize("findings, level, code", [
        ([hc.Finding(hc.OK, "fine")], "green", 0),
        ([hc.Finding(hc.YOU, "a small thing", severity="low")], "green", 0),
        ([hc.Finding(hc.YOU, "soon", severity="high")], "attention", 1),
        ([hc.Finding(hc.CLAUDE, "fix", severity="medium")], "attention", 1),
        ([hc.Finding(hc.CLAUDE, "tidy", severity="low")], "green", 0),
        ([hc.Finding(hc.ERROR, "could not run", severity="medium")], "attention", 1),
        ([hc.Finding(hc.YOU, "today is late", severity="critical")], "red", 2),
    ])
    def test_levels_and_exit_codes(self, findings, level, code):
        v = hc.verdict(findings)
        assert (v["level"], v["exit_code"]) == (level, code)

    def test_all_good_still_counts_the_small_things(self):
        v = hc.verdict([hc.Finding(hc.YOU, "x", severity="low"), hc.Finding(hc.YOU, "y", severity="medium")])
        assert v["headline"].startswith("ALL GOOD") and "2 small things for you" in v["headline"]


class TestParsingTheSuite:
    def test_the_summary_line(self):
        out = ("....\nFAILED tests/test_x.py::test_a - AssertionError: boom\n"
               "=== 2 failed, 979 passed, 2 skipped, 1 warning in 86.69s (0:01:26) ===\n")
        assert hc._pytest_summary(out) == {"failed": 2, "passed": 979, "skipped": 2}
        assert hc._failing_tests(out) == ["FAILED tests/test_x.py::test_a"]

    def test_a_clean_run(self):
        assert hc._pytest_summary("981 passed, 2 skipped, 1 warning in 36.21s") == {"passed": 981, "skipped": 2}


def test_times_are_read_the_way_this_project_writes_them():
    assert hc._ts("2026-09-29T00:20:10.505204+00:00").minute == 20
    assert hc._ts("2026-10-02T12:29:00Z").tzinfo is not None
    assert hc._ts("2026‑03‑26").date() == date(2026, 3, 26)
    assert hc._ts("2026-08-24T23:25:46.943042").tzinfo is not None
    assert hc._ts("2026-09-17T13:28:44.50489Z").second == 44
    assert hc._ts("") is None and hc._ts("not a time") is None

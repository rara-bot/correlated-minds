"""The front page shows the record, and nothing that keeps it there touches the record.

The repository's default branch is `front`, whose only commits are copies of
`main`'s files (scripts/front_page.py says why). `main` is the record: every commit
id the registration, the addenda and the Week-5 prediction cite is on it. So the
promises pinned here are about what can never happen to `main`, and about `front`
being nothing but a copy:

- `front` is created once, as a single commit with no parent, holding `main`'s files.
- Each later copy is one commit on top of `front`; `main` is never pushed, rebased
  or rewritten, and `front` never comes to contain one of `main`'s commits -- or a
  line naming a co-author, which is what the front page's contributor list reads.
- A copy that cannot be pushed reports failure and leaves `main` exactly as it was.
- A change to the workflows on `main` is flagged until it reaches `front`, because
  GitHub schedules the daily job from the default branch's copy.

Every test runs the real script against throwaway repositories; none touches the
network or this repository's remote.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import front_page as fp

SCRIPT = Path(fp.__file__).resolve()

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
pytestmark = needs_git


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, path: str, text: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", message)
    _git(repo, "push", "-q", "origin", "main")
    return _git(repo, "rev-parse", "HEAD")


def _heads(remote: Path) -> dict:
    rows = _git(remote, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
    return dict(line.split() for line in rows.splitlines() if line)


@pytest.fixture
def repos(tmp_path):
    """(remote, seed, work): a bare remote whose `main` has a history that includes a
    co-author line, the clone that writes the record, and the clone that keeps the
    front page (the runner, or the operator's copy)."""
    remote, seed, work = tmp_path / "remote.git", tmp_path / "seed", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(tmp_path, "clone", "-q", str(remote), str(seed))
    for repo in (seed,):
        _git(repo, "config", "user.name", "researcher")
        _git(repo, "config", "user.email", "researcher@example.com")
    _git(seed, "checkout", "-q", "-b", "main")
    _commit(seed, "README.md", "# A study\n", "Start")
    _commit(seed, ".github/workflows/daily.yml", "on: {schedule: [{cron: '10 13 * * *'}]}\n",
            "Collect daily\n\nCo-authored-by: Someone Else <someone@example.com>")
    _commit(seed, "data/observations.jsonl", '{"day": 1}\n', "data: collection for day 1")
    _git(tmp_path, "clone", "-q", str(remote), str(work))
    _git(work, "config", "user.name", "neff-collector")
    _git(work, "config", "user.email", "actions@github.com")
    return remote, seed, work


def _new_day(seed: Path, n: int) -> str:
    log = seed / "data" / "observations.jsonl"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"day": n}) + "\n")
    _git(seed, "add", "data/observations.jsonl")
    _git(seed, "commit", "-q", "-m", f"data: collection for day {n}")
    _git(seed, "push", "-q", "origin", "main")
    return _git(seed, "rev-parse", "HEAD")


class TestFrontIsCreatedOnceAsACopy:
    def test_nothing_happens_without_a_front_branch(self, repos):
        remote, _, work = repos
        before = _heads(remote)
        status, text = fp.show(cwd=work)
        assert status == "absent" and "nothing to show" in text
        assert _heads(remote) == before and "front" not in before

    def test_init_creates_one_parentless_copy_of_main(self, repos):
        remote, _, work = repos
        main_head = _heads(remote)["main"]
        status, _ = fp.init(cwd=work)
        assert status == "created"
        front = _heads(remote)["front"]
        assert _git(remote, "rev-list", "--count", front) == "1"
        assert _git(remote, "log", "-1", "--format=%P", front) == ""          # no parent: no history
        assert _git(remote, "rev-parse", f"{front}^{{tree}}") == _git(remote, "rev-parse", f"{main_head}^{{tree}}")
        assert _git(remote, "log", "-1", "--format=%s", front) == f"Show main at {main_head[:7]}"

    def test_init_never_overwrites_an_existing_front(self, repos):
        remote, _, work = repos
        fp.init(cwd=work)
        first = _heads(remote)["front"]
        status, _ = fp.init(cwd=work)
        assert status == "exists" and _heads(remote)["front"] == first


class TestFrontFollowsMain:
    def test_a_new_day_on_main_is_copied(self, repos):
        remote, seed, work = repos
        fp.init(cwd=work)
        before = _heads(remote)["front"]
        day2 = _new_day(seed, 2)
        status, text = fp.show(cwd=work, wait=0)
        assert status == "updated" and day2[:7] in text
        front = _heads(remote)["front"]
        assert _git(remote, "log", "-1", "--format=%P", front) == before   # one commit on top of front
        assert _git(remote, "rev-parse", f"{front}^{{tree}}") == _git(remote, "rev-parse", f"{day2}^{{tree}}")

    def test_running_again_changes_nothing(self, repos):
        remote, seed, work = repos
        fp.init(cwd=work)
        _new_day(seed, 2)
        fp.show(cwd=work, wait=0)
        settled = _heads(remote)
        status, _ = fp.show(cwd=work, wait=0)
        assert status == "current" and _heads(remote) == settled

    def test_main_is_never_written(self, repos):
        remote, seed, work = repos
        fp.init(cwd=work)
        for n in (2, 3):
            day = _new_day(seed, n)
            fp.show(cwd=work, wait=0)
            assert _heads(remote)["main"] == day

    def test_front_carries_none_of_mains_commits_or_co_author_lines(self, repos):
        remote, seed, work = repos
        fp.init(cwd=work)
        _new_day(seed, 2)
        fp.show(cwd=work, wait=0)
        st = fp.state(cwd=work)
        assert st.front_exists and st.shows_record
        assert st.co_author_lines == 0 and st.record_commits_in_front == 0
        front = _heads(remote)["front"]
        for commit in _git(remote, "rev-list", "main").split():
            reached = subprocess.run(["git", "merge-base", "--is-ancestor", commit, front], cwd=remote)
            assert reached.returncode == 1, f"main's commit {commit[:7]} is reachable from front"

    def test_a_workflow_change_is_flagged_until_copied(self, repos):
        _, seed, work = repos
        fp.init(cwd=work)
        _commit(seed, ".github/workflows/daily.yml", "on: {schedule: [{cron: '41 16 * * *'}]}\n", "Move a slot")
        st = fp.state(cwd=work)
        assert not st.shows_record and st.workflows_differ
        assert ".github/workflows/daily.yml" in st.differs_in
        fp.show(cwd=work, wait=0)
        st = fp.state(cwd=work)
        assert st.shows_record and not st.workflows_differ


class TestAFailureNeverTouchesTheRecord:
    def test_a_rejected_copy_reports_failed_and_leaves_main(self, repos):
        remote, seed, work = repos
        fp.init(cwd=work)
        front = _heads(remote)["front"]
        hook = remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nwhile read old new ref; do\n"
                        "  [ \"$ref\" = refs/heads/front ] && { echo 'front is locked' >&2; exit 1; }\n"
                        "done\nexit 0\n", encoding="utf-8")
        hook.chmod(0o755)
        day2 = _new_day(seed, 2)                       # main still accepts the record
        status, text = fp.show(cwd=work, attempts=2, wait=0)
        assert status == "failed" and "unaffected" in text
        assert _heads(remote) == {"main": day2, "front": front}

    def test_an_unreachable_remote_is_a_warning_not_a_crash(self, repos, tmp_path):
        _, _, work = repos
        _git(work, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
        done = subprocess.run([sys.executable, str(SCRIPT)], cwd=work, capture_output=True, text=True)
        assert done.returncode == 1
        assert "::warning::front page not updated" in done.stdout
        assert "Traceback" not in done.stderr


class TestTheCommandLine:
    def _run(self, work: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=work, capture_output=True, text=True)

    def test_init_check_and_show(self, repos):
        _, seed, work = repos
        made = self._run(work, "--init")
        assert made.returncode == 0 and "front created, showing main" in made.stdout
        checked = json.loads(self._run(work, "--check", "--json").stdout)
        assert checked["front_exists"] and checked["shows_record"]
        assert checked["co_author_lines"] == 0 and checked["record_commits_in_front"] == 0
        day2 = _new_day(seed, 2)
        shown = self._run(work)
        assert shown.returncode == 0 and f"front now shows main at {day2[:7]}" in shown.stdout
        assert "shows main" in self._run(work, "--check").stdout

    def test_check_changes_nothing(self, repos):
        remote, seed, work = repos
        fp.init(cwd=work)
        _new_day(seed, 2)
        before = _heads(remote)
        report = self._run(work, "--check")
        assert report.returncode == 0 and "differs from main" in report.stdout
        assert _heads(remote) == before

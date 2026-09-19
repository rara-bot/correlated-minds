"""The daily job must never report a day as saved when it was not.

The data a run collects exists only on the runner until "Commit the day" pushes it.
Until 2026-09-19 that step retried the push three times and then ended on `sleep`,
which succeeds -- so a push that never landed finished green, the day's data went
with the runner, and the alarm, which reads the job's status, had nothing to report.

Pinned here by running the step itself, extracted from the workflow, against a
throwaway repository whose remote cannot be reached. Also pinned: the alarm runs
after the commit, so it sees that failure; and both workflows run on a named
image with actions that run on Node 24, so neither changes under the study
mid-collection (daily.yml says why).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# Read as text, like every other test that reads a workflow. PyYAML is not in
# requirements.txt, and this suite runs inside the daily job before anything is
# collected: an import it cannot satisfy there would cost the day.
STEP = re.compile(r"^      - (?:name|uses): (.+)$", re.M)


def _text(name: str = "daily.yml") -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _steps(name: str = "daily.yml"):
    """[(title, block)] for each step, in order."""
    text = _text(name)
    heads = list(STEP.finditer(text))
    return [(m.group(1).strip(), text[m.start(): heads[i + 1].start() if i + 1 < len(heads) else len(text)])
            for i, m in enumerate(heads)]


def _step(title: str) -> str:
    return next(block for name, block in _steps() if name == title)


def _names():
    return [name for name, _ in _steps()]


def _run_script(block: str) -> str:
    """The body of a step's `run: |` literal block."""
    lines = block.split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip() == "run: |") + 1
    body = []
    for line in lines[start:]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line)
    return textwrap.dedent("\n".join(body))


needs_git = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None,
                               reason="needs git and bash")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def runner_checkout(tmp_path):
    """A checkout of a one-commit repository, with a day of data staged to commit."""
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(tmp_path, "clone", "-q", str(remote), str(work))
    _git(work, "config", "user.name", "t")
    _git(work, "config", "user.email", "t@t")
    _git(work, "checkout", "-q", "-b", "main")
    (work / "data").mkdir()
    (work / "data" / "observations.jsonl").write_text('{"day": 1}\n', encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "push", "-q", "origin", "main")
    with (work / "data" / "observations.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"day": 2}\n')
    return work, remote


def _run_commit_step(work: Path):
    # The waits are real minutes in CI; here they only need to happen.
    script = "sleep() { :; }\n" + _run_script(_step("Commit the day"))
    env = {"GITHUB_REF_NAME": "main", "PATH": subprocess.os.environ["PATH"],
           "HOME": str(work.parent)}
    return subprocess.run(["bash", "-e", "-c", script], cwd=work, env=env,
                          capture_output=True, text=True)


@needs_git
class TestADayIsNeverReportedSavedWhenItWasNot:
    def test_a_push_that_lands_succeeds(self, runner_checkout):
        work, remote = runner_checkout
        done = _run_commit_step(work)
        assert done.returncode == 0, done.stderr
        assert "pushed on attempt 1" in done.stdout
        log = subprocess.run(["git", "log", "--oneline", "main"], cwd=remote,
                             capture_output=True, text=True).stdout
        assert "data: collection for" in log

    def test_a_push_that_never_lands_fails_the_step(self, runner_checkout):
        work, _ = runner_checkout
        _git(work, "remote", "set-url", "origin", str(work.parent / "gone.git"))
        done = _run_commit_step(work)
        assert done.returncode == 1
        assert "could not be pushed" in done.stdout

    def test_a_conflict_is_not_left_half_rebased(self, runner_checkout, tmp_path):
        work, remote = runner_checkout
        other = tmp_path / "other"
        _git(tmp_path, "clone", "-q", str(remote), str(other))
        _git(other, "config", "user.name", "o")
        _git(other, "config", "user.email", "o@o")
        with (other / "data" / "observations.jsonl").open("a", encoding="utf-8") as fh:
            fh.write('{"someone": "else"}\n')
        _git(other, "commit", "-q", "-am", "a second writer")
        _git(other, "push", "-q", "origin", "main")
        done = _run_commit_step(work)
        assert done.returncode == 1
        assert not (work / ".git" / "rebase-merge").exists()
        assert not (work / ".git" / "rebase-apply").exists()

    def test_nothing_new_is_not_a_failure(self, runner_checkout):
        work, _ = runner_checkout
        _git(work, "checkout", "--", "data/")
        done = _run_commit_step(work)
        assert done.returncode == 0 and "no new data" in done.stdout


class TestTheAlarmSeesTheCommit:
    def test_the_alarm_runs_after_the_commit_and_always(self):
        names = _names()
        assert names.index("Raise an alarm if a day is at risk") > names.index("Commit the day")
        assert re.search(r"^        if: always\(\)$", _step("Raise an alarm if a day is at risk"), re.M)

    def test_it_reads_the_job_status(self):
        assert "JOB_STATUS: ${{ job.status }}" in _step("Raise an alarm if a day is at risk")

    def test_there_is_exactly_one_alarm(self):
        assert _names().count("Raise an alarm if a day is at risk") == 1


class TestTheMachineDoesNotChangeUnderTheStudy:
    # The first major of each action that declares `runs.using: node24`.
    NODE24 = {"actions/checkout": 5, "actions/setup-python": 6, "actions/upload-artifact": 6}

    @pytest.mark.parametrize("workflow", ["daily.yml", "tests.yml"])
    def test_a_named_image(self, workflow):
        images = re.findall(r"^\s*runs-on:\s*(\S+)", _text(workflow), re.M)
        assert images == ["ubuntu-24.04"]

    @pytest.mark.parametrize("workflow", ["daily.yml", "tests.yml"])
    def test_actions_that_run_on_node_24(self, workflow):
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", _text(workflow), re.M)
        assert uses, "no actions found"
        for ref in uses:
            action, _, version = ref.partition("@")
            major = int(re.match(r"v(\d+)", version).group(1))
            assert major >= self.NODE24[action], f"{ref} declares node20"

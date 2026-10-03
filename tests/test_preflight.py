"""Readiness checks must not report readiness they have not established.

`scripts/preflight.py` exists because a mock run on 17 Aug looked identical to a
real one and was mistaken for a completed setup. Two of its own checks then had
the same defect:

  * step 6 printed "[done] Pushed to a public GitHub repo" as soon as `git
    remote -v` returned anything. The remote was an EMPTY GitHub repo with no
    branches, so the public timestamped commit history -- the evidence the whole
    study rests on -- did not exist, and the check said it did.
  * step 2 asked whether every model had answered for real by reading
    `observations.jsonl`, but `neff.verify` writes no observations. The step
    could never pass, and its remediation told the operator to run the very
    command they had just run.

These tests use real git repositories with a local bare remote, so the push
check is exercised against actual git behaviour rather than a mock of it.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "preflight.py"


def _load(root):
    spec = importlib.util.spec_from_file_location(f"preflight_{root.name}", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT = root
    return mod


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A git repo with one commit, no remote."""
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    (work / "README.md").write_text("x\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "first")
    return work


@pytest.fixture
def bare(tmp_path):
    b = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(b)], check=True)
    return b


class TestPushState:
    def test_no_remote_is_not_pushed(self, repo):
        pushed, detail, remedy = _load(repo)._push_state()
        assert not pushed
        assert "no git remote" in detail
        assert "git remote add origin" in remedy

    def test_remote_configured_but_empty_is_not_pushed(self, repo, bare):
        """The exact false pass this check used to produce: the GitHub repo
        exists and is browsable, and holds nothing."""
        _git(repo, "remote", "add", "origin", str(bare))
        pushed, detail, remedy = _load(repo)._push_state()
        assert not pushed, "an empty remote must never report as pushed"
        assert "nothing has been pushed" in detail
        assert "git push" in remedy

    def test_pushed_and_up_to_date(self, repo, bare):
        _git(repo, "remote", "add", "origin", str(bare))
        _git(repo, "push", "-q", "-u", "origin", "main")
        pushed, detail, _ = _load(repo)._push_state()
        assert pushed
        assert "up to date" in detail

    def test_unpushed_commits_are_reported(self, repo, bare):
        """The freeze commit is the one that must reach the remote. Silently
        counting a stale remote as current would publish a hash nobody can
        check against the repository."""
        _git(repo, "remote", "add", "origin", str(bare))
        _git(repo, "push", "-q", "-u", "origin", "main")
        (repo / "PREREGISTRATION.md").write_text("frozen\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "Freeze pre-registration")
        pushed, detail, remedy = _load(repo)._push_state()
        assert not pushed
        assert "1 local commit(s) not pushed" in detail
        assert "git push origin main" in remedy

    def test_unreachable_remote_reports_rather_than_crashes(self, repo, tmp_path):
        _git(repo, "remote", "add", "origin", str(tmp_path / "does-not-exist.git"))
        pushed, detail, _ = _load(repo)._push_state()
        assert not pushed
        assert "could not reach" in detail


class TestIsCommitted:
    def test_untracked_file_is_not_committed(self, repo):
        (repo / ".osf_url").write_text("https://osf.io/ab12c\n")
        assert not _load(repo)._is_committed(".osf_url")

    def test_committed_file_is_committed(self, repo):
        (repo / ".osf_url").write_text("https://osf.io/ab12c\n")
        _git(repo, "add", ".osf_url")
        _git(repo, "commit", "-q", "-m", "Record OSF registration")
        assert _load(repo)._is_committed(".osf_url")

    def test_missing_file_is_not_committed(self, repo):
        assert not _load(repo)._is_committed(".osf_url")


class TestVerificationReceipts:
    """Step 2 reads the receipts `neff.verify` leaves behind. Without them the
    step is unsatisfiable, which is how a blocking check becomes noise the
    operator learns to ignore."""

    @pytest.fixture
    def verify_mod(self, tmp_path, monkeypatch):
        from neff import verify

        monkeypatch.setattr(verify, "VERIFICATION_PATH", tmp_path / "verification.jsonl")
        return verify

    def test_no_receipts_means_nothing_verified(self, verify_mod):
        assert verify_mod.verified_models() == {}

    def test_successful_probe_is_recorded(self, verify_mod):
        verify_mod.VERIFICATION_PATH.write_text(
            json.dumps({"model_key": "gpt_mid", "ok": True,
                        "model_id_returned": "gpt-4.1-mini-2025-04-14",
                        "checked_at": "2026-08-21T01:00:00+00:00"}) + "\n"
        )
        got = verify_mod.verified_models()
        assert set(got) == {"gpt_mid"}
        assert got["gpt_mid"]["model_id_returned"] == "gpt-4.1-mini-2025-04-14"

    def test_failed_probe_does_not_count_as_verified(self, verify_mod):
        """A model that errored must not satisfy the check that says it
        answered."""
        verify_mod.VERIFICATION_PATH.write_text(
            json.dumps({"model_key": "qwen", "ok": False, "error": "401"}) + "\n"
        )
        assert verify_mod.verified_models() == {}

    def test_later_probe_supersedes_earlier(self, verify_mod):
        verify_mod.VERIFICATION_PATH.write_text(
            json.dumps({"model_key": "llama", "ok": True, "model_id_returned": "old",
                        "checked_at": "2026-08-19T01:00:00+00:00"}) + "\n"
            + json.dumps({"model_key": "llama", "ok": True, "model_id_returned": "new",
                          "checked_at": "2026-08-21T01:00:00+00:00"}) + "\n"
        )
        assert verify_mod.verified_models()["llama"]["model_id_returned"] == "new"

    def test_corrupt_line_is_skipped_not_fatal(self, verify_mod):
        """A torn write must not take down the readiness check."""
        verify_mod.VERIFICATION_PATH.write_text(
            "{not json\n"
            + json.dumps({"model_key": "deepseek", "ok": True,
                          "model_id_returned": "deepseek/deepseek-v3.2"}) + "\n"
        )
        assert set(verify_mod.verified_models()) == {"deepseek"}

    def test_receipt_path_is_inside_data(self, verify_mod):
        from neff import verify

        importlib.reload(verify)
        assert verify.VERIFICATION_PATH.parent.name == "data"
        assert verify.VERIFICATION_PATH.name == "verification.jsonl"

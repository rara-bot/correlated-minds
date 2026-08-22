"""No file carrying a real credential may be committable.

This repository is public, and `GO-LIVE.md` instructs the operator to run
`git add -A` right after freezing the pre-registration. That combination means a
single unignored file holding an API key is published permanently -- and a leaked
key is not fixable by editing the file afterwards, only by rotating every key it
contained.

It very nearly happened. Updating `.env` created a timestamped backup:

    .env.backup-20260822-154022

`.gitignore` listed `.env`, which matches that exact name and nothing else. The
backup -- containing all four live API keys -- was untracked, unignored, and
sitting directly in the path of the next `git add -A`.

So the rule is no longer "remember to ignore the backup". It is: any path that
looks like it holds a credential must be ignored, and no tracked file may contain
anything shaped like a key.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Shapes of the credentials this project actually uses. Prefix plus a length
# floor, so a placeholder like `sk-xxx` in documentation does not trip it.
KEY_PATTERNS = [
    ("Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{40,}")),
    ("OpenAI", re.compile(r"sk-proj-[A-Za-z0-9_\-]{40,}")),
    ("OpenRouter", re.compile(r"sk-or-v1-[A-Za-z0-9_\-]{40,}")),
    ("Google", re.compile(r"AQ\.[A-Za-z0-9_\-]{30,}")),
    ("Google (legacy)", re.compile(r"AIza[A-Za-z0-9_\-]{30,}")),
    ("GitHub PAT", re.compile(r"ghp_[A-Za-z0-9]{30,}")),
    ("GitHub fine-grained", re.compile(r"github_pat_[A-Za-z0-9_]{50,}")),
]


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True
    ).stdout.splitlines()


def _is_ignored(path: str) -> bool:
    return subprocess.run(
        ["git", "check-ignore", "-q", path], cwd=ROOT
    ).returncode == 0


class TestEnvFilesAreIgnored:
    @pytest.mark.parametrize(
        "name",
        [
            ".env",
            ".env.backup",
            ".env.backup-20260822-154022",
            ".env.local",
            ".env.old",
            ".env.bak",
            ".env.save",
            ".env.2",
        ],
    )
    def test_every_env_variant_is_ignored(self, name):
        """`.gitignore` listed only `.env`, which matches that exact name and
        nothing else. Every backup, copy or editor artifact was exposed."""
        assert _is_ignored(name), f"{name} would be swept up by `git add -A`"

    def test_the_template_is_still_tracked(self):
        """`.env.example` carries no secrets and documents the required names,
        so the ignore rule must not swallow it."""
        assert ".env.example" in _git("ls-files")

    def test_template_contains_no_real_key(self):
        text = (ROOT / ".env.example").read_text()
        for label, pattern in KEY_PATTERNS:
            assert not pattern.search(text), f"{label} key found in .env.example"


class TestNothingSecretIsTracked:
    def test_no_tracked_file_matches_a_credential_shape(self):
        """The decisive check: scan everything git actually has."""
        offenders = []
        for rel in _git("ls-files"):
            p = ROOT / rel
            if not p.is_file() or p.stat().st_size > 2_000_000:
                continue
            try:
                text = p.read_text(errors="ignore")
            except OSError:
                continue
            for label, pattern in KEY_PATTERNS:
                m = pattern.search(text)
                if m:
                    offenders.append(f"{rel}: {label} ({m.group(0)[:12]}...)")
        assert not offenders, "credentials in tracked files:\n  " + "\n  ".join(offenders)

    def test_dotenv_itself_is_not_tracked(self):
        assert ".env" not in _git("ls-files")


class TestNothingSecretIsStaged:
    """Catches the moment before it becomes permanent."""

    def test_no_untracked_unignored_file_looks_like_a_secret(self):
        risky = re.compile(r"(^|/)\.env|secret|credential|\.pem$|\.key$", re.I)
        exposed = []
        for line in _git("status", "--porcelain", "--untracked-files=all"):
            path = line[3:].strip().strip('"')
            if not path or path.startswith("tests/"):
                continue
            if risky.search(path) and not _is_ignored(path):
                exposed.append(path)
        assert not exposed, (
            "untracked, unignored, and secret-shaped -- `git add -A` would "
            f"publish these: {exposed}"
        )

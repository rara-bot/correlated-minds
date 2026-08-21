"""Real collection must be impossible before the OSF registration is public.

The study's core claim is "registered before the outcome existed". Data collected
before the registration goes public cannot support it, and the failure is silent
-- a premature run looks completely normal at the time and only becomes a problem
months later when someone asks how they know the plan came first. So this is
enforced in code, like the budget cap, rather than remembered.
"""

import pytest

from neff import collect


@pytest.fixture
def osf_path(tmp_path, monkeypatch):
    p = tmp_path / ".osf_url"
    monkeypatch.setattr(collect, "OSF_URL_PATH", p)
    return p


def _call(arm="ws1_prospective", dry_run=False, use_mock=False):
    collect.require_osf_before_real_collection(
        arm=arm, dry_run=dry_run, use_mock=use_mock
    )


class TestGate:
    def test_real_arm_blocked_when_unregistered(self, osf_path):
        with pytest.raises(SystemExit, match="REFUSING TO COLLECT"):
            _call()

    def test_real_arm_blocked_when_url_file_is_empty(self, osf_path):
        """A file created as a placeholder must not count as registered."""
        osf_path.write_text("   \n")
        with pytest.raises(SystemExit, match="REFUSING TO COLLECT"):
            _call()

    def test_real_arm_allowed_once_url_recorded(self, osf_path):
        osf_path.write_text("https://osf.io/ab12c\n")
        _call()

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"use_mock": True},          # touches nothing real
            {"dry_run": True},           # prices only, asks nothing
            {"arm": "pilot"},            # separately registered arm
        ],
        ids=["mock", "dry_run", "pilot"],
    )
    def test_escape_hatches_remain_open(self, osf_path, kwargs):
        _call(**kwargs)

    def test_every_non_pilot_arm_is_gated(self, osf_path):
        """A new arm added to config must be gated by default, not by being
        remembered. Only `pilot` is exempt."""
        from neff.config import ARM_CAPS_USD

        for arm in ARM_CAPS_USD:
            if arm in collect.PRE_REGISTRATION_ARMS:
                continue
            with pytest.raises(SystemExit):
                _call(arm=arm)


class TestPlaceholdersDoNotOpenTheGate:
    """The original check was "the file is non-empty", which any placeholder
    satisfies. A gate that `echo pending > .osf_url` opens is not a gate."""

    @pytest.mark.parametrize(
        "text",
        ["pending", "TODO", "osf.io/ab12c", "see email", "-", "https://", "n/a"],
    )
    def test_non_url_content_is_refused(self, osf_path, text, monkeypatch):
        monkeypatch.delenv(collect.OSF_URL_ENV, raising=False)
        osf_path.write_text(text + "\n")
        with pytest.raises(SystemExit, match="REFUSING TO COLLECT"):
            _call()

    @pytest.mark.parametrize(
        "url",
        [
            "https://osf.io/ab12c",
            "https://osf.io/ab12c/",
            "http://osf.io/ab12c",
            "https://aspredicted.org/blind.php?x=ab12cd",
        ],
    )
    def test_real_urls_are_accepted(self, osf_path, url, monkeypatch):
        """AsPredicted is the documented fallback if OSF is not done in time, so
        the check must not be hard-wired to one host."""
        monkeypatch.delenv(collect.OSF_URL_ENV, raising=False)
        osf_path.write_text(url + "\n")
        _call()

    def test_surrounding_whitespace_is_tolerated(self, osf_path, monkeypatch):
        monkeypatch.delenv(collect.OSF_URL_ENV, raising=False)
        osf_path.write_text("\n  https://osf.io/ab12c  \n\n")
        _call()


class TestCIReadsTheRegistrationFromTheRepo:
    """The scheduled job runs from a fresh checkout. A `.osf_url` written on the
    operator's laptop and never committed is invisible to it, so every automated
    collection day would fail on a registration that plainly exists. The env
    override exists so that failure has a remedy that does not need a commit."""

    def test_env_var_satisfies_the_gate_with_no_file(self, osf_path, monkeypatch):
        assert not osf_path.exists()
        monkeypatch.setenv(collect.OSF_URL_ENV, "https://osf.io/ab12c")
        _call()

    def test_env_var_placeholder_is_still_refused(self, osf_path, monkeypatch):
        monkeypatch.setenv(collect.OSF_URL_ENV, "pending")
        with pytest.raises(SystemExit, match="REFUSING TO COLLECT"):
            _call()

    def test_file_is_used_when_env_is_absent(self, osf_path, monkeypatch):
        monkeypatch.delenv(collect.OSF_URL_ENV, raising=False)
        osf_path.write_text("https://osf.io/ab12c\n")
        assert collect.registered_osf_url() == "https://osf.io/ab12c"

    def test_error_message_says_to_commit_the_file(self, osf_path, monkeypatch):
        """Naming the actual cause is the difference between a five-minute fix
        and a lost collection day."""
        monkeypatch.delenv(collect.OSF_URL_ENV, raising=False)
        with pytest.raises(SystemExit) as exc:
            _call()
        assert "git add .osf_url" in str(exc.value)
        assert "fresh" in str(exc.value)


class TestTheGateIsNotIgnored:
    def test_url_file_is_not_gitignored(self):
        """`.osf_url` must be committable -- if it were ignored, the CI checkout
        could never see it and the study would run on the env override alone."""
        from pathlib import Path

        root = Path(collect.__file__).resolve().parent.parent
        ignored = (root / ".gitignore").read_text().splitlines()
        assert ".osf_url" not in [line.strip() for line in ignored]

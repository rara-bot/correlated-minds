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

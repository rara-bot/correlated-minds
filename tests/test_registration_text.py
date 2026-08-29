"""The text pasted into OSF becomes immutable. It must agree with the plan.

`OSF.md` carries field-by-field, paste-ready text for the OSF registration form.
That text — not `PREREGISTRATION.md` — is what ends up in the registry, and an
OSF registration cannot be edited after submission. It can only be withdrawn,
leaving a public tombstone.

Six of its fields had drifted out of step with the plan they mirror. The one that
mattered most was the state-variable list: it named six, omitting
`ladder_distance`. That count is the Benjamini-Hochberg denominator, so
registering six while the analysis corrects across seven would have set H1's
falsification threshold to a value the study does not use — permanently, in the
one document where finding 12 could not be corrected later.

These tests bind the paste-ready text to `config.py` and to the plan, so the
three can never disagree again.
"""

import re
from pathlib import Path

import pytest

from neff import config

ROOT = Path(__file__).resolve().parent.parent
OSF = ROOT / "OSF.md"
PREREG = ROOT / "PREREGISTRATION.md"


@pytest.fixture(scope="module")
def osf():
    return OSF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prereg():
    return PREREG.read_text(encoding="utf-8")


class TestPanelSize:
    def test_no_stale_seven_model_claim(self, osf):
        """The panel has been nine since the H3 fix. "seven" is the pre-audit
        count and would have gone into the registry."""
        assert "seven language models" not in osf
        assert "seven models" not in osf

    def test_sample_size_uses_the_primary_panel_size(self, osf):
        m = re.search(r"25 task-days x (\d+) models x 105", osf)
        assert m, "sample-size field not found in the expected form"
        assert int(m.group(1)) == len(config.primary_panel()) == 9

    def test_sample_size_total_matches_the_plan(self, osf, prereg):
        """Two different observation counts in two registered documents is the
        first arithmetic a reviewer checks."""
        assert "23,625" in osf
        assert "23,625" in prereg

    def test_the_tenth_model_is_disclosed(self, osf):
        """The public log shows ten model ids. A registration naming nine
        invites the one question a pre-registered study cannot answer later."""
        assert "tenth model" in osf.lower()
        assert "all ten models" in osf

    def test_no_model_named_that_the_panel_does_not_use(self, osf):
        assert "Claude Sonnet 5" not in osf


class TestStateVariables:
    """The count is the BH denominator and therefore H1's falsification
    threshold."""

    def test_says_seven_not_six(self, osf):
        assert "seven registered state variables" in osf
        assert "six registered state variables" not in osf

    def test_every_registered_variable_is_named(self, osf):
        prose = {
            "ladder_distance": "ladder distance",
            "vix_level": "VIX level",
            "realized_vol_20d": "20-day realised volatility",
            "expectation_dispersion": "cross-model forecast dispersion",
            "abs_surprise": "absolute macro surprise",
            "days_out": "days to resolution",
            "novelty_score": "novelty score",
        }
        assert set(prose) == set(config.STATE_VARIABLES)
        missing = [v for v, phrase in prose.items() if phrase not in osf]
        assert not missing, f"registered but absent from the OSF text: {missing}"

    def test_ask_time_variables_are_flagged_as_irrecoverable(self, osf):
        """They cannot be reconstructed after the fact, which is worth stating
        in the registration rather than discovering in December."""
        assert "recorded at ask time" in osf


class TestTheOrderIsStillCorrect:
    """Freeze before registering. If the hash is published before the document
    is stamped, the two cannot match and the belt-and-braces claim is lost."""

    def test_walkthrough_puts_the_freeze_before_the_registration(self, osf):
        freeze = osf.index("## Step 3 — Freeze and hash")
        register = osf.index("## Step 5 — Create the registration")
        assert freeze < register

    def test_the_ordering_rule_is_stated_explicitly(self, osf):
        assert "Step 3 before step 5 is non-negotiable" in osf


class TestCollectionCannotStartWithoutTheCommit:
    def test_walkthrough_says_to_commit_the_url(self, osf):
        """`.osf_url` is read from a fresh checkout by the scheduled job. A URL
        written only on the operator's laptop fails every collection day."""
        assert "git add .osf_url" in osf
        assert "commit is not optional" in osf

    def test_env_alternative_is_documented(self, osf):
        assert "OSF_URL" in osf


class TestDatesAgree:
    @pytest.mark.parametrize(
        "needle", ["29 Aug 2026", "11 Dec 2026"]
    )
    def test_key_dates_appear_in_both_documents(self, osf, prereg, needle):
        assert needle in osf
        assert needle in prereg

    def test_dates_match_the_code(self, prereg):
        assert config.COLLECTION_START == "2026-08-29"
        assert config.DATA_FREEZE == "2026-12-11"
        assert "**Collection begins:** 29 Aug 2026" in prereg

    def test_stopping_rule_is_the_registered_freeze_date(self, osf):
        assert "data freeze on 11 Dec 2026" in osf
        assert "never data-dependent" in osf

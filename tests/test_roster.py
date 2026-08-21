"""The registered roster and the running code must be the same roster.

§9 freezes the model roster. After the freeze the pre-registration cannot be
edited, so any disagreement between what the document says and what the daily
job actually queries is permanent, public, and exactly the kind of thing a
reviewer checks first: they open the log, count the model ids, and compare.

This is not hypothetical. Before these tests existed, §3.1 named
"Claude Sonnet 5" as the frontier anchor while `config.py` pinned
`claude-sonnet-4-6` -- the repin from AUDIT.md finding 13 reached the code and
never reached the document. Freezing in that state would have registered a model
the study does not use, forever. Separately, the tenth model (`gpt_frontier`)
was collected daily and named nowhere in the registration at all.

So §3.1 now carries an explicit roster table and these tests hold it to the code
in both directions: nothing in the code may be missing from the document, and
nothing in the document may be missing from the code.
"""

import re
from pathlib import Path

import pytest

from neff import config

ROOT = Path(__file__).resolve().parent.parent
PREREG = ROOT / "PREREGISTRATION.md"

ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|"
    r"\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$"
)


def _registered_roster():
    """Parse the roster table out of §3.1."""
    rows = {}
    for line in PREREG.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        _n, key, provider, model_id, family, tier, panel = m.groups()
        rows[key] = {
            "provider": provider.strip(),
            "model_id": model_id.strip(),
            "family": family.strip(),
            "tier": tier.strip(),
            "panel": panel.strip().replace("*", "").lower(),
        }
    return rows


@pytest.fixture(scope="module")
def registered():
    r = _registered_roster()
    assert r, "no roster table found in PREREGISTRATION.md §3.1"
    return r


class TestRosterMatchesCode:
    def test_every_collected_model_is_registered(self, registered):
        """A model queried daily but absent from the registration is an
        undeclared arm in a public log."""
        missing = [m.key for m in config.enabled_panel() if m.key not in registered]
        assert not missing, f"collected but not registered: {missing}"

    def test_every_registered_model_is_collected(self, registered):
        """A model registered but never queried is a promise not kept."""
        keys = {m.key for m in config.enabled_panel()}
        assert not [k for k in registered if k not in keys]

    @pytest.mark.parametrize("field", ["provider", "model_id", "family", "tier"])
    def test_field_matches_exactly(self, registered, field):
        for spec in config.enabled_panel():
            assert getattr(spec, field) == registered[spec.key][field], (
                f"{spec.key}.{field}: code={getattr(spec, field)!r} "
                f"document={registered[spec.key][field]!r}"
            )

    def test_primary_secondary_split_matches(self, registered):
        """The document's `panel` column is what tells a reader which models
        enter the confirmatory estimates."""
        for spec in config.enabled_panel():
            expected = "primary" if spec.primary else "secondary"
            assert registered[spec.key]["panel"] == expected, (
                f"{spec.key} is {expected} in code, "
                f"{registered[spec.key]['panel']!r} in the document"
            )

    def test_the_frontier_anchor_is_not_a_temperature_rejecting_model(self):
        """AUDIT.md 13: `claude-sonnet-5` returns HTTP 400 for `temperature`,
        which §9 registers as frozen at 0.0. A roster edit that reintroduces a
        model from that line would silently break a registered parameter."""
        anchor = {m.key: m for m in config.PANEL}["claude_sonnet"]
        assert anchor.model_id == "claude-sonnet-4-6"
        assert PREREG.read_text(encoding="utf-8").count("Claude Sonnet 5") == 0, (
            "the document still names Claude Sonnet 5, which the panel does not use"
        )


class TestRegisteredCountsAreTrue:
    """The document states counts that carry statistical weight. Each is
    recomputed from the code rather than trusted."""

    def test_primary_panel_is_nine(self):
        assert len(config.primary_panel()) == 9

    def test_exactly_one_secondary_model(self):
        assert len(config.secondary_panel()) == 1

    def test_thirty_six_pairs(self):
        m = len(config.primary_panel())
        assert m * (m - 1) // 2 == 36
        assert "**36 pairs**" in PREREG.read_text(encoding="utf-8")

    def test_three_within_family_pairs(self):
        """H3 and H6 rest entirely on this count, and at one pair the
        permutation test's best achievable p-value is 1/21 = 0.048."""
        fams = {}
        for m in config.primary_panel():
            fams.setdefault(m.family, []).append(m.key)
        within = sum(len(v) * (len(v) - 1) // 2 for v in fams.values())
        assert within == 3, f"within-family pairs: {within}"

    def test_six_families(self):
        assert len({m.family for m in config.primary_panel()}) == 6

    def test_m_equals_nine_wherever_the_document_says_so(self):
        """H4 matches human SPF headroom measured AT M = 9. If the primary panel
        size ever changes, that baseline is silently unmatched."""
        assert len(config.primary_panel()) == 9
        assert "M = 9" in PREREG.read_text(encoding="utf-8")


class TestSecondaryModelIsExcludedFromAnalysis:
    def test_analysis_reads_the_primary_panel_only(self):
        """Collection is deliberately wider than analysis. The exclusion has to
        be structural, not remembered."""
        keys = {m.key for m in config.primary_panel()}
        assert "gpt_frontier" not in keys
        assert "gpt_frontier" in {m.key for m in config.enabled_panel()}

    def test_panel_module_defaults_to_primary(self):
        """`panel.load_panel` must default to the registered nine, so a caller
        who passes nothing cannot accidentally analyse ten."""
        import inspect

        from neff import panel

        src = inspect.getsource(panel)
        assert "primary_panel" in src
        assert "enabled_panel" not in src, (
            "panel.py must not build matrices from the collected roster"
        )


class TestStateVariablesAreSeven:
    """The count is the Benjamini-Hochberg denominator, so it sets H1's
    falsification threshold directly. AUDIT.md finding 12: both documents said
    six while the list held seven."""

    def test_config_holds_seven(self):
        assert len(config.STATE_VARIABLES) == 7

    def test_no_duplicates(self):
        assert len(set(config.STATE_VARIABLES)) == 7

    def test_document_says_seven_not_six(self):
        text = PREREG.read_text(encoding="utf-8")
        assert "seven state variables" in text
        assert "six state variables" not in text
        assert "across the six" not in text

    def test_every_registered_variable_is_named_in_the_document(self):
        text = PREREG.read_text(encoding="utf-8")
        prose = {
            "ladder_distance": "ladder distance",
            "vix_level": "VIX level",
            "realized_vol_20d": "20-day realised volatility",
            "expectation_dispersion": "cross-model forecast dispersion",
            "abs_surprise": "macro surprise",
            "days_out": "days-to-resolution",
            "novelty_score": "novelty score",
        }
        assert set(prose) == set(config.STATE_VARIABLES)
        for var, phrase in prose.items():
            assert phrase in text, f"{var} is registered in code but not named in §4"

    def test_ask_time_subset_is_a_subset(self):
        assert set(config.STATE_COLLECTED_AT_ASK) <= set(config.STATE_VARIABLES)
        assert len(config.STATE_COLLECTED_AT_ASK) == 4

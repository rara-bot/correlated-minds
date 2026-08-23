"""The plan and the code must never disagree again.

PREREGISTRATION.md is frozen and hashed, and after that a correction is a
numbered deviation in section 11 rather than an edit. So every factual claim it
makes about the instrument has to be true of the instrument at the moment of
freezing, and has to STAY true for the 15 weeks that follow.

The audit history is the argument for this file. Finding 17 registered a model
the study does not use. Finding 12 counted six state variables where the code
had seven -- and that count sets the Benjamini-Hochberg denominator, so it moved
H1's falsification threshold. Finding 18 was the same disease in OSF.md. Each
was found by a human reading two files side by side and noticing. That does not
scale and it does not survive a tired evening.

These tests read the document and compare it to `neff.config`, so drift fails
the suite instead of reaching the registry.
"""

import re
from collections import defaultdict
from pathlib import Path

import pytest

from neff import config

PREREG = Path(__file__).resolve().parent.parent / "PREREGISTRATION.md"


@pytest.fixture(scope="module")
def doc():
    return PREREG.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Structure: a dangling cross-reference in a frozen document cannot be fixed.
# --------------------------------------------------------------------------
class TestStructure:
    def test_top_level_sections_are_contiguous(self, doc):
        nums = [int(n) for n in re.findall(r"^## (\d+)\. ", doc, re.M)]
        assert nums == list(range(1, len(nums) + 1)), f"gap in section numbering: {nums}"

    def test_subsections_are_contiguous(self, doc):
        subs = defaultdict(list)
        for parent, child in re.findall(r"^### (\d+)\.(\d+) ", doc, re.M):
            subs[int(parent)].append(int(child))
        for parent, children in subs.items():
            assert children == list(range(1, len(children) + 1)), \
                f"gap in section {parent}.x: {children}"

    def test_every_cross_reference_resolves(self, doc):
        tops = {int(n) for n in re.findall(r"^## (\d+)\. ", doc, re.M)}
        subs = {f"{a}.{b}" for a, b in re.findall(r"^### (\d+)\.(\d+) ", doc, re.M)}
        def missing(ref):
            return ref not in subs if "." in ref else int(ref) not in tops

        dangling = sorted(
            ref for ref in set(re.findall(r"§\s?(\d+(?:\.\d+)?)", doc)) if missing(ref)
        )
        assert not dangling, f"references to sections that do not exist: {sorted(dangling)}"

    def test_every_hypothesis_referenced_is_declared(self, doc):
        declared = set(re.findall(r"^### (H\d)", doc, re.M))
        referenced = set(re.findall(r"\b(H\d)\b", doc))
        assert referenced <= declared, f"undeclared: {sorted(referenced - declared)}"

    def test_deviations_table_is_empty_at_registration(self, doc):
        tail = doc.split("## 11. Deviations from this plan")[-1]
        rows = [r for r in re.findall(r"^\| (.+?) \|", tail, re.M)
                if r not in ("#", "---") and not set(r) <= {"-", "—", " "}]
        assert not rows, f"section 11 must be empty at registration, found: {rows}"


# --------------------------------------------------------------------------
# The roster. Finding 17: the document registered a model the study never ran.
# --------------------------------------------------------------------------
def _roster(doc):
    rows = re.findall(
        r"^\| \d+ \| `(\w+)` \| (\w+) \| `([^`]+)` \| (\w+) \| (\w+) \| \*?\*?(\w+)",
        doc, re.M,
    )
    return {k: dict(provider=p, model_id=m, family=f, tier=t, panel=pan)
            for k, p, m, f, t, pan in rows}


class TestRoster:
    def test_document_and_code_list_the_same_models(self, doc):
        assert set(_roster(doc)) == {m.key for m in config.enabled_panel()}

    def test_every_pinned_id_matches_the_code(self, doc):
        cfg = {m.key: m for m in config.enabled_panel()}
        for key, row in _roster(doc).items():
            assert cfg[key].model_id == row["model_id"], key
            assert cfg[key].provider == row["provider"], key
            assert cfg[key].family == row["family"], key

    def test_primary_panel_membership_matches(self, doc):
        doc_primary = {k for k, r in _roster(doc).items() if r["panel"] == "primary"}
        assert doc_primary == {m.key for m in config.primary_panel()}

    def test_panel_size_is_nine(self):
        """H4 matches SPF RECESS headroom measured at M = 9. A tenth member
        silently unmatches the human comparison."""
        assert len(config.primary_panel()) == 9

    def test_six_families_and_three_within_family_pairs(self):
        """Section 3.1: one within-family pair caps the permutation test at
        p = 1/21. Three drops the floor below 0.001."""
        fams = defaultdict(list)
        for m in config.primary_panel():
            fams[m.family].append(m.key)
        assert len(fams) == 6, dict(fams)
        assert sum(1 for ks in fams.values() if len(ks) >= 2) == 3, dict(fams)

    def test_pair_count_is_stated_correctly(self, doc):
        m = len(config.primary_panel())
        assert f"{m * (m - 1) // 2} pairs" in doc


# --------------------------------------------------------------------------
# H1's state variables AND the direction registered for each.
# --------------------------------------------------------------------------
def _directions(doc):
    return re.findall(r"^  \| `(\w+)` \| .+ \| \*?\*?(negative|positive)", doc, re.M)


class TestStateVariables:
    def test_direction_registered_for_every_state_variable(self, doc):
        assert [n for n, _ in _directions(doc)] == config.STATE_VARIABLES

    def test_the_count_that_sets_the_bh_denominator(self, doc):
        """Finding 12: the document said six, the code had seven, and the count
        is the Benjamini-Hochberg denominator -- so it sets H1's falsification
        threshold."""
        assert len(config.STATE_VARIABLES) == 7
        assert len(_directions(doc)) == 7
        assert "**Seven**" in doc

    def test_inverse_ambiguity_variables_are_registered_negative(self, doc):
        """`ladder_distance` is distance FROM the ladder median, so a higher
        value is a LESS ambiguous question. H1 predicts correlation rises with
        ambiguity, therefore a negative coefficient.

        The clause used to read "no state variable shows a positive,
        BH-surviving coefficient". In a calm 15 weeks -- the scenario 10.5 names
        as the largest risk to H1 -- ladder_distance is the only leg guaranteed
        to vary, so H1 could have been confirmed through it and reported as
        falsified anyway."""
        d = dict(_directions(doc))
        assert d["ladder_distance"] == "negative"
        assert d["expectation_dispersion"] == "negative"

    def test_stress_variables_are_registered_positive(self, doc):
        d = dict(_directions(doc))
        for v in ("vix_level", "realized_vol_20d", "abs_surprise", "novelty_score", "days_out"):
            assert d[v] == "positive", v

    def test_falsification_clause_is_direction_aware(self, doc):
        assert "in the\n  direction registered above" in doc or \
               "in the direction registered above" in doc
        assert "shows a positive, BH-surviving coefficient" not in doc, \
            "the sign-blind falsification clause is back"

    def test_ask_time_variables_are_a_subset_of_the_registered_seven(self):
        assert set(config.STATE_COLLECTED_AT_ASK) <= set(config.STATE_VARIABLES)


# --------------------------------------------------------------------------
# Numbers a reviewer can check with a calculator.
# --------------------------------------------------------------------------
class TestArithmeticAndDates:
    def test_sample_size_multiplies_out(self, doc):
        m = re.search(r"(\d+) task-days × (\d+) models × (\d+) days ≈ ([\d,]+)", doc)
        assert m, "sample-size sentence not found in the expected form"
        tasks, models, days, claimed = (int(m.group(1)), int(m.group(2)),
                                        int(m.group(3)), int(m.group(4).replace(",", "")))
        assert tasks * models * days == claimed
        assert tasks == config.TASKS_PER_DAY
        assert models == len(config.primary_panel())
        assert days == config.collection_days()

    @pytest.mark.parametrize("needle", ["24 Aug 2026", "27 Sep 2026", "6 Dec 2026"])
    def test_key_dates_appear(self, doc, needle):
        assert needle in doc

    def test_dates_match_the_code(self):
        assert config.COLLECTION_START == "2026-08-24"
        assert config.CALIBRATION_END == "2026-09-27"
        assert config.DATA_FREEZE == "2026-12-06"

    def test_registered_constants_match_the_code(self, doc):
        assert f"REPLICATES_PER_DAY = {config.REPLICATES_PER_DAY}" in doc
        assert str(config.REPLICATE_VARIANT) in doc
        assert config.TEMPERATURE == 0.0
        assert "TEMPERATURE = 0.0" in doc

    def test_arm_caps_fit_inside_the_global_budget(self):
        assert sum(config.ARM_CAPS_USD.values()) <= config.BUDGET_USD

    def test_the_projection_leaves_headroom_under_its_cap(self):
        """The cap is a hard stop, not a warning. Finding 22: a projection that
        met its cap would have halted collection in November."""
        assert config.projected_ws1_usd() < config.ARM_CAPS_USD[config.PRIMARY_ARM]


# --------------------------------------------------------------------------
# Retired statistics must not reappear as live commitments.
# --------------------------------------------------------------------------
class TestRetiredStatisticsStayRetired:
    def test_the_residual_metric_is_not_a_registered_outcome(self, doc):
        """Section 2.3: residuals sum to zero by construction, so their pairwise
        correlation is exactly -1/(M-1) whatever the truth is. It carries no
        information and was removed as an outcome."""
        assert "primary outcome is now **excess correlation" not in doc
        assert "-1/(M-1)" in doc or "`-1/(M-1)`" in doc, \
            "the reason it was dropped should stay on the record"

    def test_the_unqualified_power_figure_is_not_claimed(self, doc):
        """7.7 sigma assumed i.i.d. task-days. Questions are re-asked daily, so
        they are not."""
        live = [l for l in doc.splitlines()
                if "7.7 sigma" in l and "earlier draft" not in l]
        assert not live, live

    def test_section_9_freezes_what_section_4_registers(self, doc):
        """A commitment section 9 does not list is one that could be quietly
        dropped later."""
        nine = doc.split("## 9. Researcher degrees of freedom")[-1].split("## 10.")[0]
        assert "direction" in nine, "section 9 must freeze the registered directions"
        assert "event-clustered" in nine, "section 9 must freeze the second interval"


# --------------------------------------------------------------------------
# The daily job must collect under the arm the analysis admits.
# --------------------------------------------------------------------------
class TestTheWorkflowCollectsUnderTheRegisteredArm:
    """`load_panel` is fail-closed on `arm`, which makes this string load-bearing.

    If `.github/workflows/daily.yml` ever passes an `--arm` that is not
    `config.PRIMARY_ARM`, every row the study collects is stamped with the wrong
    label and silently excluded from every primary estimate. Collection would
    look perfectly healthy -- green runs, growing files, spend on the ledger --
    and the panel would be empty. Nothing else in the suite would notice.
    """

    def test_daily_workflow_arm_matches_the_primary_arm(self):
        wf = (Path(__file__).resolve().parent.parent
              / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
        arms = set(re.findall(r"--arm\s+(\S+)", wf))
        assert arms == {config.PRIMARY_ARM}, (
            f"workflow collects under {arms}, analysis admits only "
            f"{config.PRIMARY_ARM!r}"
        )

    def test_the_workflow_runs_the_suite_before_spending(self):
        """Broken statistics must never collect data against themselves."""
        wf = (Path(__file__).resolve().parent.parent
              / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
        assert "pytest" in wf
        assert wf.index("pytest") < wf.index("--arm")

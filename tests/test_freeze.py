"""The freeze stamp must be verifiable by a stranger, or it is worth nothing.

The whole defence of this study is "the plan was fixed before the data existed".
That defence rests on one mechanical claim: the SHA-256 printed at freeze time,
published on OSF, is the hash of the document as it now stands. If a skeptic
runs `--check` and is told the document was tampered with, the registration is
worse than useless -- and because an OSF registration is immutable, there is no
way to correct it afterwards.

Two defects in the original script broke exactly that claim, silently:

  * the hash was computed before the `**Status:**` line was rewritten, so the
    hash stored in the document was never the hash of the document; and
  * `--check` compared a backtick-wrapped recorded hash against a bare digest,
    so it reported a mismatch even when the document was intact.

Both are regression-tested here. These tests exist because the failure is
invisible: freezing "worked", printed a plausible 64-hex string, and exited 0.
"""

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "freeze_prereg.py"
REAL_DOC = ROOT / "PREREGISTRATION.md"

HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


def _load(doc_path):
    """Load the script with DOC pointed at a scratch copy.

    Loaded fresh per test so module state cannot leak between them.
    """
    spec = importlib.util.spec_from_file_location(f"freeze_{doc_path.parent.name}", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.DOC = doc_path
    return mod


@pytest.fixture
def doc(tmp_path):
    """A real, unfrozen copy of the actual pre-registration."""
    p = tmp_path / "PREREGISTRATION.md"
    shutil.copyfile(REAL_DOC, p)
    return p


@pytest.fixture
def frz(doc):
    return _load(doc)


def _freeze(frz):
    return frz._do_freeze(frz.DOC.read_text(encoding="utf-8"))


def _check(frz):
    return frz._do_check(frz.DOC.read_text(encoding="utf-8"))


class TestTheDocumentIsStillFreezable:
    """If the header is reworded, freezing must fail loudly rather than no-op."""

    def test_real_document_carries_every_anchor_exactly_once(self, frz):
        text = REAL_DOC.read_text(encoding="utf-8")
        # Only meaningful while the real document is still unfrozen; once frozen
        # for real, the placeholders are gone by design.
        if "_(to be filled" not in text:
            pytest.skip("the real document is already frozen")
        for anchor in (
            frz.FROZEN_ON_PLACEHOLDER,
            frz.HASH_PLACEHOLDER,
            frz.DRAFT_STATUS,
        ):
            assert text.count(anchor) == 1, f"anchor missing or duplicated: {anchor[:40]!r}"

    def test_missing_anchor_refuses_rather_than_silently_skipping(self, frz, doc):
        """A reworded status line must stop the freeze, not produce a document
        that reads DRAFT while the script reports success."""
        doc.write_text(
            doc.read_text(encoding="utf-8").replace(frz.DRAFT_STATUS, "**Status:** whatever"),
            encoding="utf-8",
        )
        with pytest.raises(SystemExit, match="REFUSING TO FREEZE"):
            _freeze(frz)


class TestFreezeRoundTrip:
    def test_freeze_then_check_is_clean(self, frz):
        assert _freeze(frz) == 0
        assert _check(frz) == 0, "a freshly frozen document must verify as intact"

    def test_recorded_hash_equals_actual_hash(self, frz, doc):
        """The defect that mattered: the stored hash was of a document that had
        already been mutated again before it was written to disk."""
        _freeze(frz)
        text = doc.read_text(encoding="utf-8")
        assert frz.recorded_hash(text) == frz.digest(text)

    def test_printed_hash_equals_recorded_hash(self, frz, doc, capsys):
        """The user pastes the PRINTED hash into an immutable OSF registration.
        If it differs from the stored one, the registration is permanently
        wrong."""
        _freeze(frz)
        printed = HEX64.findall(capsys.readouterr().out)
        assert printed, "freeze must print the hash"
        assert set(printed) == {frz.recorded_hash(doc.read_text(encoding="utf-8"))}

    def test_status_line_flips_to_frozen(self, frz, doc):
        _freeze(frz)
        text = doc.read_text(encoding="utf-8")
        assert "**Status:** FROZEN" in text
        assert "DRAFT" not in text.split("\n## 1.")[0]

    def test_date_stamp_is_utc_and_written(self, frz, doc):
        _freeze(frz)
        assert re.search(
            r"\*\*Frozen on:\*\* \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC",
            doc.read_text(encoding="utf-8"),
        )

    def test_hash_is_stable_across_repeated_checks(self, frz):
        _freeze(frz)
        assert _check(frz) == 0
        assert _check(frz) == 0


class TestTamperDetection:
    def test_edit_after_freeze_is_caught(self, frz, doc):
        _freeze(frz)
        doc.write_text(
            doc.read_text(encoding="utf-8") + "\n\nsneaked in later\n", encoding="utf-8"
        )
        assert _check(frz) == 2, "a post-freeze edit must be detected"

    def test_single_character_edit_is_caught(self, frz, doc):
        """Tamper detection has to be exact, not approximate."""
        _freeze(frz)
        text = doc.read_text(encoding="utf-8")
        assert "Nine models" in text
        doc.write_text(text.replace("Nine models", "Ten models", 1), encoding="utf-8")
        assert _check(frz) == 2

    def test_stamp_lines_are_excluded_from_the_hash(self, frz, doc):
        """Otherwise writing the hash would change the hash, forever."""
        _freeze(frz)
        text = doc.read_text(encoding="utf-8")
        digest_before = frz.digest(text)
        rewrapped = text.replace("**Frozen on:** ", "**Frozen on:**  ")
        assert frz.digest(rewrapped) == digest_before

    def test_frozen_doc_with_no_hash_is_rejected(self, frz, doc):
        _freeze(frz)
        text = doc.read_text(encoding="utf-8")
        text = re.sub(r"\*\*SHA-256 of frozen version:\*\* .*", "**SHA-256 of frozen version:** ", text)
        doc.write_text(text, encoding="utf-8")
        assert _check(frz) == 2


class TestBackticksDoNotBreakComparison:
    """The second defect: the stored hash is wrapped in backticks for markdown,
    and the comparison was against the raw captured string."""

    def test_recorded_hash_strips_markdown_wrapping(self, frz):
        assert (
            frz.recorded_hash("**SHA-256 of frozen version:** `" + "a" * 64 + "`")
            == "a" * 64
        )

    def test_recorded_hash_handles_bare_hex(self, frz):
        assert frz.recorded_hash("**SHA-256 of frozen version:** " + "b" * 64) == "b" * 64

    def test_stored_form_is_still_wrapped_for_rendering(self, frz, doc):
        _freeze(frz)
        assert re.search(
            r"\*\*SHA-256 of frozen version:\*\* `[0-9a-f]{64}`",
            doc.read_text(encoding="utf-8"),
        )


class TestFreezeIsOneShot:
    def test_refuses_to_refreeze(self, frz):
        assert _freeze(frz) == 0
        assert _freeze(frz) == 1, "re-freezing would destroy the guarantee"

    def test_refreeze_attempt_leaves_the_document_untouched(self, frz, doc):
        _freeze(frz)
        before = doc.read_text(encoding="utf-8")
        _freeze(frz)
        assert doc.read_text(encoding="utf-8") == before


class TestUnfrozenDocument:
    def test_check_reports_not_yet_frozen(self, frz, capsys):
        assert _check(frz) == 0
        assert "NOT YET FROZEN" in capsys.readouterr().out

    def test_check_never_mutates_the_document(self, frz, doc):
        before = doc.read_text(encoding="utf-8")
        _check(frz)
        assert doc.read_text(encoding="utf-8") == before

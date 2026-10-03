"""Logging a deviation must not be indistinguishable from tampering.

The frozen plan requires that every post-freeze change is written into section
11 as a dated row. Writing one changes the file, which changes the hash, which
made `--check` report HASH MISMATCH -- permanently, from the first honest
deviation onward. README.md tells a skeptic to run that command and expect
`intact`, so the first time the study did what its own plan requires, the
instruction would have started producing what reads as evidence of tampering.

The fix is a second hash covering the document with section 11's table rows
removed. That is the part which was actually promised not to change, and these
tests exist to hold the line between "a deviation was logged" and "the plan was
edited". If that line blurs, the integrity claim is gone and nothing else in
this file matters.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "freeze_prereg.py"
REAL_DOC = ROOT / "PREREGISTRATION.md"


@pytest.fixture
def frz():
    spec = importlib.util.spec_from_file_location("freeze_dev", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def text():
    return REAL_DOC.read_text(encoding="utf-8")


class TestTheBodyHashIsTheRegisteredOne:
    def test_the_real_document_still_matches_the_recorded_body_hash(self, frz, text):
        """If this fails, either the plan was edited outside section 11 or the
        constant was fitted to a document that had already drifted."""
        assert frz.body_digest(text) == frz.REGISTERED_BODY_SHA

    def test_check_passes_while_deviations_are_logged(self, frz, text, capsys):
        assert frz._do_check(text) == 0
        out = capsys.readouterr().out
        assert "intact outside section 11" in out

    def test_the_registered_hash_is_still_reported(self, frz, text, capsys):
        """The primary claim is the full-document hash on OSF. Softening the
        check must not hide it."""
        frz._do_check(text)
        out = capsys.readouterr().out
        assert "90a7e7de5980a80bef786e87b938495d7a08e10234032a11c5d67e8ce1c70009" in out


class TestOnlySectionElevenRowsAreForgiven:
    def test_another_deviation_row_leaves_the_body_hash_alone(self, frz, text):
        before = frz.body_digest(text)
        grown = text.replace(
            "| 1 | 2026-09-03 |",
            "| 2 | 2026-10-01 | Something else | Because |\n| 1 | 2026-09-03 |",
            1,
        )
        assert frz.body_digest(grown) == before

    def test_prose_appended_after_the_table_is_still_caught(self, frz, text):
        """The tamper test in test_freeze.py appends at the end of the document,
        and section 11 IS the end. Only well-formed rows may pass."""
        assert frz.body_digest(text + "\n\nsneaked in later\n") != frz.REGISTERED_BODY_SHA

    def test_an_edit_elsewhere_is_still_caught(self, frz, text):
        assert "Nine models" in text
        tampered = text.replace("Nine models", "Ten models", 1)
        assert frz.body_digest(tampered) != frz.REGISTERED_BODY_SHA

    def test_prose_inside_section_eleven_is_still_covered(self, frz, text):
        """Only the TABLE is writable, not the section around it."""
        tampered = text.replace(
            "_(Numbered and dated. Empty at registration.)_",
            "_(Numbered and dated. Empty at registration.)_ ...and rewritten.",
            1,
        )
        assert frz.body_digest(tampered) != frz.REGISTERED_BODY_SHA

    def test_a_row_added_to_a_different_table_is_still_caught(self, frz, text):
        """Section 11's exemption must not leak into the other tables."""
        marker = "| Tasks | 16 (10 macro event, 6 filing), 8 asked on each day |"
        assert marker in text
        tampered = text.replace(marker, marker + "\n| Smuggled | row |", 1)
        assert frz.body_digest(tampered) != frz.REGISTERED_BODY_SHA


class TestTheDeviationsThemselvesAreReadable:
    def test_every_logged_deviation_is_numbered_and_dated(self, frz, text):
        """Asserted as a shape, not a count -- this list is expected to grow, and
        a test that pins its length just breaks on the next honest deviation."""
        import re

        rows = frz.logged_deviations(text)
        assert rows, "section 11 parsed as empty"
        for cells in rows:
            assert re.fullmatch(r"\d+", cells[0]), f"unnumbered deviation: {cells}"
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[1]), \
                f"undated deviation: {cells}"
            assert len(cells) >= 4 and cells[3].strip(), \
                f"deviation with no reason given: {cells}"

    def test_they_are_numbered_from_one_without_gaps(self, frz, text):
        numbers = sorted(int(c[0]) for c in frz.logged_deviations(text))
        assert numbers == list(range(1, len(numbers) + 1)), (
            f"deviation numbering is not contiguous: {numbers} -- a missing "
            f"number reads as a deviation that was logged and then removed"
        )

    def test_the_header_and_separator_are_not_counted_as_deviations(self, frz, text):
        for cells in frz.logged_deviations(text):
            assert cells[0] not in ("#", "—", "---")

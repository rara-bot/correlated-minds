#!/usr/bin/env python3
"""Freeze the pre-registration: stamp it with a date and a SHA-256 hash.

The hash is the point. Once PREREGISTRATION.md is hashed, committed, and the
hash is published on OSF, any later edit changes the hash and is detectable by
anyone. That converts "we planned this in advance" from a claim into something a
skeptic can verify themselves.

    python scripts/freeze_prereg.py --check    # show the current hash
    python scripts/freeze_prereg.py --freeze   # stamp it (do this ONCE)

WHY THIS FILE IS PARANOID
-------------------------
An earlier version of this script had two defects that between them destroyed
the guarantee above, and neither raised an error:

1. It computed the hash BEFORE rewriting the `**Status:**` line from DRAFT to
   FROZEN. The hash written into the document was therefore the hash of a
   document that no longer existed. `--freeze` printed one hash and stored a
   different one, and the user would paste the printed hash into an IMMUTABLE
   OSF registration.
2. `--check` compared a backtick-wrapped recorded hash (`` `abc123…` ``) against
   a bare hex digest, so the strings could never be equal. Every check reported
   HASH MISMATCH -- including on an untampered document.

Together: the first honest skeptic to run `--check` would have been told the
registered plan had been tampered with, and there would have been no way to
correct the OSF record. So this script now VERIFIES ITS OWN OUTPUT before it
writes, and again after, and restores the original file if anything disagrees.

That is the lesson from AUDIT.md finding 15, applied to ourselves: where a
registered commitment is involved, confirm the change took EFFECT -- do not
settle for "the call returned without error".
"""
import argparse
import hashlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "PREREGISTRATION.md"

# Lines excluded from the hash. They carry the stamp itself, so including them
# would be circular: writing the hash would change the hash.
STAMP_PREFIXES = ("**Frozen on:**", "**SHA-256 of frozen version:**")

# Exact anchors in the document. If any of these stops matching -- because the
# header was reworded or rewrapped -- freezing must FAIL rather than silently
# skip the substitution and leave a document that says DRAFT while this script
# announces it is frozen.
FROZEN_ON_PLACEHOLDER = "**Frozen on:** _(to be filled at registration)_"
HASH_PLACEHOLDER = "**SHA-256 of frozen version:** _(to be filled at registration)_"
DRAFT_STATUS = (
    "**Status:** DRAFT — to be frozen, hashed, and registered on OSF before the first\n"
    "observation is collected."
)
FROZEN_STATUS = (
    "**Status:** FROZEN. No edits permitted; changes go in section 11 as dated deviations."
)

_HEX64 = re.compile(r"[0-9a-f]{64}")


def body_without_stamps(text: str) -> str:
    """Hash the content, not the stamp lines -- otherwise the hash changes when
    we write the hash into the file, which is circular."""
    return "\n".join(
        line for line in text.splitlines() if not line.startswith(STAMP_PREFIXES)
    )


def digest(text: str) -> str:
    return hashlib.sha256(body_without_stamps(text).encode("utf-8")).hexdigest()


def recorded_hash(text: str) -> str:
    """The hash stored in the document, normalised.

    The stored form is wrapped in backticks for markdown rendering. Comparing
    the raw captured string against a bare digest is what made every `--check`
    report a mismatch, so extraction is by hex pattern rather than by strip().
    """
    m = re.search(r"\*\*SHA-256 of frozen version:\*\* (.+)", text)
    if not m:
        return ""
    found = _HEX64.search(m.group(1))
    return found.group(0) if found else ""


def frozen_on(text: str) -> str:
    m = re.search(r"\*\*Frozen on:\*\* (.+)", text)
    if not m or "_(to be filled" in m.group(1):
        return ""
    return m.group(1).strip()


def _replace_once(text: str, old: str, new: str, what: str) -> str:
    """Substitute, and fail loudly if the anchor is not there exactly once.

    `str.replace` on a missing anchor returns the string unchanged and reports
    nothing. For a one-shot, irreversible operation that publishes a scientific
    commitment, a silent no-op is the worst possible failure mode.
    """
    n = text.count(old)
    if n != 1:
        raise SystemExit(
            f"REFUSING TO FREEZE: expected exactly one {what} anchor in "
            f"{DOC.name}, found {n}.\n"
            f"The document header was edited and no longer matches this script.\n"
            f"Fix the anchor or this script BEFORE freezing -- do not work around it."
        )
    return text.replace(old, new)


def _do_check(text: str) -> int:
    h = digest(text)
    print(f"file      : {DOC.name}")
    print(f"sha256    : {h}")

    stamped_on = frozen_on(text)
    if not stamped_on:
        print("status    : NOT YET FROZEN")
        return 0

    print(f"frozen on : {stamped_on}")
    recorded = recorded_hash(text)
    if not recorded:
        print("\n!! NO HASH RECORDED -- the document says it is frozen but carries")
        print("   no SHA-256. Do not register it in this state.")
        return 2
    if recorded != h:
        print("\n!! HASH MISMATCH -- the document changed after freezing.")
        print(f"   recorded: {recorded}")
        print(f"   actual  : {h}")
        print("   Record this in section 11 as a dated deviation.")
        return 2

    print("status    : intact, matches recorded hash")
    print(f"\nPaste this into the OSF registration's 'Other / Notes' field:\n")
    print(f"    SHA-256 of the frozen plan document (PREREGISTRATION.md):")
    print(f"    {h}")
    return 0


def _do_freeze(text: str) -> int:
    if "_(to be filled" not in text:
        print("Already frozen. Refusing to re-freeze -- that is the whole point.")
        print("A genuine change goes in section 11 as a dated deviation.")
        return 1

    original = text
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Every mutation to the hashed body happens BEFORE the digest is taken.
    # The status line is part of the body; hashing before rewriting it is the
    # defect described in this module's docstring.
    text = _replace_once(
        text, FROZEN_ON_PLACEHOLDER, f"**Frozen on:** {stamp}", "'Frozen on'"
    )
    text = _replace_once(text, DRAFT_STATUS, FROZEN_STATUS, "'Status: DRAFT'")

    h = digest(text)

    # Writing the hash cannot change the hash: its line is excluded from the body.
    text = _replace_once(
        text, HASH_PLACEHOLDER, f"**SHA-256 of frozen version:** `{h}`", "'SHA-256'"
    )

    # Verify in memory before touching the file on disk.
    if digest(text) != h or recorded_hash(text) != h:
        raise SystemExit(
            "REFUSING TO FREEZE: internal inconsistency between the computed and "
            "recorded hash. The file has NOT been modified."
        )

    DOC.write_text(text, encoding="utf-8")

    # Verify again from disk. If the round trip disagrees for any reason
    # (encoding, line endings, a concurrent edit), put the original back rather
    # than leave a document whose stamp cannot be trusted.
    after = DOC.read_text(encoding="utf-8")
    if digest(after) != h or recorded_hash(after) != h:
        DOC.write_text(original, encoding="utf-8")
        raise SystemExit(
            "REFUSING TO FREEZE: the file on disk does not match what was written.\n"
            "The original document has been restored. DO NOT register anything."
        )

    print(f"FROZEN {stamp}")
    print(f"sha256: {h}\n")
    print("This hash is recorded in the document and verified against it.")
    print("Confirm any time with: scripts/freeze_prereg.py --check\n")
    print("Next: commit this, then paste the hash into your OSF registration.")
    try:
        subprocess.run(["git", "add", str(DOC)], check=False)
    except Exception:
        pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if not DOC.exists():
        print(f"missing {DOC}")
        return 1
    text = DOC.read_text(encoding="utf-8")

    if args.freeze and not args.check:
        return _do_freeze(text)
    return _do_check(text)


if __name__ == "__main__":
    sys.exit(main())

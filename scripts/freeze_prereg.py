#!/usr/bin/env python3
"""Freeze the pre-registration: stamp it with a date and a SHA-256 hash.

The hash is the point. Once PREREGISTRATION.md is hashed, committed, and the
hash is published on OSF, any later edit changes the hash and is detectable by
anyone. That converts "we planned this in advance" from a claim into something a
skeptic can verify themselves.

    python scripts/freeze_prereg.py --check    # show the current hash
    python scripts/freeze_prereg.py --freeze   # stamp it (do this ONCE)
"""
import argparse, hashlib, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "PREREGISTRATION.md"


def body_without_stamps(text: str) -> str:
    """Hash the content, not the stamp lines -- otherwise the hash changes when
    we write the hash into the file, which is circular."""
    out = []
    for line in text.splitlines():
        if line.startswith("**Frozen on:**") or line.startswith("**SHA-256"):
            continue
        out.append(line)
    return "\n".join(out)


def digest(text: str) -> str:
    return hashlib.sha256(body_without_stamps(text).encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if not DOC.exists():
        print(f"missing {DOC}"); return 1
    text = DOC.read_text(encoding="utf-8")
    h = digest(text)

    if args.check or not args.freeze:
        print(f"file      : {DOC.name}")
        print(f"sha256    : {h}")
        frozen = re.search(r"\*\*Frozen on:\*\* (.+)", text)
        stamped = re.search(r"\*\*SHA-256 of frozen version:\*\* (.+)", text)
        if frozen and "_(to be filled" not in frozen.group(1):
            print(f"frozen on : {frozen.group(1).strip()}")
            recorded = stamped.group(1).strip() if stamped else ""
            if recorded and recorded != h:
                print("\n!! HASH MISMATCH -- the document changed after freezing.")
                print(f"   recorded: {recorded}")
                print(f"   actual  : {h}")
                print("   Record this in section 11 as a dated deviation.")
                return 2
            print("status    : intact, matches recorded hash")
        else:
            print("status    : NOT YET FROZEN")
        return 0

    if "_(to be filled" not in text:
        print("Already frozen. Refusing to re-freeze -- that is the whole point.")
        print("A genuine change goes in section 11 as a dated deviation.")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = text.replace("**Frozen on:** _(to be filled at registration)_",
                        f"**Frozen on:** {stamp}")
    text = text.replace("**SHA-256 of frozen version:** _(to be filled at registration)_",
                        f"**SHA-256 of frozen version:** `{digest(text)}`")
    text = text.replace("**Status:** DRAFT — to be frozen, hashed, and registered on OSF before the first\nobservation is collected.",
                        "**Status:** FROZEN. No edits permitted; changes go in section 11 as dated deviations.")
    DOC.write_text(text, encoding="utf-8")

    final = digest(DOC.read_text(encoding="utf-8"))
    print(f"FROZEN {stamp}\nsha256: {final}\n")
    print("Next: commit this, then paste the hash into your OSF registration.")
    try:
        subprocess.run(["git", "add", str(DOC)], check=False)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

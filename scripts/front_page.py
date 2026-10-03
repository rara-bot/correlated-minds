#!/usr/bin/env python3
"""Keep the repository's front page showing the record.

The study's record is the `main` branch: every forecast committed, in order, before
its outcome existed. The commit ids the registration, the addenda and the Week-5
prediction cite are all on `main`, and nothing here ever writes to it.

GitHub shows a repository's default branch on its front page and builds the page's
contributor list from that branch's history. The default branch is `front`, whose
only commits are copies of `main`'s files, one each time `main` changes. So the
front page shows exactly what `main` holds -- the same files, the same README, the
same workflows -- while the full history stays where it always was, on `main`.

GitHub starts scheduled workflows from the default branch, so `.github/workflows/
daily.yml` runs from `front`; it checks out `main` and commits the day to `main`
whichever branch it started from (RECORD_BRANCH in daily.yml), then runs this.

    python scripts/front_page.py           # copy main onto front if they differ
    python scripts/front_page.py --check   # does front show main? changes nothing
    python scripts/front_page.py --init    # create front, once, as a copy of main

Run from the repository's root, by the daily job after it commits the day and by
hand after a push to `main` that should reach the front page before the next run.
It writes only to `front`. A failure here never costs a day: the day is already on
`main`, and a front page that lags a day behind is still the record, a day late.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

RECORD = "main"
FRONT = "front"
REMOTE = "origin"
# Paths whose difference between the two branches changes what GitHub RUNS, not
# just what the page shows: the schedule is read from `front`'s copy.
WORKFLOWS = ".github/workflows"


@dataclass
class State:
    """What `front` shows, read from the remote. Changes nothing."""
    front_exists: bool
    record_head: str = ""
    front_head: str = ""
    shows_record: bool = False
    differs_in: List[str] = field(default_factory=list)
    workflows_differ: bool = False
    co_author_lines: int = 0       # lines naming a co-author anywhere in front's history
    record_commits_in_front: int = 0   # commits of `main` reachable from `front` (must be 0)


def _git(*args: str, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run git in `cwd`, or in the current directory: the repository being kept."""
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def _out(*args: str, cwd: Optional[Path] = None) -> str:
    return _git(*args, cwd=cwd).stdout.strip()


def _remote_has(branch: str, remote: str, cwd: Optional[Path]) -> bool:
    found = _git("ls-remote", "--heads", remote, f"refs/heads/{branch}", cwd=cwd, check=False)
    if found.returncode != 0:
        raise RuntimeError(f"cannot reach {remote}: {found.stderr.strip()}")
    return bool(found.stdout.strip())


def _fetch(branch: str, remote: str, cwd: Optional[Path]) -> str:
    """Fetch one branch into its remote-tracking ref and return the ref's name."""
    ref = f"refs/remotes/{remote}/{branch}"
    _git("fetch", "--quiet", "--no-tags", remote, f"+refs/heads/{branch}:{ref}", cwd=cwd)
    return ref


def state(record: str = RECORD, front: str = FRONT, remote: str = REMOTE,
          cwd: Optional[Path] = None) -> State:
    record_ref = _fetch(record, remote, cwd)
    record_head = _out("rev-parse", record_ref, cwd=cwd)
    if not _remote_has(front, remote, cwd):
        return State(front_exists=False, record_head=record_head)
    front_ref = _fetch(front, remote, cwd)
    front_head = _out("rev-parse", front_ref, cwd=cwd)
    differs = [p for p in _out("diff", "--name-only", front_ref, record_ref, cwd=cwd).splitlines() if p]
    messages = _out("log", "--format=%B", front_ref, cwd=cwd)
    # `front` must never carry `main`'s commits: if the two share any history, every
    # commit up to their merge base is a `main` commit reachable from the front page.
    merge_base = _git("merge-base", front_ref, record_ref, cwd=cwd, check=False).stdout.strip()
    record_in_front = int(_out("rev-list", "--count", merge_base, cwd=cwd)) if merge_base else 0
    return State(
        front_exists=True,
        record_head=record_head,
        front_head=front_head,
        shows_record=not differs,
        differs_in=differs,
        workflows_differ=any(p.startswith(WORKFLOWS + "/") for p in differs),
        co_author_lines=sum(1 for line in messages.splitlines()
                            if line.strip().lower().startswith("co-authored-by:")),
        record_commits_in_front=record_in_front,
    )


def _message(record: str, record_head: str) -> str:
    return f"Show {record} at {record_head[:7]}"


def show(record: str = RECORD, front: str = FRONT, remote: str = REMOTE, cwd: Optional[Path] = None,
         attempts: int = 3, wait: float = 5.0) -> Tuple[str, str]:
    """Copy `record`'s files onto `front` as one new commit. Returns (status, text).

    status: "absent" (no front branch; nothing to do), "current" (front already
    shows record), "updated", or "failed". Only `front` is ever pushed, and only
    as a fast-forward of itself: its history is copies, never `record`'s commits.
    """
    for attempt in range(1, attempts + 1):
        st = state(record, front, remote, cwd)
        if not st.front_exists:
            return "absent", f"there is no {front} branch on {remote}; nothing to show"
        if st.shows_record:
            return "current", f"{front} already shows {record} at {st.record_head[:7]}"
        tree = _out("rev-parse", f"{st.record_head}^{{tree}}", cwd=cwd)
        commit = _out("commit-tree", tree, "-p", st.front_head, "-m", _message(record, st.record_head), cwd=cwd)
        pushed = _git("push", "--quiet", remote, f"{commit}:refs/heads/{front}", cwd=cwd, check=False)
        if pushed.returncode == 0:
            return "updated", f"{front} now shows {record} at {st.record_head[:7]}"
        if attempt < attempts:
            time.sleep(wait * attempt)
    return "failed", (f"could not update {front} after {attempts} attempts; "
                      f"the record on {record} is unaffected")


def init(record: str = RECORD, front: str = FRONT, remote: str = REMOTE,
         cwd: Optional[Path] = None) -> Tuple[str, str]:
    """Create `front` once, as a single commit holding `record`'s files and no history."""
    st = state(record, front, remote, cwd)
    if st.front_exists:
        return "exists", f"{front} already exists on {remote}; nothing created"
    tree = _out("rev-parse", f"{st.record_head}^{{tree}}", cwd=cwd)
    commit = _out("commit-tree", tree, "-m", _message(record, st.record_head), cwd=cwd)
    _git("push", "--quiet", remote, f"{commit}:refs/heads/{front}", cwd=cwd)
    return "created", f"{front} created, showing {record} at {st.record_head[:7]}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report whether front shows main; change nothing")
    mode.add_argument("--init", action="store_true", help="create front as a copy of main (once)")
    parser.add_argument("--json", action="store_true", help="with --check: print the state as JSON")
    args = parser.parse_args(argv)
    try:
        if args.check:
            st = state()
            if args.json:
                print(json.dumps(asdict(st), indent=2))
            elif not st.front_exists:
                print(f"no {FRONT} branch yet")
            elif st.shows_record:
                print(f"{FRONT} shows {RECORD} at {st.record_head[:7]}")
            else:
                print(f"{FRONT} differs from {RECORD} in {len(st.differs_in)} file(s)"
                      + (" including the workflows GitHub runs" if st.workflows_differ else ""))
            return 0
        status, text = init() if args.init else show()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        print(f"::warning::front page not updated: {detail.strip()}")
        return 1
    print(text if status != "failed" else f"::warning::{text}")
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())

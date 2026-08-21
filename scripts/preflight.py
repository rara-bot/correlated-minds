#!/usr/bin/env python3
"""One command that says exactly what is done and what is not.

Written because a mock run on 17 Aug looked identical to a successful real one
-- it printed "140 observations" and a dollar figure, none of it real -- and that
was mistaken for a completed setup. Guessing at readiness is how a study starts
on synthetic data. Run this instead:

    ./.venv/bin/python scripts/preflight.py
"""

import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neff.config import COLLECTION_START, DATA_FREEZE, enabled_panel  # noqa: E402
from neff.verify import verified_models  # noqa: E402

GREEN, RED, YELLOW, DIM, BOLD, END = (
    "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[1m", "\033[0m"
)


def _tick(ok):
    return f"{GREEN}[done]{END}" if ok else f"{RED}[TODO]{END}"


def _git(*args, timeout=20):
    """Run git, returning (ok, stdout). Never raises -- a readiness check that
    crashes tells you less than one that reports what it could not determine."""
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip()
    except Exception:
        return False, ""


def _is_committed(relpath) -> bool:
    ok, out = _git("ls-files", "--error-unmatch", str(relpath))
    return ok and bool(out)


def _push_state():
    """(pushed, human detail, remedy).

    The claim this check underwrites is "every forecast was committed publicly
    before its outcome existed". That claim needs commits ON THE REMOTE, so the
    remote is what gets asked -- not the local config.
    """
    ok, remote = _git("remote", "-v")
    if not ok or not remote:
        return (False, "no git remote configured",
                "create a public repo and: git remote add origin <url> "
                "&& git push -u origin main")

    url = remote.splitlines()[0].split()[1] if remote.splitlines() else "?"

    ok, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    branch = branch or "main"

    ok, heads = _git("ls-remote", "--heads", "origin", branch, timeout=30)
    if not ok:
        return (False, f"could not reach {url} (network, or the repo does not exist)",
                f"check the remote is reachable, then: git push -u origin {branch}")
    if not heads:
        # This is the real state the old check reported as [done]: the GitHub
        # repo exists and is browsable, but holds no branches at all.
        return (False, f"{url} exists but has no '{branch}' branch — nothing has been pushed",
                f"git push -u origin {branch}")

    remote_sha = heads.split()[0]
    _, local_sha = _git("rev-parse", "HEAD")
    if remote_sha == local_sha:
        return (True, f"{url} — up to date at {local_sha[:8]}", "")

    ok, ahead = _git("rev-list", "--count", f"{remote_sha}..HEAD")
    n = ahead if ok and ahead else "some"
    return (False, f"{url} — {n} local commit(s) not pushed",
            f"git push origin {branch}")


def _read_jsonl(path):
    if not path.exists() or path.stat().st_size == 0:
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def main() -> int:
    print(f"\n{BOLD}PRE-FLIGHT — Correlated Minds{END}")
    today = datetime.now(timezone.utc).date()
    start = date.fromisoformat(COLLECTION_START)
    print(f"{DIM}today {today} | collection starts {start} "
          f"({(start - today).days} days) | freeze {DATA_FREEZE}{END}\n")

    blocking = []

    # 1 -- keys
    env = ROOT / ".env"
    needed = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"]
    present = {}
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                present[k.strip()] = v.strip()
    have = [k for k in needed if len(present.get(k, "")) > 10]
    print(f"{_tick(len(have) == len(needed))} 1. API keys in .env — {len(have)}/4")
    for k in needed:
        state = f"{GREEN}set{END}" if k in have else f"{RED}missing{END}"
        print(f"        {k:22} {state}")
    if len(have) < len(needed):
        blocking.append("put the four API keys in .env  (cp .env.example .env)")

    # 2 -- model ids verified
    #
    # Read from the verification receipts, not from observations.jsonl. `neff.verify`
    # makes one live call per model but writes no observations, so checking the
    # observation log here meant this step could never pass -- and its own
    # remediation line told the operator to run the command they had just run.
    panel = enabled_panel()
    verified = verified_models()
    ok_verify = all(m.key in verified for m in panel)
    print(f"\n{_tick(ok_verify)} 2. Model IDs verified against live APIs — "
          f"{len(verified)}/{len(panel)} models have answered for real")
    if not ok_verify:
        missing = [m.key for m in panel if m.key not in verified]
        print(f"        never answered: {', '.join(missing)}")
        blocking.append("run: ./.venv/bin/python -m neff.verify")
    else:
        drifted = [k for k, r in verified.items() if r.get("drift")]
        when = sorted({r.get("checked_at", "")[:10] for r in verified.values()})
        print(f"        {DIM}last verified {when[-1] if when else '?'}; "
              f"receipts in data/verification.jsonl{END}")
        if drifted:
            print(f"        {YELLOW}served id differs from pinned id: "
                  f"{', '.join(drifted)}{END}")

    # 3 -- real pilot
    #
    # This step DOES belong to observations.jsonl: it asks whether a full day has
    # been exercised end to end, which a per-model probe does not establish.
    obs = _read_jsonl(ROOT / "data" / "observations.jsonl")
    real = [o for o in obs
            if str(o.get("provider", "")).lower() != "mock"
            and not str(o.get("model_id_returned", "")).endswith("-mock")]
    mock = [o for o in obs if o not in real]
    print(f"\n{_tick(bool(real))} 3. Real pilot collected — "
          f"{len(real)} real observations, {len(mock)} mock")
    if mock:
        print(f"        {YELLOW}mock rows are excluded from analysis by default{END}")
    if not real:
        blocking.append("run a real pilot: ./.venv/bin/python -m neff.collect --tasks 8 --arm pilot")

    # 4 -- spend
    ledger = _read_jsonl(ROOT / "data" / "ledger.jsonl")
    spent = sum(float(r.get("usd", 0) or 0) for r in ledger)
    print(f"\n{DIM}    4. Recorded spend: ${spent:.4f}{END}")

    # 5 -- freeze
    text = (ROOT / "PREREGISTRATION.md").read_text()
    frozen = "DRAFT" not in text.split("\n## 1.")[0]
    print(f"\n{_tick(frozen)} 5. Pre-registration frozen + hashed")
    if not frozen:
        blocking.append("freeze it: ./.venv/bin/python scripts/freeze_prereg.py --freeze")

    # 6 -- github
    #
    # A configured remote is NOT a push. The previous version of this check
    # printed [done] as soon as `git remote -v` returned anything, so an empty
    # GitHub repo with nothing in it reported as a public, timestamped history --
    # which is precisely the evidence the study rests on. Ask the remote.
    pushed, detail, remedy = _push_state()
    print(f"\n{_tick(pushed)} 6. Pushed to a public GitHub repo")
    print(f"        {DIM if pushed else YELLOW}{detail}{END}")
    if not pushed:
        blocking.append(remedy)

    # 7 -- osf (cannot be checked from disk)
    marker = ROOT / ".osf_url"
    osf = marker.read_text().strip() if marker.exists() else ""
    valid = osf.startswith(("http://", "https://"))
    print(f"\n{_tick(valid)} 7. OSF registration public"
          f"{' — ' + osf if osf else ''}")
    if not valid:
        if osf:
            print(f"        {RED}{osf!r} is not a URL — the collection gate will "
                  f"refuse this{END}")
        print(f"        {DIM}cannot be checked from disk; save the URL to .osf_url when done{END}")
        blocking.append("register on OSF (see OSF.md), then: echo '<url>' > .osf_url")
    elif not _is_committed(".osf_url"):
        # The scheduled job runs from a fresh checkout. A URL that exists only
        # here fails every automated collection day on a registration that is,
        # locally, plainly present.
        print(f"        {RED}.osf_url is NOT COMMITTED — CI cannot see it and "
              f"every daily run will fail{END}")
        blocking.append(
            "commit the registration URL: git add .osf_url && "
            "git commit -m 'Record OSF registration' && git push"
        )

    print(f"\n{BOLD}{'—' * 62}{END}")
    if blocking:
        print(f"{BOLD}Next, in this order:{END}")
        for i, item in enumerate(blocking, 1):
            print(f"  {i}. {item}")
        print(f"\n{YELLOW}Real study collection must not begin until steps 5-7 are done.{END}")
        print(f"{DIM}Keys, verify and the pilot are safe to do first — the pilot is a{END}")
        print(f"{DIM}separate registered arm, excluded from the primary analysis.{END}")
    else:
        print(f"{GREEN}{BOLD}Ready. Collection can start.{END}")
    print()
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())

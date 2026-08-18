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

GREEN, RED, YELLOW, DIM, BOLD, END = (
    "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[1m", "\033[0m"
)


def _tick(ok):
    return f"{GREEN}[done]{END}" if ok else f"{RED}[TODO]{END}"


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
    panel = enabled_panel()
    obs = _read_jsonl(ROOT / "data" / "observations.jsonl")
    real = [o for o in obs
            if str(o.get("provider", "")).lower() != "mock"
            and not str(o.get("model_id_returned", "")).endswith("-mock")]
    verified = {o.get("model_key") for o in real if o.get("model_id_returned")}
    ok_verify = len(verified) >= len(panel)
    print(f"\n{_tick(ok_verify)} 2. Model IDs verified against live APIs — "
          f"{len(verified)}/{len(panel)} models have answered for real")
    if not ok_verify:
        missing = [m.key for m in panel if m.key not in verified]
        print(f"        never answered: {', '.join(missing)}")
        blocking.append("run: ./.venv/bin/python -m neff.verify")

    # 3 -- real pilot
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
    try:
        remote = subprocess.run(["git", "remote", "-v"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip()
    except Exception:
        remote = ""
    print(f"\n{_tick(bool(remote))} 6. Pushed to a public GitHub repo")
    if not remote:
        blocking.append("create a public repo and: git remote add origin <url> && git push -u origin main")

    # 7 -- osf (cannot be checked from disk)
    marker = ROOT / ".osf_url"
    osf = marker.read_text().strip() if marker.exists() else ""
    print(f"\n{_tick(bool(osf))} 7. OSF registration public"
          f"{' — ' + osf if osf else ''}")
    if not osf:
        print(f"        {DIM}cannot be checked from disk; save the URL to .osf_url when done{END}")
        blocking.append("register on OSF (see OSF.md), then: echo '<url>' > .osf_url")

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

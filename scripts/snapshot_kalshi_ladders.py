#!/usr/bin/env python
"""Record the strike structure of every Kalshi market the panel was asked about
before the task record carried it.

WHY THIS EXISTS

`ladder_distance` is H1's experimentally varied state variable. As registered in
code it has two properties the plan never states (PREREGISTRATION.md 11,
deviations 15 and 17): the curated path pools every open expiry of a series into
one ladder, and an event with no numeric ladder records 0.0 -- the same value a
real ladder's median strike records. Fed and central-bank decisions are the live
case: their tickers (`C26`, `H0`) parse as numbers and are categories.

From 2026-09-14 each task records `strike_type`, `custom_strike`, its Kalshi
event and that event's numeric ladder. Rows before then do not, and the stored
value cannot tell a median strike from no ladder. Kalshi keeps settled events
and their markets, so the STRUCTURE of each ladder -- which markets exist, and
their strike fields -- can still be read. This script reads it once and writes it
down, so that the analysis runs offline and a reader can check exactly what it
used.

WHAT IT RECORDS, AND WHAT IT NEVER RECORDS

One row per market ticker: its event, strike type and strike fields, the event's
sorted numeric rungs, and whether the market is a rung of a ladder of at least
three. It never writes a result, a settlement, a price or a volume. The
structure of a ladder says nothing about how any question resolved, so reading
it cannot unblind anything.

Structure is read as it stands when this runs, not as it stood on the ask date.
Kalshi occasionally adds strikes to an open event, so a reconstructed rung count
can exceed the one the panel faced. Every row says it was reconstructed, and the
analysis labels anything built from it.

Append-only and idempotent: a ticker already in the file is skipped.

    ./.venv/bin/python scripts/snapshot_kalshi_ladders.py            # write
    ./.venv/bin/python scripts/snapshot_kalshi_ladders.py --dry-run  # print only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neff.sources import kalshi  # noqa: E402
from neff.sources.http import FetchError, get_json  # noqa: E402
from neff.store import JsonlStore  # noqa: E402

TASKS = ROOT / "data" / "tasks.jsonl"
OUT = ROOT / "data" / "kalshi_ladders.jsonl"
PRIMARY_ARM = "ws1_prospective"

# The last ask date whose rows carry no ladder fields. From 2026-09-14 the task
# record itself holds them (deviation 15), so nothing later needs reconstructing.
LAST_UNRECORDED_DAY = "2026-09-13"

STRUCTURE_FIELDS = ("strike_type", "floor_strike", "cap_strike", "custom_strike")


def _structure(market: dict) -> dict:
    """The strike fields of a market, and nothing that depends on its outcome."""
    row = {"ticker": str(market.get("ticker") or "")}
    row.update({field: market.get(field) for field in STRUCTURE_FIELDS})
    row["strike"] = kalshi._strike_of(market)
    return row


def _tickers_to_reconstruct(tasks: list) -> list:
    return sorted({
        str(t["source_ref"]) for t in tasks
        if t.get("arm") == PRIMARY_ARM and t.get("kind") == "event"
        and (t.get("state") or {}).get("asked_on", "") <= LAST_UNRECORDED_DAY
        and t.get("source_ref")
    })


def reconstruct(ticker: str, events_cache: dict) -> dict:
    market = (get_json(f"{kalshi.BASE}/markets/{ticker}").get("market") or {})
    event = str(market.get("event_ticker") or "")
    if event not in events_cache:
        payload = get_json(f"{kalshi.BASE}/events/{event}",
                           params={"with_nested_markets": "true"})
        nested = (payload.get("event") or {}).get("markets") or payload.get("markets") or []
        events_cache[event] = [_structure(m) for m in nested]
    siblings = events_cache[event]
    this = _structure(market)
    rungs = sorted(m["strike"] for m in siblings if kalshi._is_numeric_rung(m))
    is_rung = kalshi._is_numeric_rung(this)
    return {
        **this,
        "kalshi_event": event,
        "event_markets": len(siblings),
        "event_numeric_rungs": rungs,
        "is_numeric_rung": is_rung,
        "ladder_defined": bool(is_rung and len(rungs) >= 3 and rungs[-1] > rungs[0]),
        "reconstructed": True,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Kalshi public API: /markets/{ticker} and /events/{event}",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    tasks = JsonlStore(TASKS).read_all()
    wanted = _tickers_to_reconstruct(tasks)
    store = JsonlStore(OUT)
    have = store.existing_ids("ticker")
    todo = [t for t in wanted if t not in have]
    print(f"{len(wanted)} market(s) asked on or before {LAST_UNRECORDED_DAY}; "
          f"{len(have & set(wanted))} already recorded; {len(todo)} to read")

    events: dict = {}
    written, failed = 0, []
    for ticker in todo:
        try:
            row = reconstruct(ticker, events)
        except FetchError as exc:
            failed.append(ticker)
            print(f"  !! {ticker}: {exc}")
            continue
        flag = "ladder" if row["ladder_defined"] else "NO LADDER"
        print(f"  {ticker:40s} {row['kalshi_event']:28s} "
              f"rungs={len(row['event_numeric_rungs']):3d} {flag}")
        if not args.dry_run:
            store.append(row)
            written += 1
        time.sleep(0.2)          # polite to a free public API

    print(f"wrote {written} row(s) to {OUT.relative_to(ROOT)}"
          + (f"; {len(failed)} failed and can be retried" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

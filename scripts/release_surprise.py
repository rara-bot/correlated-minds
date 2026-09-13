#!/usr/bin/env python
"""Compute the market surprise of listed macro releases (PREREGISTRATION.md 11, deviation 18).

Writes data/release_surprise.jsonl, one row per Kalshi event, append-only: an
event already recorded is never recomputed or rewritten.

  --reference  every listed release that closed in the twelve months before the
               first study observation (`surprise.REFERENCE_WINDOW`). Its 80th
               percentile is the threshold the Week-5 prediction names. Market
               data only, and no event in it overlaps the panel's.
  --study      each listed release a primary task resolves against, once settled.
  --p80        print the reference 80th percentile and the events behind it.

Neither computing mode reads a model's forecast, so running either cannot
unblind the panel.

    ./.venv/bin/python scripts/release_surprise.py --reference
    ./.venv/bin/python scripts/release_surprise.py --study
    ./.venv/bin/python scripts/release_surprise.py --p80
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neff import surprise  # noqa: E402
from neff.analysis import resolution_event  # noqa: E402
from neff.sources.http import FetchError  # noqa: E402
from neff.store import JsonlStore  # noqa: E402

OUT = ROOT / "data" / "release_surprise.jsonl"
TASKS = ROOT / "data" / "tasks.jsonl"
PRIMARY_ARM = "ws1_prospective"


def _write(store: JsonlStore, record: dict, role: str) -> None:
    record["role"] = role
    store.append(record)
    value = record.get("surprise")
    shown = f"{value:.4f}" if isinstance(value, float) else f"undefined ({record.get('why_not')})"
    print(f"  {record['kalshi_event']:30s} closes {str(record.get('close_time'))[:16]}  "
          f"rungs {record.get('rungs', 0):3d}  informative {record.get('informative', 0):3d}  "
          f"surprise {shown}")


def reference(store: JsonlStore, have: set) -> int:
    lo, hi = (datetime.fromisoformat(x) for x in surprise.REFERENCE_WINDOW)
    failures = 0
    for series in surprise.RELEASE_SERIES:
        try:
            events = surprise.settled_release_events(series)
        except FetchError as exc:
            print(f"!! {series}: {exc}")
            failures += 1
            continue
        candidates = [e for e in events
                      if surprise.series_of(e) == series
                      and (surprise.ticker_year(e) or 0) in (lo.year, hi.year)
                      and e not in have]
        print(f"{series}: {len(events)} settled event(s), {len(candidates)} to check against the window")
        for event in candidates:
            try:
                fetched = surprise.fetch_event_markets(event)
                close = surprise.event_close(fetched[0])
                if close is None or not (lo <= close < hi):
                    continue
                _write(store, surprise.event_surprise(event, fetched=fetched), "reference")
            except FetchError as exc:
                print(f"  !! {event}: {exc}")
                failures += 1
    return failures


def study(store: JsonlStore, have: set) -> int:
    lo = datetime.fromisoformat(surprise.REFERENCE_WINDOW[1])
    events = sorted({
        resolution_event(str(t.get("source_ref")))
        for t in JsonlStore(TASKS).read()
        if t.get("arm") == PRIMARY_ARM and t.get("kind") == "event"
    })
    failures = 0
    for event in events:
        if event in have or not surprise.is_release_event(event):
            continue
        try:
            fetched = surprise.fetch_event_markets(event)
        except FetchError as exc:
            print(f"  !! {event}: {exc}")
            failures += 1
            continue
        markets = fetched[0]
        close = surprise.event_close(markets)
        # Only once EVERY market in the release has settled. The first row per
        # event is the one the analysis keeps, so a surprise computed while some
        # rungs were still open would be frozen incomplete.
        finished = bool(markets) and all(
            str(m.get("status") or "").lower() in ("finalized", "settled") for m in markets)
        if not finished or close is None or close < lo:
            continue                                   # not fully settled yet: next run
        _write(store, surprise.event_surprise(event, fetched=fetched), "study")
    return failures


def show_p80(store: JsonlStore) -> int:
    rows = [r for r in store.read() if r.get("role") == "reference"]
    defined = [r for r in rows if isinstance(r.get("surprise"), float)]
    p80 = surprise.percentile_80(r["surprise"] for r in defined)
    print(f"reference events: {len(rows)} recorded, {len(defined)} with a defined surprise")
    print(f"80th percentile : {p80}")
    return 0 if p80 is not None else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--reference", action="store_true")
    mode.add_argument("--study", action="store_true")
    mode.add_argument("--p80", action="store_true")
    args = parser.parse_args(argv)

    store = JsonlStore(OUT)
    have = store.existing_ids("kalshi_event")
    if args.p80:
        return show_p80(store)
    failures = reference(store, have) if args.reference else study(store, have)
    if failures:
        print(f"{failures} failure(s); rerun to retry -- recorded events are skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

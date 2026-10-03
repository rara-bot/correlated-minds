#!/usr/bin/env python
"""Pin each Kalshi series' base rate for H2 (PREREGISTRATION.md 11, deviation 20).

    ./.venv/bin/python scripts/category_base_rates.py          # every series asked, once each
    ./.venv/bin/python scripts/category_base_rates.py --show

Writes data/category_base_rates.jsonl, one row per Kalshi series, append-only: a
series already recorded is never recomputed or rewritten. Its base rate is the
share of its markets that settled YES, over its events closing in deviation 18's
reference window, the twelve months before the first study observation. It reads
market settlements from before any question in this study was asked, never a
forecast and never a study outcome, so running it cannot unblind anything.

A series the study first asks about later is added the next time this runs; the
daily workflow runs it in a step that cannot fail the run. A series whose events
cannot be read is left unrecorded and retried next time, never recorded as empty.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from neff import h2, surprise  # noqa: E402
from neff.config import PRIMARY_ARM, TASKS_PATH  # noqa: E402
from neff.sources.http import FetchError  # noqa: E402
from neff.store import JsonlStore  # noqa: E402


def series_asked(tasks_path: Path = TASKS_PATH) -> list:
    """Every Kalshi series a primary task has been asked about."""
    return sorted({h2.category_of(str(t.get("source_ref")))
                   for t in JsonlStore(tasks_path).read()
                   if t.get("arm") == PRIMARY_ARM and t.get("source") == "kalshi"
                   and t.get("source_ref")})


def record_for(series: str) -> dict:
    """The reference-window base rate of one series, with the events behind it."""
    lo, hi = (datetime.fromisoformat(x) for x in surprise.REFERENCE_WINDOW)
    results = {}
    for event in surprise.settled_release_events(series):
        if surprise.series_of(event) != series:
            continue
        year = surprise.ticker_year(event)
        if year is not None and year not in (lo.year, hi.year):
            continue
        markets, _ = surprise.fetch_event_markets(event)
        close = surprise.event_close(markets)
        if close is not None and lo <= close < hi:
            results[event] = [m.get("result") for m in markets]
    return {
        "series": series,
        "window": list(surprise.REFERENCE_WINDOW),
        **h2.reference_base_rate(results),
        "event_tickers": sorted(results),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "definition": "PREREGISTRATION.md 11, deviation 20 (neff/h2.py)",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args(argv)

    store = JsonlStore(h2.BASE_RATES_PATH)
    if args.show:
        for row in store.read():
            print(f"  {row.get('series', ''):24s} events {row.get('events', 0):4d}  "
                  f"markets {row.get('markets', 0):5d}  base rate {row.get('base_rate')}")
        return 0
    have = store.existing_ids("series")
    failures = 0
    for series in series_asked():
        if series in have:
            continue
        try:
            record = record_for(series)
        except FetchError as exc:
            print(f"!! {series}: {exc}")
            failures += 1
            continue
        store.append(record)
        print(f"  {series:24s} events {record['events']:4d}  markets {record['markets']:5d}  "
              f"base rate {record['base_rate']}")
    if failures:
        print(f"{failures} series could not be read; rerun to retry -- recorded series are skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

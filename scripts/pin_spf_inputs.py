#!/usr/bin/env python
"""Pin the inputs of the human benchmark (PREREGISTRATION.md 11, deviation 19).

WHY THIS EXISTS

H4's human benchmark is registered as numbers -- SPF RECESS headroom at M = 9,
PREREGISTRATION.md 2.3 -- and the plan recomputes it: at the surviving panel size
if 5.6 removes a model (deviation 17), and on the squared-error scale and at the
matched accuracy that 5.5 and H4 name. Its inputs are two public files that change
underneath it. The Philadelphia Fed replaces SPFmicrodata.xlsx with each quarterly
survey, and FRED serves only the latest vintage of a series, which BEA's annual
update revises. Recomputed in December from fresh downloads, the benchmark would
rest on different data from the registered numbers, and choosing a vintage then
would be a choice made with the AI results in view.

WHAT IT WRITES, INTO data/spf/

  <SHEET>.csv        RECESS, UNEMP, CPI, EMP and RGDP from the workbook: rows from
                     2000, and only the columns spf.py reads
  fred_<SERIES>.csv  FRED's CSV for CPIAUCSL, GDPC1, PAYEMS and UNRATE, as served
  PROVENANCE.json    where each file came from, when, and its SHA-256

Human forecasts and official statistics only. Nothing here reads a model's
forecast or a question's outcome, so it cannot unblind anything.

It refuses to run when a pin exists: changing the registered benchmark's inputs
is a deviation, not a rerun.

    ./.venv/bin/python scripts/pin_spf_inputs.py [--workbook PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import pandas as pd  # noqa: E402

from neff.config import USER_AGENT  # noqa: E402
from neff.sources import fred, spf  # noqa: E402
from neff.sources.http import get_text  # noqa: E402


def _utc(timestamp: Optional[float] = None) -> str:
    moment = (datetime.fromtimestamp(timestamp, timezone.utc) if timestamp is not None
              else datetime.now(timezone.utc))
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def served_bytes() -> Optional[int]:
    """Length of the workbook the Philadelphia Fed serves now, to set beside the pinned copy."""
    try:
        response = httpx.head(spf.MICRODATA_URL, params={"sc_lang": "en"},
                              headers={"User-Agent": USER_AGENT}, timeout=60.0,
                              follow_redirects=True)
        return int(response.headers["content-length"]) if response.status_code == 200 else None
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pin the human benchmark's inputs (deviation 19).")
    parser.add_argument("--workbook", type=Path, default=spf.CACHE_PATH)
    args = parser.parse_args(argv)

    if spf.PROVENANCE_PATH.exists():
        print(f"REFUSING: {spf.PROVENANCE_PATH.relative_to(ROOT)} exists. Changing the "
              "benchmark's inputs is a deviation (PREREGISTRATION.md 11), not a rerun.")
        return 1
    workbook = args.workbook.read_bytes()
    if workbook[:2] != b"PK":
        print(f"REFUSING: {args.workbook} is not an xlsx workbook.")
        return 1

    spf.PINNED_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "registered_in": "PREREGISTRATION.md 11, deviation 19",
        "read_by": "neff/sources/spf.py",
        "spf_workbook": {
            "url": spf.MICRODATA_URL,
            "file_modified": _utc(args.workbook.stat().st_mtime),
            "bytes": len(workbook),
            "sha256": hashlib.sha256(workbook).hexdigest(),
            "bytes_served_when_pinned": served_bytes(),
        },
        "spf_sheets": {},
        "fred_series": {},
    }

    for sheet, columns in spf.PINNED_SHEETS.items():
        frame = pd.read_excel(args.workbook, sheet_name=sheet)
        frame.columns = [str(c).strip().upper() for c in frame.columns]
        kept = frame[frame["YEAR"] >= spf.PINNED_MIN_YEAR][["YEAR", "QUARTER", "ID"] + columns]
        path = spf.PINNED_DIR / f"{sheet}.csv"
        kept.to_csv(path, index=False)
        record["spf_sheets"][sheet] = {"file": path.name, "rows": int(len(kept)),
                                       "sha256": spf._sha256(path)}
        print(f"  {path.name}: {len(kept)} rows")

    for series_id in spf.PINNED_SERIES:
        fetched_at = _utc()
        text = get_text(fred.CSV_URL, params={"id": series_id})
        observations = fred.parse_series_csv(text, series_id)  # refuses HTML and empty bodies
        path = spf.PINNED_DIR / f"fred_{series_id}.csv"
        path.write_text(text, encoding="utf-8")
        record["fred_series"][series_id] = {
            "file": path.name,
            "url": f"{fred.CSV_URL}?id={series_id}",
            "fetched_at": fetched_at,
            "rows": len(observations),
            "last_observation": observations[-1][0].isoformat(),
            "sha256": spf._sha256(path),
        }
        print(f"  {path.name}: {len(observations)} rows through {observations[-1][0]}")

    spf.PROVENANCE_PATH.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    problems = spf.pinned_problems()
    print("pinned" if not problems else f"!! {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

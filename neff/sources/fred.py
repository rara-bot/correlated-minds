"""FRED macro series -- realized outcomes and market-state variables.

VERIFIED 17 Aug 2026: the CSV graph endpoint

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES

serves clean CSV with **no API key**. The documented REST API at
api.stlouisfed.org returns HTTP 400 without a key, so we use the CSV endpoint
and avoid the key dependency entirely. One less secret to manage in CI, and one
less thing that can expire mid-panel.

Two jobs:

1. GROUND TRUTH. Realized values for the macro questions the panel forecasts,
   which is what turns a forecast into an error.

2. MARKET STATE. VIX and realized volatility are the conditioning variables for
   H1 -- the hypothesis that error correlation rises with stress. Without these
   there is no conditional test, only an average.
"""

import csv
import io
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from .http import FetchError, get_text

CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# Series we depend on, with the role each one plays.
SERIES = {
    "UNRATE": "Unemployment rate (U-3), monthly, percent",
    "CPIAUCSL": "CPI-U all items, monthly index (SA)",
    "PAYEMS": "Total nonfarm payrolls, monthly, thousands",
    "GDPC1": "Real GDP, quarterly, billions chained",
    "VIXCLS": "CBOE VIX close, daily -- primary stress state variable",
    "DGS10": "10-year Treasury constant maturity, daily",
    "DFF": "Effective federal funds rate, daily",
    "T10Y2Y": "10Y-2Y Treasury spread, daily",
}


def fetch_series(series_id: str) -> List[Tuple[date, Optional[float]]]:
    """Full history of a FRED series as (date, value) pairs.

    FRED writes '.' for missing observations (holidays in daily series, etc.);
    those become None rather than being silently dropped, so a caller asking for
    "the value on date d" gets an explicit gap instead of the previous value.
    """
    text = get_text(CSV_URL, params={"id": series_id})

    # Guard against the 200-with-HTML failure mode that both Stooq and the
    # Philadelphia Fed asset paths exhibit.
    stripped = text.lstrip()
    if stripped.startswith("<"):
        raise FetchError(f"FRED {series_id}: expected CSV, got HTML")

    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or len(header) < 2:
        raise FetchError(f"FRED {series_id}: unexpected CSV header {header!r}")

    out: List[Tuple[date, Optional[float]]] = []
    for row in reader:
        if len(row) < 2:
            continue
        try:
            observed = datetime.strptime(row[0].strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        raw = row[1].strip()
        value: Optional[float]
        if raw in ("", "."):
            value = None
        else:
            try:
                value = float(raw)
            except ValueError:
                value = None
        out.append((observed, value))

    if not out:
        raise FetchError(f"FRED {series_id}: no observations parsed")
    return out


def latest_value(series_id: str) -> Tuple[Optional[date], Optional[float]]:
    """Most recent non-missing observation."""
    for observed, value in reversed(fetch_series(series_id)):
        if value is not None:
            return observed, value
    return None, None


def value_on_or_before(
    series_id: str, target: date, series: Optional[List[Tuple[date, Optional[float]]]] = None
) -> Optional[float]:
    """Most recent non-missing value at or before `target`.

    This is the point-in-time accessor. Using it rather than a plain lookup is
    what keeps state variables free of lookahead: when we tag a task asked on
    day d with a VIX level, it must be the VIX that was actually published by
    day d, never a later revision.
    """
    data = series if series is not None else fetch_series(series_id)
    best: Optional[float] = None
    for observed, value in data:
        if observed > target:
            break
        if value is not None:
            best = value
    return best


def quarterly_average(
    series_id: str, year: int, quarter: int, series: Optional[List] = None
) -> Optional[float]:
    """Average of a monthly series over a calendar quarter.

    The SPF forecasts quarterly averages of monthly series (unemployment, for
    example), so comparing an SPF forecast to a single month's print would
    manufacture error that the forecaster never made.
    """
    data = series if series is not None else fetch_series(series_id)
    start_month = 3 * (quarter - 1) + 1
    months = {start_month, start_month + 1, start_month + 2}

    values = [
        value
        for observed, value in data
        if observed.year == year and observed.month in months and value is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def state_snapshot(as_of: Optional[date] = None) -> Dict[str, Optional[float]]:
    """Point-in-time market-state variables for conditioning the H1 test.

    Only variables observable on `as_of` are included. Anything unavailable is
    reported as None rather than back-filled, because a quietly forward-filled
    stress measure would corrupt exactly the conditional analysis it feeds.
    """
    target = as_of or date.today()
    snapshot: Dict[str, Optional[float]] = {}

    for series_id, key in (
        ("VIXCLS", "vix_level"),
        ("DGS10", "treasury_10y"),
        ("T10Y2Y", "yield_curve_10y2y"),
        ("DFF", "fed_funds"),
    ):
        try:
            snapshot[key] = value_on_or_before(series_id, target)
        except FetchError:
            snapshot[key] = None

    # 20-day realized volatility of the VIX level itself: a second, independent
    # stress measure so H1 does not rest on a single indicator.
    try:
        vix = [(d, v) for d, v in fetch_series("VIXCLS") if v is not None and d <= target]
        window = [v for _, v in vix[-21:]]
        if len(window) >= 10:
            rets = [
                (window[i] - window[i - 1]) / window[i - 1]
                for i in range(1, len(window))
                if window[i - 1]
            ]
            if rets:
                mean = sum(rets) / len(rets)
                var = sum((r - mean) ** 2 for r in rets) / len(rets)
                snapshot["realized_vol_20d"] = var ** 0.5
    except FetchError:
        snapshot["realized_vol_20d"] = None

    return snapshot

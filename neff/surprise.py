"""How much a macro release surprised the market.

PREREGISTRATION.md 4 registers `abs_surprise`, "the release surprised consensus by
more", and §5.3 builds the out-of-sample prediction on "the next macro release
with |surprise| above the 80th percentile". Deviation 8 defined it as
|realized - consensus| scaled by the historical spread of that difference, and
named no working consensus source; the variable has been NaN on every row.

The consensus this study can actually observe is the market's. Kalshi quotes a
ladder of strikes on every scheduled release, and the quote a day before the
print is the crowd's probability for each strike. So the surprise is how wrong
that crowd turned out to be, measured with the same proper scoring rule the
study applies to the models (PREREGISTRATION.md 11, deviation 18):

    surprise(E) = mean over informative rungs m of E of (y_m - q_m) ** 2

  q_m  the midpoint of rung m's yes bid and ask in the last hourly candle ending
       at or before SNAPSHOT_HOURS_BEFORE_CLOSE before the event closes, used
       only if both sides are quoted and the spread is at most MAX_SPREAD
  y_m  1 if rung m settled yes, 0 if no
  informative  INFORMATIVE[0] <= q_m <= INFORMATIVE[1]: a rung the market was
       genuinely unsure about. A far strike priced at 0.99 that settles yes
       carries no surprise, and averaging it in would make a long ladder look
       calm simply for being long.

Undefined -- None, never 0 -- with fewer than MIN_INFORMATIVE_RUNGS informative
rungs. It needs no historical scale, because a probability error is already on
one scale for every series.

It reads market settlements and market prices. It never reads a model's
forecast, so it cannot unblind the panel.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .sources import kalshi
from .sources.http import FetchError, get_json

# Series whose settlement is a scheduled US official statistic (BLS, BEA,
# Census). Fixed on 2026-09-13 in deviation 18; a release series that enters the
# battery later is not a "macro release" for this study unless listed here.
RELEASE_SERIES = (
    "KXCPIYOY",               # CPI, year over year (BLS)
    "KXECONSTATCORECPIYOY",   # core CPI, year over year (BLS)
    "KXUSPPI",                # PPI, month over month (BLS)
    "KXUSPPIYOY",             # PPI, year over year (BLS)
    "KXU3",                   # unemployment rate (BLS)
    "KXECONSTATU3",           # unemployment rate, exact-value buckets (BLS)
    "KXPAYROLLS",             # nonfarm payrolls (BLS)
    "KXGDP",                  # real GDP, advance estimate (BEA)
    "KXHOUSINGSTART",         # housing starts (Census)
)

SNAPSHOT_HOURS_BEFORE_CLOSE = 24
MAX_SPREAD = 0.20
INFORMATIVE = (0.05, 0.95)
MIN_INFORMATIVE_RUNGS = 2
CANDLE_LOOKBACK_DAYS = 7

# The reference distribution for the 80th percentile: every listed release that
# closed in the twelve months before the first study observation (2026-09-01).
# Market data only, and no event in it overlaps the panel's.
REFERENCE_WINDOW = ("2025-09-01T00:00:00+00:00", "2026-09-01T00:00:00+00:00")


def series_of(event_ticker: str) -> str:
    return str(event_ticker or "").split("-", 1)[0]


def is_release_event(event_ticker: str) -> bool:
    return series_of(event_ticker) in RELEASE_SERIES


def _close_price(side: Optional[Dict[str, Any]]) -> Optional[float]:
    """Candle close for one side. Live candles say `close_dollars`, historical `close`."""
    if not side:
        return None
    return kalshi._number(side.get("close_dollars", side.get("close")))


def snapshot_quote(candles: Iterable[Dict[str, Any]], snapshot_ts: int) -> Optional[float]:
    """The market's probability at the snapshot, or None.

    The last candle ending at or before the snapshot that quotes both sides. If
    that quote is wider than MAX_SPREAD the market had no usable consensus at
    the snapshot, and an older, narrower quote is not substituted for it.
    """
    usable = sorted(
        (c for c in candles if int(c.get("end_period_ts") or 0) <= snapshot_ts),
        key=lambda c: int(c["end_period_ts"]),
        reverse=True,
    )
    for candle in usable:
        bid, ask = _close_price(candle.get("yes_bid")), _close_price(candle.get("yes_ask"))
        if bid is None or ask is None:
            continue
        if not (0.0 <= bid <= ask <= 1.0) or ask - bid > MAX_SPREAD:
            return None
        return (bid + ask) / 2.0
    return None


def brier_surprise(rungs: Sequence[Tuple[float, Optional[float]]]) -> Tuple[Optional[float], int]:
    """(surprise, informative rung count) from (settled 0/1, snapshot quote) pairs."""
    lo, hi = INFORMATIVE
    informative = [(y, q) for y, q in rungs if q is not None and lo <= q <= hi]
    if len(informative) < MIN_INFORMATIVE_RUNGS:
        return None, len(informative)
    return float(np.mean([(y - q) ** 2 for y, q in informative])), len(informative)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    return kalshi._parse_ts(value)


def _paged(url: str, params: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    cursor = None
    for _ in range(50):
        query = dict(params, **({"cursor": cursor} if cursor else {}))
        payload = get_json(url, params=query)
        out.extend(payload.get(key) or [])
        cursor = payload.get("cursor")
        if not cursor or not payload.get(key):
            break
    return out


def fetch_event_markets(event_ticker: str) -> Tuple[List[Dict[str, Any]], str]:
    """Every market of an event, from the live namespace or else the historical one.

    Kalshi moves older markets out of `/markets` into `/historical/markets`, and
    the boundary is not clean -- some 2026 events answer partly from each -- so
    the namespace that returns more markets is the one used.
    """
    live = _paged(f"{kalshi.BASE}/markets", {"event_ticker": event_ticker, "limit": 200}, "markets")
    try:
        old = _paged(f"{kalshi.BASE}/historical/markets",
                     {"event_ticker": event_ticker, "limit": 200}, "markets")
    except FetchError:
        old = []
    return (live, "live") if len(live) >= len(old) else (old, "historical")


def fetch_candles(ticker: str, namespace: str, start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
    params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": 60}
    if namespace == "historical":
        url = f"{kalshi.BASE}/historical/markets/{ticker}/candlesticks"
    else:
        url = f"{kalshi.BASE}/series/{series_of(ticker)}/markets/{ticker}/candlesticks"
    return get_json(url, params=params).get("candlesticks") or []


def event_surprise(event_ticker: str, pause_s: float = 0.1,
                   fetched: Optional[Tuple[List[Dict[str, Any]], str]] = None) -> Dict[str, Any]:
    """The registered surprise of one settled release event, with its working.

    `fetched` passes in (markets, namespace) already read, so a caller that had to
    read them to decide whether the event is in scope does not read them twice.
    """
    markets, namespace = fetched if fetched is not None else fetch_event_markets(event_ticker)
    record: Dict[str, Any] = {
        "kalshi_event": event_ticker,
        "series": series_of(event_ticker),
        "namespace": namespace,
        "markets": len(markets),
        "surprise": None,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "definition": "PREREGISTRATION.md 11, deviation 18 (neff/surprise.py)",
    }
    closes = [t for t in (_parse_ts(m.get("close_time")) for m in markets) if t]
    if not closes:
        record["why_not"] = "no market with a close time"
        return record
    close = min(closes)
    snapshot = close - timedelta(hours=SNAPSHOT_HOURS_BEFORE_CLOSE)
    record.update(close_time=close.isoformat(), snapshot=snapshot.isoformat())

    rungs: List[Tuple[float, Optional[float]]] = []
    settled = 0
    for market in markets:
        result = str(market.get("result") or "").lower()
        if result not in ("yes", "no"):
            continue
        settled += 1
        rung = dict(market, strike=kalshi._strike_of(market))
        if not kalshi._is_numeric_rung(rung):
            continue
        candles = fetch_candles(
            str(market.get("ticker")), namespace,
            int((snapshot - timedelta(days=CANDLE_LOOKBACK_DAYS)).timestamp()),
            int(snapshot.timestamp()),
        )
        rungs.append((1.0 if result == "yes" else 0.0,
                      snapshot_quote(candles, int(snapshot.timestamp()))))
        time.sleep(pause_s)
    surprise, informative = brier_surprise(rungs)
    record.update(settled=settled, rungs=len(rungs),
                  quoted=sum(1 for _, q in rungs if q is not None),
                  informative=informative, surprise=surprise)
    if surprise is None:
        record["why_not"] = f"{informative} informative rung(s)"
    return record


def event_close(markets: Iterable[Dict[str, Any]]) -> Optional[datetime]:
    closes = [t for t in (_parse_ts(m.get("close_time")) for m in markets) if t]
    return min(closes) if closes else None


def ticker_year(event_ticker: str) -> Optional[int]:
    """Two-digit year from `KXCPIYOY-25DEC` / `KXGDP-26OCT30`, or None."""
    parts = str(event_ticker or "").split("-")
    if len(parts) < 2 or not parts[1][:2].isdigit():
        return None
    return 2000 + int(parts[1][:2])


def settled_release_events(series: str) -> List[str]:
    events = _paged(f"{kalshi.BASE}/events",
                    {"series_ticker": series, "status": "settled", "limit": 200}, "events")
    return [str(e.get("event_ticker")) for e in events if e.get("event_ticker")]


def percentile_80(values: Iterable[Optional[float]]) -> Optional[float]:
    finite = [float(v) for v in values if v is not None and np.isfinite(v)]
    return float(np.percentile(finite, 80)) if finite else None

"""Kalshi event contracts -- the primary task source and ground truth.

Kalshi is a CFTC-regulated exchange for event contracts. Public market data needs
no authentication.

VERIFIED 17 Aug 2026, and one finding shaped this module:

  - Series browsing, market listing, and SETTLEMENT are all public.
    A settled market reports result='yes'/'no' with status='finalized', which is
    unambiguous ground truth requiring no judgement call from us.

  - QUOTES ARE NOT PUBLIC. yes_bid / yes_ask / last_price / volume come back null
    on every economics series, including on individual market fetch. So Kalshi
    cannot supply the market-implied human benchmark; Polymarket does that job
    instead (see polymarket.py), and the Philadelphia Fed SPF is the primary
    human baseline regardless.

Because we cannot see prices, we cannot filter out near-certain contracts by
their implied probability. Instead we exploit Kalshi's strike-ladder structure:
a series like KXCPIYOY lists many thresholds for the same event, and the MIDDLE
strikes are the genuinely uncertain ones while the extremes are near-foregone.
Selecting median strikes per event gives informative questions without needing
quotes -- see select_tasks().

Every task we register is drawn from OPEN markets only, so no outcome exists at
the moment we ask.
"""

import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .http import FetchError, get_json

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Kalshi's own taxonomy. Far more reliable than guessing ticker prefixes --
# an earlier prefix-based filter matched 0 of 600 markets.
FINANCIAL_CATEGORIES = ("Economics", "Financials", "Companies")

# Series that map to scheduled macro releases with hard resolution dates. These
# are the highest-value tasks: unambiguous, frequently recurring, and directly
# comparable to the Survey of Professional Forecasters human baseline.
PRIORITY_SERIES = (
    "KXCPIYOY",        # CPI inflation year-over-year
    "KXU3",            # unemployment rate
    "KXPAYROLLS",      # nonfarm payrolls
    "KXGDP",           # real GDP growth
    "KXFEDDECISION",   # FOMC rate decision
    "KXRECSSNBER",     # NBER recession call
    "KXMORTGAGERATE",  # 30-year mortgage rate
)


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_series(category: str) -> List[Dict[str, Any]]:
    """All series in a Kalshi category."""
    payload = get_json(f"{BASE}/series", params={"category": category})
    return payload.get("series") or []


def fetch_series_tickers(categories: tuple = FINANCIAL_CATEGORIES) -> List[str]:
    tickers: List[str] = []
    for category in categories:
        for series in fetch_series(category):
            ticker = series.get("ticker")
            if ticker:
                tickers.append(str(ticker))
    return tickers


def fetch_open_markets_for_series(series_ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Open markets for one series. Returns [] if the series has none."""
    try:
        payload = get_json(
            f"{BASE}/markets",
            params={"series_ticker": series_ticker, "status": "open", "limit": limit},
        )
    except FetchError:
        return []
    return payload.get("markets") or []


def _strike_of(market: Dict[str, Any]) -> Optional[float]:
    """Numeric strike, read from explicit fields or parsed from the ticker suffix.

    Kalshi tickers look like KXCPIYOY-26AUG-T2.9, where 2.9 is the threshold.
    """
    for key in ("cap_strike", "floor_strike", "strike_value"):
        value = market.get(key)
        if isinstance(value, (int, float)):
            return float(value)

    ticker = str(market.get("ticker", ""))
    tail = ticker.rsplit("-", 1)[-1]
    if tail[:1].upper() in ("T", "B", "C") and len(tail) > 1:
        tail = tail[1:]
    try:
        return float(tail)
    except ValueError:
        return None


def assign_ladder_distance(markets: List[Dict[str, Any]]) -> bool:
    """Populate `ladder_distance` for every market in ONE event's strike ladder.

    LADDER POSITION IS DELIBERATELY VARIED, NOT HELD CONSTANT.

    An earlier version took only the strikes nearest the ladder median. That
    maximises average uncertainty -- but H1, the PRIMARY hypothesis, predicts
    that correlation RISES WITH AMBIGUITY, and a sample with no ambiguity
    variation cannot test it. Holding ambiguity constant suppresses exactly the
    variance the primary test consumes.

    We instead sample graded positions across the ladder's INTERIOR, so ambiguity
    varies by construction rather than waiting on the market to supply a stress
    event. Extremes are still avoided: the registered [0.05, 0.95] first-day
    median rule (PREREGISTRATION.md §3.3) excludes anything effectively settled,
    so this widens the ambiguity range without admitting foregone conclusions.

    `ladder_distance` -- normalised |strike - median| / span, in [0, 1] -- is
    recorded per task and is a registered H1 state variable (§4). Unlike VIX it
    is available every single day regardless of market calm, which is what §10.5
    relies on when it claims H1 survives a calm 15 weeks.

    THIS IS A SHARED HELPER ON PURPOSE. It used to be inline in the curated-series
    branch only, so markets picked up by the broaden-if-short path -- which the
    comment there says fires "on many days" -- reached `tasks.py` with no
    `ladder_distance` at all and were persisted as None. Measured on a live
    25-task day: 5 of 15 event tasks, a third of the sample, carrying nothing for
    the primary hypothesis's experimental leg. It cannot be backfilled, because it
    needs the live strike ladder as it stood on the ask date and closed Kalshi
    ladders are not reliably re-queryable. Every path that produces a market must
    go through here.

    Returns True if the event had a usable ladder (>= 3 strikes), so the caller
    can decide whether to grade its selection across the interior.
    """
    strikes = [m for m in markets if m.get("strike") is not None]
    if len(strikes) >= 3:
        values = sorted(m["strike"] for m in strikes)
        median_strike = statistics.median(values)
        span = values[-1] - values[0]
        for market in markets:
            if market.get("strike") is None:
                market["ladder_distance"] = 0.0
            else:
                market["ladder_distance"] = (
                    abs(market["strike"] - median_strike) / span if span > 0 else 0.0
                )
        return True

    # No usable ladder: the registered convention is 0.0 rather than missing.
    for market in markets:
        market.setdefault("ladder_distance", 0.0)
    return False


def select_tasks(
    max_tasks: int = 15,
    min_days_out: float = 1.0,
    max_days_out: float = 60.0,
    series_tickers: Optional[List[str]] = None,
    strikes_per_event: int = 2,
    broaden_if_short: bool = False,
) -> List[Dict[str, Any]]:
    """Choose informative, resolvable forecasting questions.

    Selection logic and the reason for each rule:

    - PRIORITY_SERIES first: scheduled macro releases are directly comparable to
      the SPF human baseline, which is the study's headline comparison.

    - resolves in [min_days_out, max_days_out]: a contract settling after the
      11 Dec data freeze never gets scored and is wasted spend. One settling in
      hours carries almost no information.

    - median strikes only: without quotes we cannot see implied probability, so
      we use ladder position as a proxy for uncertainty. Extreme strikes on a
      CPI ladder are near-foregone conclusions and would compress error variance
      toward zero, biasing rho_bar upward for a trivial reason rather than a
      scientific one.
    """
    now = datetime.now(timezone.utc)
    tickers = list(series_tickers) if series_tickers else list(PRIORITY_SERIES)

    # Group candidate markets by event so we can pick median strikes per event.
    by_event: Dict[str, List[Dict[str, Any]]] = {}

    for series_ticker in tickers:
        for market in fetch_open_markets_for_series(series_ticker):
            if market.get("status") not in ("open", "active"):
                continue
            close = _parse_ts(market.get("close_time"))
            if close is None:
                continue
            days_out = (close - now).total_seconds() / 86400.0
            if not (min_days_out <= days_out <= max_days_out):
                continue

            event_ticker = str(market.get("event_ticker") or market.get("ticker", "")).rsplit("-", 1)[0]
            record = {
                "ticker": str(market.get("ticker", "")),
                "event_ticker": event_ticker,
                "series_ticker": series_ticker,
                "title": str(market.get("title") or market.get("subtitle") or ""),
                "rules": str(market.get("rules_primary") or "")[:1200],
                "close_time": market.get("close_time"),
                "days_out": round(days_out, 2),
                "strike": _strike_of(market),
                "market_implied": None,   # not public on Kalshi; see module docstring
            }
            if record["ticker"] and record["title"]:
                by_event.setdefault(event_ticker, []).append(record)

    selected: List[Dict[str, Any]] = []
    for event_ticker, markets in sorted(by_event.items()):
        if assign_ladder_distance(markets):
            ordered = sorted(
                (m for m in markets if m["strike"] is not None),
                key=lambda m: m["ladder_distance"],
            )
            interior = ordered[: max(strikes_per_event, len(ordered) - 1)]
            if len(interior) <= strikes_per_event:
                selected.extend(interior)
            else:
                # even spread across the interior: nearest the median, furthest
                # still-included, and graded steps between.
                step = (len(interior) - 1) / max(1, strikes_per_event - 1)
                picks = {int(round(k * step)) for k in range(strikes_per_event)}
                selected.extend(interior[i] for i in sorted(picks))
        else:
            selected.extend(markets[:strikes_per_event])

    # Prefer questions that resolve sooner: they get scored inside the window,
    # which is what makes the panel usable rather than merely collected.
    selected.sort(key=lambda m: m["days_out"])

    # The curated macro series are the highest-value questions, but on many days
    # they simply do not supply enough. Rather than run a thin panel -- which
    # costs statistical power in every stress bin -- widen to the full Economics
    # and Financials universe and take the most liquid additional questions.
    if broaden_if_short and len(selected) < max_tasks and series_tickers is None:
        have = {m["ticker"] for m in selected}
        try:
            extra_series = [
                t for t in fetch_series_tickers(("Economics", "Financials"))
                if t not in set(PRIORITY_SERIES)
            ]
        except FetchError:
            extra_series = []

        for series_ticker in extra_series:
            if len(selected) >= max_tasks:
                break

            # Build this series' candidates FIRST, then assign ladder positions
            # per event, then take them. Appending market-by-market -- as this
            # loop used to -- means no market ever sees the rest of its own strike
            # ladder, so `ladder_distance` cannot be computed and was simply
            # absent. H1's experimental leg was silently empty on every broadened
            # task. See `assign_ladder_distance`.
            candidates: List[Dict[str, Any]] = []
            for market in fetch_open_markets_for_series(series_ticker, limit=20):
                ticker = str(market.get("ticker", ""))
                if not ticker or ticker in have:
                    continue
                if market.get("status") not in ("open", "active"):
                    continue
                close = _parse_ts(market.get("close_time"))
                if close is None:
                    continue
                days_out = (close - now).total_seconds() / 86400.0
                if not (min_days_out <= days_out <= max_days_out):
                    continue
                title = str(market.get("title") or market.get("subtitle") or "")
                if not title:
                    continue
                candidates.append({
                    "ticker": ticker,
                    "event_ticker": str(market.get("event_ticker") or ticker),
                    "series_ticker": series_ticker,
                    "title": title,
                    "rules": str(market.get("rules_primary") or "")[:1200],
                    "close_time": market.get("close_time"),
                    "days_out": round(days_out, 2),
                    "strike": _strike_of(market),
                    "market_implied": None,
                })

            by_extra_event: Dict[str, List[Dict[str, Any]]] = {}
            for market in candidates:
                by_extra_event.setdefault(market["event_ticker"], []).append(market)
            for group in by_extra_event.values():
                assign_ladder_distance(group)

            for market in candidates:
                if len(selected) >= max_tasks:
                    break
                have.add(market["ticker"])
                selected.append(market)

    chosen = selected[:max_tasks]

    # A registered state variable that is irrecoverable if missed must never
    # leave this function unset. Finding 12 of AUDIT.md fixed the propagation of
    # this value and a second path was still dropping it; the invariant is
    # cheaper than a third audit.
    missing = [m["ticker"] for m in chosen if m.get("ladder_distance") is None]
    if missing:
        raise FetchError(
            f"ladder_distance missing for {len(missing)} selected market(s): "
            f"{missing[:5]}. It is a registered H1 state variable recorded at ask "
            f"time and cannot be reconstructed later."
        )

    return chosen


def fetch_settlement(ticker: str) -> Optional[float]:
    """Resolved outcome: 1.0 (yes), 0.0 (no), or None if not yet settled.

    Verified public: settled markets report result='yes'/'no' with
    status='finalized'.
    """
    try:
        payload = get_json(f"{BASE}/markets/{ticker}")
    except FetchError:
        return None

    market = payload.get("market") or {}
    if market.get("status") not in ("settled", "finalized", "closed"):
        return None

    result = str(market.get("result") or "").strip().lower()
    if result == "yes":
        return 1.0
    if result == "no":
        return 0.0
    return None

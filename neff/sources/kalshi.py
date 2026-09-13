"""Kalshi event contracts -- the primary task source and ground truth.

Kalshi is a CFTC-regulated exchange for event contracts. Public market data needs
no authentication.

VERIFIED 17 Aug 2026, and one finding shaped this module:

  - Series browsing, market listing, and SETTLEMENT are all public.
    A settled market reports result='yes'/'no' with status='finalized', which is
    unambiguous ground truth requiring no judgement call from us.

  - Quotes appeared not to be public: yes_bid / yes_ask / last_price / volume
    came back null on every economics series, including on individual market
    fetch.

    CORRECTED 2026-09-13. The quotes were public; the field names had changed.
    Kalshi serves prices as dollar strings (`yes_bid_dollars: "0.4100"`) and
    sizes as fixed-point strings (`volume_fp`), and the old integer fields are
    gone. Every market fetched on 2026-09-13 carried the new ones, and hourly
    history is served by the candlesticks endpoint. They are recorded on the
    task from 2026-09-14 (PREREGISTRATION.md 11, deviation 15); `market_implied`
    was null on every task before that, and PREREGISTRATION.md 10 limitation 1
    rests on the mistaken reading. (There is no polymarket.py.)

Because we could not see prices, selection does not filter near-certain
contracts by their implied probability -- and still does not, because selection
is registered and a quote is recorded, never used to choose. Instead we exploit
Kalshi's strike-ladder structure:
a series like KXCPIYOY lists many thresholds for the same event, and the MIDDLE
strikes are the genuinely uncertain ones while the extremes are near-foregone.
Selecting median strikes per event gives informative questions without needing
quotes -- see select_tasks().

Every task we register is drawn from OPEN markets only, so no outcome exists at
the moment we ask.
"""

import math
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


# --- the market's own price ----------------------------------------------------
#
# Kalshi serves prices as dollar strings and sizes as fixed-point strings. The
# 17 Aug check read the integer fields these replaced (`yes_bid`, `last_price`),
# found them null or absent, and concluded the quotes were not public. They were
# (PREREGISTRATION.md 11, deviation 15).
_QUOTE_FIELDS = (
    ("yes_bid", "yes_bid_dollars"),
    ("yes_ask", "yes_ask_dollars"),
    ("last_price", "last_price_dollars"),
    ("previous_price", "previous_price_dollars"),
    ("volume", "volume_fp"),
    ("volume_24h", "volume_24h_fp"),
    ("open_interest", "open_interest_fp"),
    ("liquidity", "liquidity_dollars"),
)


def _number(value: Any) -> Optional[float]:
    """A finite float, or None. Never 0 for a field that is missing or malformed."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def market_quote(market: Dict[str, Any], observed_at: Optional[str] = None) -> Dict[str, Any]:
    """The market's standing quote when the question was put to the panel.

    Recorded on the task, NEVER in the prompt: `tasks.build_daily_tasks` builds
    the prompt before attaching it. A price shown to the panel would change the
    instrument and hand every model the same anchor.
    """
    quote: Dict[str, Any] = {
        name: _number(market.get(field)) for name, field in _QUOTE_FIELDS
    }
    quote["observed_at"] = observed_at
    return quote


def implied_probability(quote: Optional[Dict[str, Any]]) -> Optional[float]:
    """Midpoint of the standing yes bid and ask, or None when there is no quote.

    Unfiltered on purpose. A 0-30 cent quote is recorded as the 15 cents it
    implies; whether a quote that wide is informative is a judgement for the
    analysis to state, not one for collection to make silently.
    """
    if not quote:
        return None
    bid, ask = quote.get("yes_bid"), quote.get("yes_ask")
    if bid is None or ask is None or ask <= 0.0 or not (0.0 <= bid <= ask <= 1.0):
        return None
    return round((bid + ask) / 2.0, 4)


# --- the shape of each question's own ladder ------------------------------------
#
# `assign_ladder_distance` positions a strike against the markets it is handed.
# The curated path hands it a whole SERIES -- every open expiry at once -- and an
# event with no numeric ladder gets 0.0, the value a real ladder's median strike
# also gets. Both are kept exactly as the code ran at registration, because a
# recorded variable that changes meaning mid-panel splits the record. These
# fields describe the ladder a question actually sits on, so the analysis can
# tell the cases apart (PREREGISTRATION.md 11, deviations 15 and 17).
_NUMERIC_STRIKE_TYPES = {"greater", "greater_or_equal", "less", "less_or_equal", "between"}


def _is_numeric_rung(market: Dict[str, Any]) -> bool:
    """Is this market one rung of a numeric ladder, rather than a category?

    Fed and central-bank decisions are served as `custom` strikes keyed `Cut`,
    `Hike` or `Action`, and their tickers (`C26`, `H0`) parse as numbers without
    being strikes. Exact-value buckets are `custom` strikes keyed `Value`, and
    are rungs. A market with no `strike_type` at all is judged on its parsed
    strike alone, which is how every market looked before the field was read.
    """
    if market.get("strike") is None:
        return False
    strike_type = market.get("strike_type")
    if not strike_type:
        return True
    if strike_type in _NUMERIC_STRIKE_TYPES:
        return True
    custom = market.get("custom_strike")
    if strike_type == "custom" and isinstance(custom, dict) and len(custom) == 1:
        (key, value), = custom.items()
        return str(key).strip().lower() == "value" and _number(value) is not None
    return False


def annotate_event_ladders(markets: List[Dict[str, Any]]) -> None:
    """`event_ladder_size` and `event_ladder_distance`, per real Kalshi event.

    The event is Kalshi's own `event_ticker`: one expiry of one series. The
    distance is |strike - median| / span over that event's numeric rungs -- the
    quantity PREREGISTRATION.md 4 describes as `ladder_distance` -- and it is
    None, never 0.0, for a market that is not a rung or an event with fewer than
    three of them.
    """
    by_event: Dict[str, List[Dict[str, Any]]] = {}
    for market in markets:
        key = str(market.get("kalshi_event") or market.get("event_ticker") or "")
        by_event.setdefault(key, []).append(market)
    for group in by_event.values():
        rungs = sorted(m["strike"] for m in group if _is_numeric_rung(m))
        size = len(rungs)
        median = statistics.median(rungs) if rungs else None
        span = (rungs[-1] - rungs[0]) if size >= 2 else 0.0
        for market in group:
            market["event_ladder_size"] = size
            if size >= 3 and span > 0 and _is_numeric_rung(market):
                market["event_ladder_distance"] = round(
                    abs(market["strike"] - median) / span, 6
                )
            else:
                market["event_ladder_distance"] = None


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

    # No usable ladder: 0.0 rather than missing. This is the convention the code
    # carried at registration; PREREGISTRATION.md never states it, and 0.0 is
    # also what the MEDIAN strike of a real ladder records, so the stored value
    # cannot tell the two apart. Collection keeps writing it, because a recorded
    # variable must not change meaning mid-panel; the analysis treats it as
    # undefined for an event without a numeric ladder (deviation 17), and
    # `annotate_event_ladders` records the difference on every new row.
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

            # NB: this strips the EXPIRY from Kalshi's event ticker, so the group
            # below is a series, not an event -- every open expiry shares one
            # ladder median. Kept as registered; see `annotate_event_ladders`.
            event_ticker = str(market.get("event_ticker") or market.get("ticker", "")).rsplit("-", 1)[0]
            quote = market_quote(market, observed_at=now.isoformat())
            record = {
                "ticker": str(market.get("ticker", "")),
                "event_ticker": event_ticker,
                "kalshi_event": str(market.get("event_ticker") or ""),
                "series_ticker": series_ticker,
                "title": str(market.get("title") or market.get("subtitle") or ""),
                "rules": str(market.get("rules_primary") or "")[:1200],
                "close_time": market.get("close_time"),
                "days_out": round(days_out, 2),
                "strike": _strike_of(market),
                "strike_type": market.get("strike_type"),
                "custom_strike": market.get("custom_strike"),
                "quote": quote,
                "market_implied": implied_probability(quote),
            }
            if record["ticker"] and record["title"]:
                by_event.setdefault(event_ticker, []).append(record)

    selected: List[Dict[str, Any]] = []
    for event_ticker, markets in sorted(by_event.items()):
        annotate_event_ladders(markets)
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
                quote = market_quote(market, observed_at=now.isoformat())
                candidates.append({
                    "ticker": ticker,
                    "event_ticker": str(market.get("event_ticker") or ticker),
                    "kalshi_event": str(market.get("event_ticker") or ""),
                    "series_ticker": series_ticker,
                    "title": title,
                    "rules": str(market.get("rules_primary") or "")[:1200],
                    "close_time": market.get("close_time"),
                    "days_out": round(days_out, 2),
                    "strike": _strike_of(market),
                    "strike_type": market.get("strike_type"),
                    "custom_strike": market.get("custom_strike"),
                    "quote": quote,
                    "market_implied": implied_probability(quote),
                })

            by_extra_event: Dict[str, List[Dict[str, Any]]] = {}
            for market in candidates:
                by_extra_event.setdefault(market["event_ticker"], []).append(market)
            for group in by_extra_event.values():
                annotate_event_ladders(group)
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

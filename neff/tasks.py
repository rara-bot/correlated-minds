"""Build the daily task battery.

A "task" is one forecasting question, registered before its outcome exists.

Two design choices that follow directly from the Week-0 human-baseline finding:

1. WE PREFER GENUINELY UNCERTAIN QUESTIONS. Measuring the SPF showed that
   near-term nowcasts saturate the metric -- human error correlation runs ~0.996
   at horizon 1 but drops to ~0.876 three quarters out. Questions whose answers
   are nearly known compress error variance toward zero and make every
   forecaster look identical for an uninteresting reason. So task selection
   weights toward longer horizons and away from anything close to settled.

2. WE RE-ASK OPEN QUESTIONS DAILY. The same contract is asked every day until it
   resolves. That costs little and buys a second dimension: how each model's
   belief evolves as information arrives, and whether the panel converges as
   resolution approaches. A single snapshot per question would throw that away.
"""

import hashlib
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from .config import DATA_FREEZE, TASKS_PER_DAY
from .providers import RESPONSE_INSTRUCTIONS
from .sources import edgar, fred, kalshi
from .store import Task

PROMPT_TEMPLATE = """\
{instructions}
--- QUESTION ---
{title}

{resolution_criteria}
Resolution date: {close_time}
Today's date: {today}

--- MARKET CONTEXT (as of today) ---
{context}

Give your probability that the stated outcome resolves YES.
"""

# Prompt variants for the H3 test: does prompt-level diversity buy any real
# independence, or only cross-family diversity? Variants must differ in framing
# while asking exactly the same question -- otherwise we would be measuring
# question differences, not diversity.
PROMPT_VARIANTS = [
    "",
    "Think like a careful professional forecaster who is scored on calibration.\n",
    "Consider the base rate for this kind of event first, then adjust.\n",
    "Consider what would have to be true for the answer to be the opposite of your first instinct.\n",
    "You are advising a risk committee. State the probability you would defend.\n",
]


def _task_id(source_ref: str, as_of: date) -> str:
    """Stable per-day id, so re-running a day is idempotent."""
    raw = f"{source_ref}|{as_of.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _format_context(state: Dict[str, Optional[float]]) -> str:
    labels = [
        ("vix_level", "VIX"),
        ("treasury_10y", "10-year Treasury yield"),
        ("yield_curve_10y2y", "10Y-2Y spread"),
        ("fed_funds", "Effective fed funds rate"),
    ]
    lines = []
    for key, label in labels:
        value = state.get(key)
        if value is not None:
            lines.append(f"- {label}: {value:.2f}")
    return "\n".join(lines) if lines else "- (market context unavailable today)"


def build_prompt(
    title: str,
    resolution_criteria: str,
    close_time: str,
    context: str,
    as_of: date,
    variant: int = 0,
) -> str:
    prefix = PROMPT_VARIANTS[variant % len(PROMPT_VARIANTS)]
    return PROMPT_TEMPLATE.format(
        instructions=prefix + RESPONSE_INSTRUCTIONS,
        title=title.strip(),
        resolution_criteria=(
            f"Resolution criteria: {resolution_criteria.strip()}\n"
            if resolution_criteria.strip()
            else ""
        ),
        close_time=close_time,
        today=as_of.isoformat(),
        context=context,
    )


def days_until_freeze(as_of: date) -> float:
    """Days remaining until the pre-registered data freeze (6 Dec 2026).

    This is a hard scientific boundary, not a preference. A question resolving
    after the freeze can never be scored, so forecasts on it are unusable in the
    primary analysis -- we would be paying for observations that cannot enter a
    result. The usable horizon therefore shrinks by one day, every day.
    """
    freeze = datetime.strptime(DATA_FREEZE, "%Y-%m-%d").date()
    return max(0.0, (freeze - as_of).days)


def build_daily_tasks(
    as_of: Optional[date] = None,
    max_tasks: int = TASKS_PER_DAY,
    include_state: bool = True,
    min_days_out: float = 3.0,
    max_days_out: Optional[float] = None,
    respect_freeze: bool = True,
    filing_fraction: float = 0.4,
) -> List[Task]:
    """Assemble today's questions.

    min_days_out defaults to 3 rather than 1: contracts resolving within hours
    are effectively already decided, and per the finding above they would
    saturate the correlation estimate.

    max_days_out is capped at the data freeze by default, so every question we
    pay for can actually be scored inside the study.

    filing_fraction splits the battery between two task types, and the split is
    a validity decision rather than a convenience:

      MACRO (Kalshi)   -- directly comparable to the Philadelphia Fed's human
                          forecaster panel, which is the study's headline
                          benchmark. But macro forecasting is NOT the dominant
                          real-world use of LLMs in finance.

      FILING (EDGAR)   -- read a company's own SEC filings, then judge its next
                          reported quarter. This matches what banks and funds
                          actually deploy: the BoE/FCA survey and 2026 industry
                          data both put document-grounded analysis of financial
                          reports at the centre of real use.

    Running both lets us test whether error correlation is a property of the
    models or an artefact of one task format -- which is itself a result.
    """
    today = as_of or datetime.now(timezone.utc).date()

    horizon_cap = max_days_out if max_days_out is not None else 120.0
    if respect_freeze:
        horizon_cap = min(horizon_cap, days_until_freeze(today))
    if horizon_cap <= min_days_out:
        return []

    state: Dict[str, Optional[float]] = {}
    if include_state:
        try:
            state = fred.state_snapshot(today)
        except Exception:                                   # noqa: BLE001
            state = {}
    context = _format_context(state)

    n_filing = int(round(max_tasks * max(0.0, min(1.0, filing_fraction))))
    n_event = max_tasks - n_filing

    candidates = kalshi.select_tasks(
        max_tasks=n_event,
        min_days_out=min_days_out,
        max_days_out=horizon_cap,
        broaden_if_short=True,
    )

    tasks: List[Task] = []
    for candidate in candidates:
        ticker = candidate["ticker"]
        prompt = build_prompt(
            title=candidate["title"],
            resolution_criteria=candidate.get("rules", ""),
            close_time=str(candidate.get("close_time", "")),
            context=context,
            as_of=today,
            variant=0,
        )
        tasks.append(
            Task(
                task_id=_task_id(ticker, today),
                kind="event",
                prompt=prompt,
                resolves_after=str(candidate.get("close_time") or ""),
                source="kalshi",
                source_ref=ticker,
                outcome_kind="binary",
                market_implied=candidate.get("market_implied"),
                state=dict(
                    state,
                    # ladder_distance is computed in kalshi.select_tasks and MUST
                    # be carried here. It is the experimental leg of H1 -- the one
                    # state variable populated every day regardless of whether
                    # markets supply a stress event (PREREGISTRATION.md 4, 10.5).
                    # It also cannot be backfilled: it needs the live strike
                    # ladder as it stood on the day the question was asked, and
                    # closed Kalshi ladders are not reliably re-queryable. Dropping
                    # it here silently made H1 untestable in a calm regime, which
                    # is precisely the scenario 10.5 claims it protects against.
                    ladder_distance=candidate.get("ladder_distance"),
                    days_out=candidate.get("days_out"),
                    series=candidate.get("series_ticker"),
                    strike=candidate.get("strike"),
                    asked_on=today.isoformat(),
                ),
            )
        )

    # --- document-grounded filing tasks ---------------------------------
    if n_filing > 0:
        try:
            filings = edgar.build_universe_tasks(today, max_tasks=n_filing)
        except Exception:                                  # noqa: BLE001
            filings = []

        for candidate in filings:
            prompt = build_prompt(
                title=candidate["title"],
                resolution_criteria=candidate.get("rules", ""),
                close_time="when the company files its next 10-Q or 10-K",
                context=candidate.get("context", "") + "\n\n" + context,
                as_of=today,
                variant=0,
            )
            tasks.append(
                Task(
                    task_id=_task_id(candidate["source_ref"], today),
                    kind="filing",
                    prompt=prompt,
                    resolves_after="",
                    source="edgar",
                    source_ref=candidate["source_ref"],
                    outcome_kind="binary",
                    market_implied=None,
                    state=dict(
                        state,
                        ticker=candidate["ticker"],
                        cik=candidate["cik"],
                        threshold=candidate["threshold"],
                        last_reported_end=candidate["last_reported_end"],
                        asked_on=today.isoformat(),
                    ),
                )
            )

    return tasks[:max_tasks]


def summarize(tasks: List[Task]) -> Dict[str, Any]:
    by_series: Dict[str, int] = {}
    horizons: List[float] = []
    for task in tasks:
        series = str(task.state.get("series") or "?")
        by_series[series] = by_series.get(series, 0) + 1
        days_out = task.state.get("days_out")
        if isinstance(days_out, (int, float)):
            horizons.append(float(days_out))

    by_kind: Dict[str, int] = {}
    for task in tasks:
        by_kind[task.kind] = by_kind.get(task.kind, 0) + 1

    return {
        "n_tasks": len(tasks),
        "by_kind": by_kind,
        "by_series": dict(sorted(by_series.items())),
        "median_days_out": (
            round(sorted(horizons)[len(horizons) // 2], 1) if horizons else None
        ),
        "min_days_out": round(min(horizons), 1) if horizons else None,
        "max_days_out": round(max(horizons), 1) if horizons else None,
    }

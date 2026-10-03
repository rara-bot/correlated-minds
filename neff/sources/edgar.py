"""SEC EDGAR -- document-grounded forecasting tasks.

WHY THIS MODULE EXISTS (ecological validity)

Our first task type asks models to forecast macro variables (CPI, payrolls, Fed
decisions). Those are clean and directly comparable to the Philadelphia Fed's
human forecaster panel -- but they are NOT what financial institutions mainly
use language models for.

The evidence on real deployment:
  - Bank of England / FCA joint survey: 75% of UK financial firms use AI;
    foundation models are 17% of all AI use cases.
  - 2026 industry data: 55% of hedge-fund and banking investors have AI in the
    investment process (research, due diligence, risk monitoring).
  - The dominant LLM use cases are DOCUMENT-GROUNDED: analysing financial
    reports and earnings-call transcripts, extracting sentiment from news, and
    retrieval-augmented pipelines that ingest financial statements and classify
    direction.

So a study measuring only macro forecasting would measure a real cognitive act,
but not the one banks actually deploy. This module closes that gap by adding
tasks with the shape real systems face: **read a company's actual filing, then
make a forward-looking judgement about that company.**

DESIGN

Task:   Given the revenue history disclosed in a company's own SEC filings
        through today, will NEXT quarter's reported revenue exceed a threshold?
Truth:  The value the company itself reports in its next 10-Q/10-K, read from
        XBRL company facts.

Three properties make this a good task:

1. CONTAMINATION-PROOF BY CONSTRUCTION -- but only while the source is live.
   The next quarter has not been filed, so no amount of pretraining can contain
   the answer. That holds only if the freshest figure we can see is genuinely
   recent. If a filer's tag series has gone dead, the "next" quarter is one the
   company reported years ago, and every model may simply recall it.
   MAX_REPORTING_GAP_DAYS enforces the precondition; without it this property
   is assumed rather than built in, and a contaminated task is indistinguishable
   from a good one at every later stage.
2. UNAMBIGUOUS GROUND TRUTH. The outcome is a number the company reports itself,
   in a structured field, with a filing date. No judgement call from us.
3. NO PRICE DATA NEEDED. Free daily equity prices are hard to obtain reliably
   (Stooq serves a JS challenge behind an HTTP 200). Anchoring on reported
   fundamentals sidesteps that dependency entirely.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from .http import FetchError, get_json

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
COMPANY_CONCEPT = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"
)
COMPANY_TICKERS = "https://www.sec.gov/files/company_tickers.json"

# Revenue is reported under several tags depending on the filer and era. Try in
# order of how current they are.
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
)

# A live quarterly filer produces a new reported period roughly every 92 days.
# Allowing two missed quarters plus a filing lag puts the outer edge of normal
# reporting at ~200 days. Past that, the tag series is no longer tracking the
# company: the successor quarter exists, was filed long ago, and is reported
# under a tag we are not reading -- so the task would ask for something the
# models can recall rather than forecast.
#
# Banks are the live case. JPMorgan reports under RevenuesNetOfInterestExpense,
# which is not in REVENUE_TAGS, so its best available series ends in 2014.
# Measured across the collected battery on 2026-09-08, ordinary filers sat at
# 32-161 days and JPM sat at 4,269.
MAX_REPORTING_GAP_DAYS = 200

# THE NEXT QUARTER MUST NOT ALREADY BE PAST ITS FILING DEADLINE.
#
# MAX_REPORTING_GAP_DAYS catches a series that died years ago. It cannot catch
# one that stopped a single quarter ago, and on 2026-09-13 one had. ExxonMobil
# filed its Q2 2026 10-Q on 2026-08-03, but no revenue fact in its company facts
# is a three-month figure ending 2026-06-30, so the freshest XOM quarter visible
# here stayed 2026-03-31. Every XOM task from 2026-09-01 asked the panel about a
# quarter whose figure was already filed -- the property "contamination-proof by
# construction" rests on -- and the resolver would have scored those questions
# against Q3 instead (PREREGISTRATION.md 11, deviation 16).
#
# The SEC sets the edge, so no threshold is tuned to the data. A fiscal quarter
# is at most 14 weeks. Large accelerated filers -- all of DEFAULT_UNIVERSE --
# must file a 10-Q within 40 days of quarter end and a 10-K within 60 days of
# year end. A question about the quarter after the latest visible one, asked
# later than that, is about a figure that is, or by law already had to be,
# public.
MAX_QUARTER_DAYS = 98
TEN_Q_DEADLINE_DAYS = 40
TEN_K_DEADLINE_DAYS = 60

# PREREGISTRATION.md 3.3: "at least 8 usable point-in-time quarters of history".
# The builder checked 6. Every company in the universe has far more, so enforcing
# the registered figure changes no task; it makes the code say what the plan says.
MIN_HISTORY_QUARTERS = 8


def filing_deadline_gap(last_fp: Optional[str]) -> int:
    """Days after the last visible period end by which the NEXT quarter must be filed.

    The next quarter is a fiscal Q4, reported in the 10-K, only when the last
    visible one is Q3. An unrecognised label takes the longer 10-K allowance, so
    an unfamiliar label can only keep a task, never wrongly refuse one.
    """
    fp = (last_fp or "").strip().upper()
    if fp in ("Q1", "Q2", "Q4", "Q4D", "FY"):
        return MAX_QUARTER_DAYS + TEN_Q_DEADLINE_DAYS
    return MAX_QUARTER_DAYS + TEN_K_DEADLINE_DAYS

# Large, liquid, reliably quarterly filers across several sectors. Sector spread
# matters: a panel of only mega-cap tech would confound "model agreement" with
# "these companies are unusually easy to forecast".
DEFAULT_UNIVERSE: Tuple[Tuple[str, int], ...] = (
    ("AAPL", 320193),
    ("MSFT", 789019),
    ("NVDA", 1045810),
    ("JPM", 19617),
    ("WMT", 104169),
    ("XOM", 34088),
    ("JNJ", 200406),
    ("PG", 80424),
    ("KO", 21344),
    ("CAT", 18230),
    ("UNH", 731766),
    ("HD", 354950),
    # Added 2026-09-13 (PREREGISTRATION.md 11, deviation 16), LAST, so that no
    # company above changes place in the build order. KO has never built a task
    # (no quarterly series under any tag read here), JPM is refused as a dead
    # series (deviation 3), and XOM is refused while its latest visible quarter
    # is past its filing deadline -- which left nine companies for ten daily
    # slots and would have moved the registered 60/40 mix. Chevron replaces the
    # universe's only energy filer with another, so the sector spread above
    # survives.
    ("CVX", 93410),
)


@dataclass
class QuarterlyFact:
    """One reported quarterly figure."""

    fy: int
    fp: str
    start: date
    end: date
    filed: date
    value: float
    accession: str = ""

    @property
    def duration_days(self) -> int:
        return (self.end - self.start).days


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _collect_facts(cik: int, tag: str) -> Tuple[Dict[date, QuarterlyFact], Dict[date, QuarterlyFact]]:
    """Return ({period_end: quarterly fact}, {period_end: annual fact}) for one tag.

    Both dicts are keyed by the PERIOD END DATE, never by XBRL's `fy` field.
    `fy` is the fiscal year of the FILING, not of the period the fact covers,
    and a 10-K carries three years of comparative income-statement figures --
    so keying on `fy` collapses three distinct annual periods into one entry and
    silently attributes the wrong year's revenue.
    """
    payload = get_json(COMPANY_CONCEPT.format(cik=cik, tag=tag))
    rows = payload.get("units", {}).get("USD", [])

    quarterly: Dict[date, QuarterlyFact] = {}
    annual: Dict[date, QuarterlyFact] = {}

    for row in rows:
        if row.get("form") not in ("10-Q", "10-K"):
            continue
        start_d = _parse_date(row.get("start"))
        end_d = _parse_date(row.get("end"))
        filed = _parse_date(row.get("filed"))
        value = row.get("val")
        if not (start_d and end_d and filed) or not isinstance(value, (int, float)):
            continue

        fact = QuarterlyFact(
            fy=int(row.get("fy") or end_d.year),
            fp=str(row.get("fp") or "?"),
            start=start_d,
            end=end_d,
            filed=filed,
            value=float(value),
            accession=str(row.get("accn") or ""),
        )
        duration = (end_d - start_d).days

        if 80 <= duration <= 100:
            existing = quarterly.get(end_d)
            if existing is None or fact.filed < existing.filed:
                quarterly[end_d] = fact
        elif 350 <= duration <= 380:
            existing = annual.get(end_d)
            if existing is None or fact.filed < existing.filed:
                annual[end_d] = fact

    return quarterly, annual


def _derive_missing_q4(
    quarterly: Dict[date, QuarterlyFact], annual: Dict[date, QuarterlyFact]
) -> int:
    """Reconstruct fiscal Q4 as (annual - Q1 - Q2 - Q3).

    Many filers -- Apple and Microsoft among them -- never publish a standalone
    Q4 10-Q; the fourth quarter appears only folded into the annual 10-K figure.
    That leaves a hole in the quarterly series exactly where the year-earlier
    comparator for a Q4 forecast should be, which silently dropped those
    companies from the study entirely.

    The identity is exact, not an approximation: the three reported quarters and
    the annual total are all the company's own audited numbers, so the residual
    IS the fourth quarter. We mark derived facts with fp='Q4D' so nothing later
    mistakes a reconstruction for a directly reported figure.
    """
    derived = 0
    for year_end, year_fact in sorted(annual.items()):
        members = [f for f in quarterly.values() if year_fact.start <= f.start and f.end <= year_fact.end]
        if len(members) != 3:
            continue
        covered = sum(f.value for f in members)
        latest_member = max(members, key=lambda f: f.end)
        q4_end = year_fact.end
        if q4_end in quarterly:
            continue
        gap_days = (q4_end - latest_member.end).days
        if not (80 <= gap_days <= 100):
            continue
        value = year_fact.value - covered
        if value <= 0:
            continue
        quarterly[q4_end] = QuarterlyFact(
            fy=year_fact.fy,
            fp="Q4D",
            start=latest_member.end,
            end=q4_end,
            filed=year_fact.filed,
            value=value,
            accession=year_fact.accession,
        )
        derived += 1
    return derived


def fetch_quarterly_revenue(cik: int) -> List[QuarterlyFact]:
    """Quarterly revenue history for one company, most recent last.

    Two corrections that were each producing wrong data:

    1. TAG SELECTION BY RECENCY, not by first match. Filers migrate between XBRL
       revenue tags over time, and a superseded tag keeps returning its old
       history forever. NVIDIA's RevenueFromContractWithCustomer... series stops
       in 2020 at $3.1bn while its Revenues series runs to 2026 at $81.6bn --
       taking the first tag that returned anything silently built the study on
       six-year-old data.

    2. XBRL reports MULTIPLE durations sharing a period end -- a three-month
       figure and a year-to-date roll-up. Mixing them would compare a quarter
       against a nine-month total (Apple Q3 2026: $109bn vs $364bn).

    Both are silent failures: the code runs, the numbers look plausible, and the
    science is wrong.
    """
    candidates: List[Tuple[date, int, List[QuarterlyFact]]] = []
    last_error = ""

    for tag in REVENUE_TAGS:
        try:
            quarterly, annual = _collect_facts(cik, tag)
        except FetchError as exc:
            last_error = str(exc)
            continue
        if not quarterly:
            continue
        _derive_missing_q4(quarterly, annual)
        series = sorted(quarterly.values(), key=lambda f: f.end)
        candidates.append((series[-1].end, len(series), series))

    if not candidates:
        if last_error:
            raise FetchError(f"CIK {cik}: no usable revenue tag ({last_error})")
        return []

    # Most recent data wins; more history breaks ties.
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    return candidates[0][2]


def visible_history(facts: List[QuarterlyFact], as_of: date) -> List[QuarterlyFact]:
    """Only facts already FILED by `as_of`.

    This is the point-in-time guard. Filtering on the period end date instead of
    the filing date would leak a quarter that had ended but not yet been
    reported -- lookahead bias of exactly the kind that has sunk published work
    in this area.
    """
    return [f for f in facts if f.filed <= as_of]


def same_quarter_last_year(
    history: List[QuarterlyFact], reference: QuarterlyFact
) -> Optional[QuarterlyFact]:
    """Find the year-earlier quarter by DATE, not by list position.

    Position-based lookup (history[-4]) is wrong: many filers' fiscal Q4 appears
    only inside the annual 10-K rather than a 10-Q, so the quarterly series has
    gaps and the fourth-from-last entry is often 15 or 18 months back, not 12.
    Matching on the period end date is robust to those gaps.
    """
    target_days = 365
    best: Optional[QuarterlyFact] = None
    best_gap = 10 ** 9
    for fact in history:
        gap = abs((reference.end - fact.end).days - target_days)
        if gap <= 25 and gap < best_gap:
            best, best_gap = fact, gap
    return best


def trailing_yoy_growth(history: List[QuarterlyFact]) -> Optional[float]:
    """Median year-over-year growth across quarters we can pair up."""
    growths: List[float] = []
    for fact in history:
        prior = same_quarter_last_year(history, fact)
        if prior and prior.value > 0:
            growths.append(fact.value / prior.value - 1.0)
    if not growths:
        return None
    growths.sort()
    return growths[len(growths) // 2]


def next_period_threshold(
    history: List[QuarterlyFact],
) -> Optional[Tuple[float, str]]:
    """A threshold that makes the question genuinely uncertain.

    Naive choices fail badly:

      - "beat last quarter" is near-deterministic for seasonal filers.
      - "beat the same quarter last year" is near-deterministic for any growing
        company. Apple reported $109B against a year-earlier $94B, so that
        question resolves YES with near-certainty and carries no information.

    Per the Week-0 saturation finding, near-certain questions compress error
    variance toward zero and make every forecaster look identical for an
    uninteresting reason -- which would corrupt the very quantity we measure.

    So the threshold is the year-earlier quarter GROWN AT THE COMPANY'S OWN
    TRAILING TREND. The question becomes "will growth continue at trend?", which
    is what an analyst actually has to judge, and which is genuinely a coin flip.
    """
    if len(history) < 6:
        return None

    latest = history[-1]

    # The quarter being forecast ends roughly 91 days after the last reported
    # one; its year-earlier comparator is ~274 days before the latest.
    target_end_gap = 91 - 365
    comparator: Optional[QuarterlyFact] = None
    best_gap = 10 ** 9
    for fact in history:
        gap = abs((fact.end - latest.end).days - target_end_gap)
        if gap <= 25 and gap < best_gap:
            comparator, best_gap = fact, gap

    if comparator is None or comparator.value <= 0:
        return None

    growth = trailing_yoy_growth(history)
    if growth is None:
        return None

    # Clamp: an extreme trailing growth rate (a one-off acquisition, say) would
    # push the threshold somewhere absurd and re-saturate the question.
    growth = max(-0.35, min(0.60, growth))
    threshold = comparator.value * (1.0 + growth)

    label = (
        f"the quarter ending {comparator.end} (${comparator.value / 1e9:,.2f}B) "
        f"grown at this company's trailing year-over-year trend of {growth:+.1%}"
    )
    return threshold, label


def build_filing_task(
    ticker: str,
    cik: int,
    as_of: date,
    facts: Optional[List[QuarterlyFact]] = None,
) -> Optional[Dict[str, Any]]:
    """Build one document-grounded forecasting question, or None if unsuitable."""
    try:
        all_facts = facts if facts is not None else fetch_quarterly_revenue(cik)
    except FetchError:
        return None

    history = visible_history(all_facts, as_of)
    if len(history) < MIN_HISTORY_QUARTERS:
        return None

    # STALENESS GUARD. A dead series produces a question whose answer is already
    # public, and it looks exactly like a good one: same shape, same scoring
    # path, same prompt. It has to be refused at the point of construction,
    # because nothing downstream can tell the difference.
    if (as_of - history[-1].end).days > MAX_REPORTING_GAP_DAYS:
        return None

    # DEADLINE GUARD -- the same failure one quarter deep instead of ten years.
    # See `filing_deadline_gap`.
    if (as_of - history[-1].end).days > filing_deadline_gap(history[-1].fp):
        return None

    picked = next_period_threshold(history)
    if picked is None:
        return None
    threshold, threshold_label = picked
    if threshold <= 0:
        return None

    latest = history[-1]
    recent = history[-6:]
    table = "\n".join(
        f"  {f.fy} {f.fp}  quarter ending {f.end}  revenue ${f.value / 1e9:,.2f}B "
        f"(reported {f.filed})"
        for f in recent
    )

    return {
        "ticker": ticker,
        "cik": cik,
        "title": (
            f"Will {ticker}'s next reported quarterly revenue exceed "
            f"${threshold / 1e9:,.2f}B?"
        ),
        "context": (
            f"{ticker} quarterly revenue as reported in its own SEC filings, "
            f"through {as_of}:\n{table}\n\n"
            f"The most recent reported quarter ended {latest.end} "
            f"(filed {latest.filed}). The threshold (${threshold / 1e9:,.2f}B) is "
            f"{threshold_label}."
        ),
        "rules": (
            f"Resolves YES if the revenue {ticker} reports for the quarter "
            f"following {latest.end}, as filed with the SEC in XBRL, exceeds "
            f"${threshold:,.0f}."
        ),
        "threshold": threshold,
        "threshold_label": threshold_label,
        "last_reported_end": latest.end.isoformat(),
        "last_reported_fp": latest.fp,
        "last_reported_value": latest.value,
        "last_filed": latest.filed.isoformat(),
        "source_ref": f"edgar:{cik}:{latest.end.isoformat()}",
    }


def resolve_filing_task_details(
    cik: int, last_reported_end: str, threshold: float
) -> Optional[Dict[str, Any]]:
    """The outcome and the filed figure behind it, once the next quarter is filed.

    Strictly point-in-time: we look for a period that ENDS after the one the
    forecaster could see, and only count it once it has actually been filed.

    AND ONLY THE QUARTER THAT WAS ASKED ABOUT. The question is about "the quarter
    following" the last visible one. This used to take the earliest later
    quarter of any kind, so a filer whose next quarter never becomes visible
    under a tag read here -- ExxonMobil's Q2 2026 (deviation 16) -- would have
    been scored against the quarter after it. A quarter ending more than
    MAX_QUARTER_DAYS + 14 days after the cutoff is not the next one, and the task
    stays unresolved rather than being settled against the wrong figure.

    The details travel with the resolution, because PREREGISTRATION.md 3.3
    registers a sensitivity excluding derived quarters, and a resolution that
    does not say whether its figure was derived cannot be sorted afterwards.
    """
    try:
        facts = fetch_quarterly_revenue(cik)
    except FetchError:
        return None

    cutoff = _parse_date(last_reported_end)
    if cutoff is None:
        return None

    later = [f for f in facts if f.end > cutoff]
    if not later:
        return None

    nxt = min(later, key=lambda f: f.end)
    if (nxt.end - cutoff).days > MAX_QUARTER_DAYS + 14:
        return None
    return {
        "outcome": 1.0 if nxt.value > threshold else 0.0,
        "period_end": nxt.end.isoformat(),
        "value": nxt.value,
        "threshold": threshold,
        "filed": nxt.filed.isoformat(),
        "fp": nxt.fp,
        "derived": nxt.fp == "Q4D",
        "accession": nxt.accession,
    }


def resolve_filing_task(
    cik: int, last_reported_end: str, threshold: float
) -> Optional[float]:
    """1.0 / 0.0 once the next quarter is filed, else None."""
    details = resolve_filing_task_details(cik, last_reported_end, threshold)
    return None if details is None else float(details["outcome"])


def build_universe_tasks(
    as_of: date,
    universe: Tuple[Tuple[str, int], ...] = DEFAULT_UNIVERSE,
    max_tasks: int = 12,
) -> List[Dict[str, Any]]:
    """Build filing-grounded tasks across the company universe."""
    out: List[Dict[str, Any]] = []
    for ticker, cik in universe:
        if len(out) >= max_tasks:
            break
        task = build_filing_task(ticker, cik, as_of)
        if task:
            out.append(task)
    return out

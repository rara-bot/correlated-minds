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

1. CONTAMINATION-PROOF BY CONSTRUCTION. The next quarter has not been filed, so
   no amount of pretraining can contain the answer.
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
    if len(history) < 6:
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
        "last_reported_value": latest.value,
        "last_filed": latest.filed.isoformat(),
        "source_ref": f"edgar:{cik}:{latest.end.isoformat()}",
    }


def resolve_filing_task(
    cik: int, last_reported_end: str, threshold: float
) -> Optional[float]:
    """1.0 / 0.0 once the next quarter is filed, else None.

    Strictly point-in-time: we look for a period that ENDS after the one the
    forecaster could see, and only count it once it has actually been filed.
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
    return 1.0 if nxt.value > threshold else 0.0


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

"""Philadelphia Fed Survey of Professional Forecasters -- the human baseline.

This module answers the question that makes every other number in the study
interpretable: **how correlated are the humans?**

Without it, reporting "mean pairwise error correlation is 0.71" tells a reader
nothing, because there is no scale. With it, the finding becomes "AI systems are
N times more redundant than the professional forecasters they are replacing" --
which is both the headline and the actual policy question the FSB, Bank of
England and IMF have posed.

VERIFIED 17 Aug 2026:
  - Individual-level microdata is public and free at SPFmicrodata.xlsx (~23 MB,
    64 sheets, quarterly rounds back to 1968, current through 2026 Q3).
  - Roughly 32-40 forecasters respond per round in recent years.
  - Sheets carry columns YEAR, QUARTER, ID, INDUSTRY, then <VAR>1..<VAR>6 for
    horizons 0-5 quarters ahead.
  - NOTE: the per-variable files (individual_cpi.xlsx etc.) return HTTP 200 with
    an HTML body, not a spreadsheet. Only the consolidated microdata file is real.

METHODOLOGICAL POINT -- why we subsample humans:

    N_eff = M / (1 + (M-1) * rho_bar)

depends on M. Comparing N_eff for 35 humans against N_eff for 7 AI models would
be meaningless: the human number is larger partly because there are more of them.
So we report two things:

  1. rho_bar directly. It is panel-size independent and is the honest primary
     comparison.
  2. N_eff for humans SUBSAMPLED TO THE AI PANEL SIZE, averaged over many random
     subsets. This is the like-for-like headline number.

Reporting only (2) without (1) would invite the objection that the result is a
panel-size artifact. Reporting both closes it.

PINNED INPUTS (PREREGISTRATION.md 11, deviation 19):

The benchmark is computed from data/spf/, never from a fresh download. The
Philadelphia Fed replaces SPFmicrodata.xlsx with every quarterly survey and FRED
serves only the latest vintage of a series, so a benchmark recomputed later -- at
the surviving panel size, on the squared-error scale, at matched accuracy -- would
silently rest on different data from the numbers registered in 2.3. The pin holds
the five sheets this module reads (rows from 2000) and FRED's CSV for the four
series they are scored against, written by scripts/pin_spf_inputs.py;
PROVENANCE.json records where each came from and its SHA-256, and
`pinned_problems()` checks them. `source="live"` reads the workbook and FRED
instead, for comparison only.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import DATA_DIR, primary_panel
from ..stats import mean_pairwise_correlation, n_eff
from .http import FetchError

MICRODATA_URL = (
    "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/"
    "survey-of-professional-forecasters/historical-data/SPFmicrodata.xlsx"
)

CACHE_PATH = DATA_DIR / "spf_raw" / "SPFmicrodata.xlsx"

PINNED_DIR = DATA_DIR / "spf"
PROVENANCE_PATH = PINNED_DIR / "PROVENANCE.json"
PINNED_MIN_YEAR = 2000
SOURCES = ("pinned", "live")

# SPF sheet -> (FRED series, how to aggregate, WHAT THE SPF COLUMN ACTUALLY IS)
#
# !! CORRECTED 17 Aug 2026, BEFORE FREEZE. The previous version of this table
#    compared every SPF column to a FRED LEVEL, which is only correct for UNEMP.
#    Measured damage on the 2000+ sample:
#
#      CPI  h=1 : median |error| 229.07   rho_bar 1.0000   (SPF reports an
#                 annualised inflation RATE ~2.7%; CPIAUCSL is an index ~333)
#      RGDP h=1 : median |error| 3488.46  rho_bar 1.0000   (SPF levels are in the
#                 chain base current at survey time; GDPC1 is 2017 dollars)
#
#    Both produced rho_bar = 1.0000 -- a perfect correlation manufactured
#    entirely by a units mismatch, in the numbers that set this study's human
#    benchmark. Corrected, CPI h=4 headroom moves from 0.0047 to 0.0797: a 17x
#    change in a quantity that appears in the denominator of the headline.
#
# unit semantics:
#   "level"  -- SPF column is the same object as the FRED series (UNEMP only)
#   "growth" -- SPF column is a level in a drifting chain base; the base cancels
#               in the annualised quarter-on-quarter growth rate, so we compare
#               growth to growth
#   "rate"   -- SPF column is ALREADY an annualised percent change; build the
#               same object from the FRED index
VARIABLE_MAP = {
    "UNEMP": ("UNRATE", "quarterly_mean", "level"),
    "CPI": ("CPIAUCSL", "quarterly_mean", "rate"),
    "EMP": ("PAYEMS", "quarterly_mean", "growth"),
    "RGDP": ("GDPC1", "quarterly_level", "growth"),
}

# Individual probability forecasts of a BINARY event. Structurally identical to
# the AI task (a probability in [0,1], an outcome in {0,1}, error = p - y), which
# is what makes H4 an apples-to-apples comparison rather than a comparison
# between binary probabilities and continuous point forecasts.
RECESS_SHEET = "RECESS"
RECESS_OUTCOME_SERIES = "GDPC1"

# What the pin holds: every sheet this module reads, with the columns it reads,
# and every FRED series those sheets are scored against.
PINNED_SHEETS = {
    RECESS_SHEET: [f"{RECESS_SHEET}{h}" for h in range(1, 6)],
    **{variable: [f"{variable}{h}" for h in range(1, 7)] for variable in VARIABLE_MAP},
}
PINNED_SERIES = sorted(
    {series for series, _, _ in VARIABLE_MAP.values()} | {RECESS_OUTCOME_SERIES}
)


@dataclass
class HumanBaseline:
    """Result of measuring independence among human forecasters."""

    variable: str
    horizon: int
    n_rounds: int
    n_forecasters_median: float
    rho_bar: float
    n_eff_full_panel: float
    n_eff_matched: float          # subsampled to the AI panel size
    matched_panel_size: int
    n_eff_matched_ci: Tuple[float, float]


@dataclass
class HumanErrors:
    """One sheet at one horizon, as the estimator sees it.

    `errors` is rounds x forecasters, forecast minus outcome, NaN where a
    forecaster did not answer. Only rounds with a published outcome are kept.
    `rounds` labels the rows as (year, quarter); `ids` labels the columns.
    """

    variable: str
    horizon: int
    errors: np.ndarray
    forecasts: np.ndarray
    outcomes: np.ndarray
    rounds: List[Tuple[int, int]]
    ids: List[int]


def download_microdata(force: bool = False) -> Path:
    """Fetch and cache the SPF microdata workbook (~23 MB)."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CACHE_PATH.exists() and not force and CACHE_PATH.stat().st_size > 1_000_000:
        return CACHE_PATH

    import httpx

    from ..config import USER_AGENT

    with httpx.stream(
        "GET",
        MICRODATA_URL,
        params={"sc_lang": "en"},
        headers={"User-Agent": USER_AGENT},
        timeout=180.0,
        follow_redirects=True,
    ) as response:
        if response.status_code != 200:
            raise FetchError(f"SPF microdata -> HTTP {response.status_code}")
        tmp = CACHE_PATH.with_suffix(".part")
        with tmp.open("wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)
        tmp.replace(CACHE_PATH)

    # The per-variable SPF URLs return HTML with a 200; verify we got a real
    # workbook rather than trusting the status code.
    with CACHE_PATH.open("rb") as fh:
        if fh.read(2) != b"PK":
            CACHE_PATH.unlink(missing_ok=True)
            raise FetchError("SPF microdata: got a non-xlsx body (likely an HTML page)")

    return CACHE_PATH


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned_problems() -> List[str]:
    """Everything wrong with the pinned inputs. An empty list means intact."""
    if not PROVENANCE_PATH.exists():
        return [f"{PROVENANCE_PATH} is missing"]
    record = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    entries = list(record.get("spf_sheets", {}).values()) + list(
        record.get("fred_series", {}).values()
    )
    expected = {f"{sheet}.csv" for sheet in PINNED_SHEETS} | {
        f"fred_{series}.csv" for series in PINNED_SERIES
    }
    problems: List[str] = []
    if {entry["file"] for entry in entries} != expected:
        problems.append("PROVENANCE.json does not list exactly the files this module reads")
    for entry in entries:
        path = PINNED_DIR / entry["file"]
        if not path.exists():
            problems.append(f"{entry['file']} is missing")
        elif _sha256(path) != entry["sha256"]:
            problems.append(f"{entry['file']} does not match its recorded SHA-256")
    return problems


def _check_source(source: str) -> None:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, not {source!r}")


def load_variable(
    variable: str, path: Optional[Path] = None, source: str = "pinned"
) -> pd.DataFrame:
    """Load one SPF sheet as a tidy frame: the pinned extract, or a workbook if live."""
    _check_source(source)
    if source == "pinned":
        if path is not None:
            raise ValueError("a workbook path is live data: pass source='live'")
        frame = pd.read_csv(PINNED_DIR / f"{variable}.csv")
    else:
        frame = pd.read_excel(Path(path) if path else download_microdata(), sheet_name=variable)
    frame.columns = [str(c).strip().upper() for c in frame.columns]
    required = {"YEAR", "QUARTER", "ID"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"SPF sheet {variable!r} missing columns: {sorted(missing)}")
    return frame


def series_history(series_id: str, source: str = "pinned") -> List[Tuple]:
    """A FRED series as (date, value) pairs: the pinned CSV, or FRED itself if live."""
    from . import fred

    _check_source(source)
    if source == "live":
        return fred.fetch_series(series_id)
    text = (PINNED_DIR / f"fred_{series_id}.csv").read_text(encoding="utf-8")
    return fred.parse_series_csv(text, series_id)


def target_quarter(year: int, quarter: int, horizon: int) -> Tuple[int, int]:
    """The quarter a forecast at `horizon` is about: h = 1 is the survey quarter.

    Getting this offset wrong would manufacture error the forecasters never made
    and inflate every correlation.
    """
    index = quarter + (horizon - 1)
    return year + (index - 1) // 4, (index - 1) % 4 + 1


def forecast_matrix(
    frame: pd.DataFrame,
    variable: str,
    horizon: int = 1,
    min_year: int = 2000,
    min_forecasters: int = 8,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[int]]:
    """Build a (rounds x forecasters) matrix of point forecasts.

    Args:
        horizon: 1 = current quarter (nowcast) ... 6 = five quarters ahead.
        min_year: recent rounds only. The panel composition and the forecasting
            environment both change enormously over 50 years, and we want a
            comparison to how humans forecast *now*.
        min_forecasters: drop thin rounds.

    Returns:
        (matrix with NaN for non-response, round labels, forecaster ids)
    """
    column = f"{variable}{horizon}"
    if column not in frame.columns:
        raise ValueError(f"column {column!r} not in sheet (have {list(frame.columns)})")

    recent = frame[frame["YEAR"] >= min_year][["YEAR", "QUARTER", "ID", column]].copy()
    recent[column] = pd.to_numeric(recent[column], errors="coerce")
    recent = recent.dropna(subset=[column])

    # Keep forecasters who appear often enough to estimate a correlation with.
    counts = recent["ID"].value_counts()
    keep_ids = sorted(counts[counts >= 12].index.tolist())
    recent = recent[recent["ID"].isin(keep_ids)]

    pivot = recent.pivot_table(
        index=["YEAR", "QUARTER"], columns="ID", values=column, aggfunc="first"
    )
    pivot = pivot[pivot.notna().sum(axis=1) >= min_forecasters]

    rounds = [(int(y), int(q)) for y, q in pivot.index]
    return pivot.to_numpy(dtype=float), rounds, [int(i) for i in pivot.columns]


def realized_outcomes(
    variable: str, rounds: List[Tuple[int, int]], horizon: int = 1, source: str = "pinned"
) -> np.ndarray:
    """Realized value each round was forecasting, from FRED.

    Horizon h in the SPF means h-1 quarters ahead of the survey quarter
    (`target_quarter`). A quarter whose months are not all published yet has no
    outcome (`fred.quarterly_average`).
    """
    from . import fred

    series_id, mode, units = VARIABLE_MAP[variable]
    history = series_history(series_id, source)

    def _value(year: int, quarter: int) -> Optional[float]:
        if mode == "quarterly_mean":
            return fred.quarterly_average(series_id, year, quarter, series=history)
        month = 3 * (quarter - 1) + 1
        return next(
            (
                v
                for d, v in history
                if d.year == year and d.month == month and v is not None
            ),
            None,
        )

    outcomes = np.full(len(rounds), np.nan, dtype=float)
    for i, (year, quarter) in enumerate(rounds):
        target_y, target_q = target_quarter(year, quarter, horizon)

        if units == "level":
            value = _value(target_y, target_q)
        else:
            # Both "rate" and "growth" compare an annualised quarter-on-quarter
            # percent change, which is invariant to the index base.
            prev_q, prev_y = (target_q - 1, target_y) if target_q > 1 else (4, target_y - 1)
            current, previous = _value(target_y, target_q), _value(prev_y, prev_q)
            value = (
                ((current / previous) ** 4 - 1) * 100
                if current is not None and previous not in (None, 0)
                else None
            )
        if value is not None:
            outcomes[i] = value

    return outcomes


def growth_matrix(
    frame: pd.DataFrame,
    variable: str,
    horizon: int,
    min_year: int = 2000,
    min_forecasters: int = 8,
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[int]]:
    """Annualised growth implied by each forecaster's OWN consecutive levels.

    For "growth" variables the SPF column is a level denominated in whatever
    chain base was current at survey time. Differencing two horizons from the
    SAME respondent cancels that base exactly, which is why growth is the only
    base-safe way to score these series against a modern FRED vintage.
    """
    if horizon < 2:
        raise ValueError("growth needs horizon >= 2 (it differences h-1 and h)")

    hi, lo = f"{variable}{horizon}", f"{variable}{horizon - 1}"
    for column in (hi, lo):
        if column not in frame.columns:
            raise ValueError(f"column {column!r} not in sheet")

    recent = frame[frame["YEAR"] >= min_year][["YEAR", "QUARTER", "ID", hi, lo]].copy()
    for column in (hi, lo):
        recent[column] = pd.to_numeric(recent[column], errors="coerce")
    recent = recent.dropna(subset=[hi, lo])
    recent = recent[recent[lo] > 0]
    recent["_g"] = ((recent[hi] / recent[lo]) ** 4 - 1) * 100

    counts = recent["ID"].value_counts()
    recent = recent[recent["ID"].isin(counts[counts >= 12].index)]

    pivot = recent.pivot_table(
        index=["YEAR", "QUARTER"], columns="ID", values="_g", aggfunc="first"
    )
    pivot = pivot[pivot.notna().sum(axis=1) >= min_forecasters]
    rounds = [(int(y), int(q)) for y, q in pivot.index]
    return pivot.to_numpy(dtype=float), rounds, [int(i) for i in pivot.columns]


def human_errors(
    variable: str,
    horizon: int = 1,
    min_year: int = 2000,
    min_forecasters: int = 8,
    source: str = "pinned",
    path: Optional[Path] = None,
) -> HumanErrors:
    """The error matrix behind every human number: each forecast minus what happened.

    For RECESS the forecasts are probabilities and the outcomes 0 or 1, the object
    the models produce. H4 needs the matrix, not only the summary `measure_binary`
    returns: 5.5 makes the headline a difference in variance reduction on the
    squared-error scale, and H4's confirmatory form matches the panels on accuracy.
    """
    if source == "pinned" and min_year < PINNED_MIN_YEAR:
        raise ValueError(f"the pinned extract starts in {PINNED_MIN_YEAR}")
    frame = load_variable(variable, path=path, source=source)
    if variable == RECESS_SHEET:
        forecasts, rounds, ids = recess_matrix(frame, horizon, min_year, min_forecasters)
        outcomes = decline_outcomes(
            rounds, horizon, series_history(RECESS_OUTCOME_SERIES, source)
        )
    else:
        build = growth_matrix if VARIABLE_MAP[variable][2] == "growth" else forecast_matrix
        forecasts, rounds, ids = build(
            frame, variable, horizon=horizon, min_year=min_year, min_forecasters=min_forecasters
        )
        outcomes = realized_outcomes(variable, rounds, horizon=horizon, source=source)

    usable = ~np.isnan(outcomes)
    forecasts, outcomes = forecasts[usable], outcomes[usable]
    return HumanErrors(
        variable=variable,
        horizon=horizon,
        errors=forecasts - outcomes[:, None],
        forecasts=forecasts,
        outcomes=outcomes,
        rounds=[r for r, keep in zip(rounds, usable) if keep],
        ids=ids,
    )


def _matched(
    errors: np.ndarray, panel_size: int, n_subsamples: int, seed: int
) -> Tuple[float, Tuple[float, float]]:
    """Mean N_eff over random panels of `panel_size` forecasters, and its 95% range.

    Like-for-like: the human number is not inflated by panel size alone.
    """
    full_n = int(errors.shape[1])
    rng = np.random.default_rng(seed)
    draws: List[float] = []
    if full_n >= panel_size:
        for _ in range(n_subsamples):
            picks = rng.choice(full_n, size=panel_size, replace=False)
            sub_rho = mean_pairwise_correlation(errors[:, picks], min_overlap=6)
            if np.isfinite(sub_rho):
                draws.append(n_eff(sub_rho, panel_size))
    if not draws:
        return float("nan"), (float("nan"), float("nan"))
    return float(np.mean(draws)), (
        float(np.percentile(draws, 2.5)),
        float(np.percentile(draws, 97.5)),
    )


def _baseline(
    human: HumanErrors, panel_size: int, n_subsamples: int, seed: int
) -> HumanBaseline:
    errors = human.errors
    if errors.shape[0] < 8:
        raise ValueError(
            f"only {errors.shape[0]} usable rounds for {human.variable} h{human.horizon}"
        )
    rho_bar = mean_pairwise_correlation(errors, min_overlap=6)
    matched, ci = _matched(errors, panel_size, n_subsamples, seed)
    return HumanBaseline(
        variable=human.variable,
        horizon=human.horizon,
        n_rounds=int(errors.shape[0]),
        n_forecasters_median=float(np.median(np.sum(~np.isnan(human.forecasts), axis=1))),
        rho_bar=float(rho_bar),
        n_eff_full_panel=float(n_eff(rho_bar, int(errors.shape[1]))),
        n_eff_matched=matched,
        matched_panel_size=panel_size,
        n_eff_matched_ci=ci,
    )


def measure(
    variable: str = "UNEMP",
    horizon: int = 1,
    min_year: int = 2000,
    matched_panel_size: Optional[int] = None,
    n_subsamples: int = 500,
    seed: int = 0,
    source: str = "pinned",
    path: Optional[Path] = None,
) -> HumanBaseline:
    """Measure effective independence among human professional forecasters.

    Uses the identical estimator applied to the AI panel, so the two numbers are
    directly comparable by construction rather than by argument. The matched
    panel defaults to the registered primary panel's size; H4 passes the surviving
    M instead if 5.6 removes a model (deviation 17).
    """
    panel_size = matched_panel_size or len(primary_panel())
    human = human_errors(variable, horizon, min_year, source=source, path=path)
    return _baseline(human, panel_size, n_subsamples, seed)


def measure_all(
    variables: Optional[List[str]] = None, horizon: int = 1, **kwargs
) -> Dict[str, HumanBaseline]:
    """Baseline for each variable the AI panel also forecasts."""
    targets = variables or ["UNEMP", "CPI", "EMP", "RGDP"]
    out: Dict[str, HumanBaseline] = {}
    for variable in targets:
        try:
            out[variable] = measure(variable, horizon=horizon, **kwargs)
        except Exception as exc:                       # noqa: BLE001
            print(f"  [skip] {variable}: {type(exc).__name__}: {exc}")
    return out


# ---------------------------------------------------------------------------
# THE STRUCTURALLY MATCHED HUMAN BENCHMARK
#
# Added 17 Aug 2026, before collection. H4 compares human and AI diversification
# headroom. The point-forecast baselines above are a comparison between two
# different objects: our models emit a PROBABILITY of a BINARY event (error
# p - y, y in {0,1}), while SPF point forecasts are continuous levels. Headroom
# is approximately tau^2 / (sigma_c^2 + tau^2) -- the share of error variance
# that is idiosyncratic -- and the mechanical floor of sigma_c^2 differs between
# a Bernoulli outcome and a continuous one. Comparing across that gap invites
# the obvious objection that the headline result is a task-format artifact.
#
# RECESS closes it. Every quarter since 1968 the SPF asks each panelist for the
# probability that real GDP will DECLINE in the survey quarter and in each of the
# next four. That is a probability forecast of a binary event, at the individual
# level, resolved by the national accounts: the same object our models produce,
# scored the same way, by the professionals they are said to replace.
#
# Registered in PREREGISTRATION.md 2.3 (2000+, 106 rounds at h=1, 13% base rate)
# and reproduced to every printed digit from the pinned inputs by
# tests/test_spf.py:
#     h=1  rho_bar 0.8417   headroom@M=9 0.1710   [0.076, 0.356]
#     h=4  rho_bar 0.8906   headroom@M=9 0.1222   [0.028, 0.311]
# ---------------------------------------------------------------------------


def _gdp_declined(series: List[Tuple], year: int, quarter: int) -> Optional[float]:
    """1.0 if real GDP fell that quarter versus the previous one."""
    levels = {(d.year, (d.month - 1) // 3 + 1): v for d, v in series if v is not None}
    prev_q, prev_y = (quarter - 1, year) if quarter > 1 else (4, year - 1)
    current, previous = levels.get((year, quarter)), levels.get((prev_y, prev_q))
    if current is None or previous is None:
        return None
    return float(current < previous)


def recess_matrix(
    frame: pd.DataFrame, horizon: int = 1, min_year: int = 2000, min_forecasters: int = 8
) -> Tuple[np.ndarray, List[Tuple[int, int]], List[int]]:
    """(rounds x forecasters) matrix of RECESS probabilities, in [0, 1]."""
    column = f"{RECESS_SHEET}{horizon}"
    if column not in frame.columns:
        raise ValueError(f"column {column!r} not in RECESS sheet")

    recent = frame[frame["YEAR"] >= min_year][["YEAR", "QUARTER", "ID", column]].copy()
    recent[column] = pd.to_numeric(recent[column], errors="coerce")
    recent = recent.dropna(subset=[column])

    counts = recent["ID"].value_counts()
    recent = recent[recent["ID"].isin(counts[counts >= 12].index)]

    pivot = recent.pivot_table(
        index=["YEAR", "QUARTER"], columns="ID", values=column, aggfunc="first"
    )
    pivot = pivot[pivot.notna().sum(axis=1) >= min_forecasters]

    rounds = [(int(y), int(q)) for y, q in pivot.index]
    # SPF records these as percentages; our models emit probabilities.
    return pivot.to_numpy(dtype=float) / 100.0, rounds, [int(i) for i in pivot.columns]


def decline_outcomes(
    rounds: List[Tuple[int, int]], horizon: int, history: List[Tuple]
) -> np.ndarray:
    """1.0 where real GDP fell in the quarter a round forecast, NaN if unpublished."""
    outcomes = np.full(len(rounds), np.nan, dtype=float)
    for i, (year, quarter) in enumerate(rounds):
        value = _gdp_declined(history, *target_quarter(year, quarter, horizon))
        if value is not None:
            outcomes[i] = value
    return outcomes


def measure_binary(
    horizon: int = 1,
    min_year: int = 2000,
    matched_panel_size: Optional[int] = None,
    n_subsamples: int = 500,
    seed: int = 0,
    source: str = "pinned",
    path: Optional[Path] = None,
    min_forecasters: int = 8,
) -> HumanBaseline:
    """Human independence on PROBABILITY forecasts of a BINARY event (SPF RECESS).

    This is the primary human benchmark for H4, because it is the only public
    human panel that produces the same kind of object our models produce.

    horizon: 1 = probability of decline in the survey quarter ... 5 = four
        quarters ahead.
    """
    panel_size = matched_panel_size or len(primary_panel())
    human = human_errors(RECESS_SHEET, horizon, min_year, min_forecasters, source=source, path=path)
    return _baseline(human, panel_size, n_subsamples, seed)

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
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import DATA_DIR
from ..stats import mean_pairwise_correlation, n_eff
from .http import FetchError, get_text

MICRODATA_URL = (
    "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/"
    "survey-of-professional-forecasters/historical-data/SPFmicrodata.xlsx"
)

CACHE_PATH = DATA_DIR / "spf_raw" / "SPFmicrodata.xlsx"

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


def load_variable(variable: str, path: Optional[Path] = None) -> pd.DataFrame:
    """Load one SPF sheet as a tidy frame."""
    source = Path(path) if path else download_microdata()
    frame = pd.read_excel(source, sheet_name=variable)
    frame.columns = [str(c).strip().upper() for c in frame.columns]
    required = {"YEAR", "QUARTER", "ID"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"SPF sheet {variable!r} missing columns: {sorted(missing)}")
    return frame


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
    variable: str, rounds: List[Tuple[int, int]], horizon: int = 1
) -> np.ndarray:
    """Realized value each round was forecasting, from FRED.

    Horizon h in the SPF means h-1 quarters ahead of the survey quarter, so we
    advance the target quarter accordingly. Getting this offset wrong would
    manufacture error the forecasters never made and inflate every correlation.
    """
    from . import fred

    series_id, mode, units = VARIABLE_MAP[variable]
    history = fred.fetch_series(series_id)

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
        target_q = quarter + (horizon - 1)
        target_y = year + (target_q - 1) // 4
        target_q = ((target_q - 1) % 4) + 1

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


def measure(
    variable: str = "UNEMP",
    horizon: int = 1,
    min_year: int = 2000,
    matched_panel_size: int = 7,
    n_subsamples: int = 500,
    seed: int = 0,
    path: Optional[Path] = None,
) -> HumanBaseline:
    """Measure effective independence among human professional forecasters.

    Uses the identical estimator applied to the AI panel, so the two numbers are
    directly comparable by construction rather than by argument.
    """
    frame = load_variable(variable, path=path)
    units = VARIABLE_MAP[variable][2]
    if units == "growth":
        forecasts, rounds, ids = growth_matrix(
            frame, variable, horizon=horizon, min_year=min_year
        )
    else:
        forecasts, rounds, ids = forecast_matrix(
            frame, variable, horizon=horizon, min_year=min_year
        )
    outcomes = realized_outcomes(variable, rounds, horizon=horizon)

    usable = ~np.isnan(outcomes)
    forecasts, outcomes = forecasts[usable], outcomes[usable]
    if forecasts.shape[0] < 8:
        raise ValueError(
            f"only {forecasts.shape[0]} usable rounds for {variable} h{horizon}"
        )

    errors = forecasts - outcomes[:, None]

    rho_bar = mean_pairwise_correlation(errors, min_overlap=6)
    full_n = int(errors.shape[1])
    n_eff_full = n_eff(rho_bar, full_n)

    # Like-for-like: repeatedly draw `matched_panel_size` forecasters at random
    # and recompute, so the human number is not inflated by panel size alone.
    rng = np.random.default_rng(seed)
    draws: List[float] = []
    if full_n >= matched_panel_size:
        for _ in range(n_subsamples):
            picks = rng.choice(full_n, size=matched_panel_size, replace=False)
            subset = errors[:, picks]
            sub_rho = mean_pairwise_correlation(subset, min_overlap=6)
            if np.isfinite(sub_rho):
                draws.append(n_eff(sub_rho, matched_panel_size))

    if draws:
        matched = float(np.mean(draws))
        ci = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
    else:
        matched, ci = float("nan"), (float("nan"), float("nan"))

    per_round = np.sum(~np.isnan(forecasts), axis=1)

    return HumanBaseline(
        variable=variable,
        horizon=horizon,
        n_rounds=int(forecasts.shape[0]),
        n_forecasters_median=float(np.median(per_round)),
        rho_bar=float(rho_bar),
        n_eff_full_panel=float(n_eff_full),
        n_eff_matched=matched,
        matched_panel_size=matched_panel_size,
        n_eff_matched_ci=ci,
    )


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
# Measured on 2000+ (106 rounds, 79 forecasters, 13% base rate):
#     h=1  rho_bar 0.8417   headroom@M=7 0.1702
#     h=4  rho_bar 0.8906   headroom@M=7 0.1153
# ---------------------------------------------------------------------------


def _gdp_declined(series: List[Tuple], year: int, quarter: int) -> Optional[float]:
    """1.0 if real GDP fell that quarter versus the previous one."""
    levels = {(d.year, (d.month - 1) // 3 + 1): v for d, v in series if v is not None}
    prev_q, prev_y = (quarter - 1, year) if quarter > 1 else (4, year - 1)
    current, previous = levels.get((year, quarter)), levels.get((prev_y, prev_q))
    if current is None or previous is None:
        return None
    return float(current < previous)


def measure_binary(
    horizon: int = 1,
    min_year: int = 2000,
    matched_panel_size: int = 7,
    n_subsamples: int = 500,
    seed: int = 0,
    path: Optional[Path] = None,
    min_forecasters: int = 8,
) -> HumanBaseline:
    """Human independence on PROBABILITY forecasts of a BINARY event (SPF RECESS).

    This is the primary human benchmark for H4, because it is the only public
    human panel that produces the same kind of object our models produce.

    horizon: 1 = probability of decline in the survey quarter ... 5 = four
        quarters ahead.
    """
    source = Path(path) if path else download_microdata()
    frame = pd.read_excel(source, sheet_name=RECESS_SHEET)
    frame.columns = [str(c).strip().upper() for c in frame.columns]

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
    forecasts = pivot.to_numpy(dtype=float) / 100.0

    from . import fred

    history = fred.fetch_series(RECESS_OUTCOME_SERIES)
    outcomes = np.full(len(rounds), np.nan, dtype=float)
    for i, (year, quarter) in enumerate(rounds):
        target_q = quarter + (horizon - 1)
        target_y = year + (target_q - 1) // 4
        target_q = ((target_q - 1) % 4) + 1
        value = _gdp_declined(history, target_y, target_q)
        if value is not None:
            outcomes[i] = value

    usable = ~np.isnan(outcomes)
    forecasts, outcomes = forecasts[usable], outcomes[usable]
    if forecasts.shape[0] < 8:
        raise ValueError(f"only {forecasts.shape[0]} usable RECESS rounds")

    errors = forecasts - outcomes[:, None]

    rho_bar = mean_pairwise_correlation(errors, min_overlap=6)
    full_n = int(errors.shape[1])

    rng = np.random.default_rng(seed)
    draws: List[float] = []
    if full_n >= matched_panel_size:
        for _ in range(n_subsamples):
            picks = rng.choice(full_n, size=matched_panel_size, replace=False)
            sub_rho = mean_pairwise_correlation(errors[:, picks], min_overlap=6)
            if np.isfinite(sub_rho):
                draws.append(n_eff(sub_rho, matched_panel_size))

    if draws:
        matched = float(np.mean(draws))
        ci = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
    else:
        matched, ci = float("nan"), (float("nan"), float("nan"))

    return HumanBaseline(
        variable="RECESS",
        horizon=horizon,
        n_rounds=int(forecasts.shape[0]),
        n_forecasters_median=float(np.median(np.sum(~np.isnan(forecasts), axis=1))),
        rho_bar=float(rho_bar),
        n_eff_full_panel=float(n_eff(rho_bar, full_n)),
        n_eff_matched=matched,
        matched_panel_size=matched_panel_size,
        n_eff_matched_ci=ci,
    )

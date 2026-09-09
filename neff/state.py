"""The three registered state variables that are DERIVED at analysis time.

PREREGISTRATION.md §4 registers seven state variables and says the count is the
Benjamini-Hochberg denominator. Four are written onto the task at ask time by
`tasks.py`. The other three were left to be derived later "from data already
retained" -- and until now none of them had any implementation at all.

That gap is not benign. Whoever wrote them in December would have been choosing
operationalisations for registered variables *while able to see whether the
choice helped H1*. Section 9 gives up exactly that freedom. So the definitions
are fixed here, on 2026-09-09, with five resolved task-days on the record and
the analysis driver still blind. Logged as PREREGISTRATION.md §11, deviation 8.

Registered semantics and predicted signs, from §4, which these must honour:

    expectation_dispersion  "the panel disagrees more"                 negative
    abs_surprise            "the release surprised consensus by more"  positive
    novelty_score           "resembles nothing in the accumulated corpus" positive

MISSING IS NaN, NEVER ZERO. A zero is a claim -- "this release did not surprise
anyone" -- and an unavailable consensus is not that claim. Zero-filling would
also drag every standardised coefficient toward the fill value. §11 deviation 8
registers complete-case handling with coverage reported.
"""

import math
import re
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

# Question text sits between these markers in the prompts `tasks.py` builds.
_QUESTION_START = "--- QUESTION ---"
# Section markers look like `--- MARKET CONTEXT (as of today) ---`: the
# parenthetical is lower case, so a rule demanding upper case throughout
# silently matches nothing and leaves the market block inside the question.
# That inflates every pair's similarity through shared boilerplate and
# drives novelty toward zero for questions that share nothing at all.
_SECTION = re.compile(r"^-{2,}\s*[A-Z][A-Za-z ()\-]*\s*-{2,}\s*$", re.MULTILINE)
_TOKEN = re.compile(r"[a-z0-9.]+")


# --- expectation_dispersion --------------------------------------------------

def expectation_dispersion(forecasts: np.ndarray, min_models: int = 2) -> np.ndarray:
    """Cross-model dispersion of the panel's own forecasts, one value per task.

    Population standard deviation across the models that answered, computed
    pairwise-complete: a model that failed leaves a NaN and is skipped, rather
    than dropping the whole task. `panel.load_panel` keeps failures as NaN
    precisely so estimators can do this.

    §4 flags this variable as DESCRIPTIVE, NOT EVIDENTIAL and the docstring
    repeats it because the number is easy to over-read: with
    `rho ~ sigma_c^2 / (sigma_c^2 + tau^2)`, cross-model dispersion *is* `tau^2`,
    so it is close to a transform of the dependent variable and moves in the
    registered direction almost mechanically. It is retained because §9 fixes
    the seven and the count sets the BH denominator -- not because it can
    support H1.
    """
    arr = np.asarray(forecasts, dtype=float)
    if arr.ndim != 2:
        raise ValueError("forecasts must be (n_tasks, n_models)")
    out = np.full(arr.shape[0], np.nan)
    for i, row in enumerate(arr):
        vals = row[~np.isnan(row)]
        if vals.size >= min_models:
            out[i] = float(np.std(vals))       # population SD; the panel is the population
    return out


# --- novelty_score -----------------------------------------------------------

def question_text(task: Dict) -> str:
    """The question itself, without the prompt scaffolding.

    Every prompt carries the same JSON-schema instructions and the same market
    context block. Comparing whole prompts would score every pair as nearly
    identical and make novelty a constant.
    """
    prompt = str(task.get("prompt") or "")
    if _QUESTION_START in prompt:
        tail = prompt.split(_QUESTION_START, 1)[1]
        parts = _SECTION.split(tail)
        return parts[0].strip() if parts else tail.strip()
    # Filing tasks are assembled from title/context/rules rather than a ladder.
    for key in ("title", "context", "rules"):
        if task.get(key):
            return " ".join(str(task.get(k) or "") for k in ("title", "rules")).strip()
    return prompt.strip()


# The ask date is stamped into every prompt as "Today's date: ...". It is not
# part of what is being asked, and leaving it in makes a question look slightly
# unlike its own earlier self purely because the calendar moved -- so a re-asked
# question would never score 0 and its novelty would drift with the date rather
# than with the corpus. The RESOLUTION date is deliberately kept: a CPI question
# settling in September is a different question from one settling in November.
_VOLATILE_LINE = re.compile(r"^\s*Today's date:.*$", re.MULTILINE | re.IGNORECASE)


def _tokens(text: str) -> frozenset:
    return frozenset(_TOKEN.findall(_VOLATILE_LINE.sub("", text).lower()))


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def novelty_scores(tasks: Sequence[Dict]) -> Dict[str, float]:
    """`1 - max Jaccard` against every task asked on a STRICTLY EARLIER day.

    Registered reading: "the question resembles nothing in the accumulated
    corpus", higher = more novel, predicted sign positive.

    Three choices, fixed here rather than in December:

    1. LEXICAL, NOT EMBEDDINGS. §5.4 already refused embedding-based rationale
       similarity as exploratory-only, because doing it honestly needs a
       validation study of the embeddings themselves. Using embeddings here
       while refusing them there would be incoherent. Jaccard over word tokens
       needs no model, no API and no seed, and recomputes identically forever.

    2. STRICTLY EARLIER DAYS, never the same day. The corpus a question is novel
       against is the one that existed when it was asked. Comparing within a day
       would make the score depend on the order tasks happen to sit in the file,
       which is not a property of the question.

    3. A QUESTION ASKED AGAIN IS NOT NOVEL. `tasks.py` re-asks open questions
       daily, so from its second day a question scores near 0. That is the
       intended reading: on day 12 it resembles something in the corpus -- itself.

    The first day of collection has no earlier corpus, so every task that day
    scores 1.0. That is correct, not a boundary bug, and it is why the score is
    standardised across the study rather than read as a level.
    """
    dated: List[tuple] = []
    for t in tasks:
        day = str((t.get("state") or {}).get("asked_on") or "")
        tid = str(t.get("task_id") or "")
        if day and tid:
            dated.append((day, tid, _tokens(question_text(t))))
    dated.sort(key=lambda r: r[0])

    out: Dict[str, float] = {}
    seen_by_day: Dict[str, List[frozenset]] = {}
    for day, tid, toks in dated:
        seen_by_day.setdefault(day, []).append(toks)

    corpus: List[frozenset] = []
    for day in sorted(seen_by_day):
        for _, tid, toks in [r for r in dated if r[0] == day]:
            best = max((_jaccard(toks, prior) for prior in corpus), default=0.0)
            out[tid] = 1.0 - best
        corpus.extend(seen_by_day[day])          # only after the whole day scores
    return out


# --- abs_surprise ------------------------------------------------------------

def standardised_surprise(
    realized: Optional[float], consensus: Optional[float], scale: Optional[float]
) -> float:
    """|realized - consensus| / scale, or NaN when any part is unavailable.

    §4 reads this as "the release surprised consensus by more", predicted sign
    positive, so it needs BOTH sides: a realized value and what was expected.
    The realized side comes from FRED vintages -- the value as first published,
    not as later revised, because a forecaster could not have been surprised by
    a revision that had not happened yet.

    `scale` makes releases comparable: a 0.2pp CPI miss and a 40k payrolls miss
    are not the same number but may be the same surprise. It is the historical
    standard deviation of (realized - consensus) for that series, so the result
    is in units of "typical surprise for this release".

    RETURNS NaN, NOT ZERO, when anything is missing. Zero asserts the release
    landed exactly on consensus, which is a strong empirical claim and not one
    an absent data source is entitled to make.
    """
    for v in (realized, consensus, scale):
        if v is None or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            return float("nan")
    if float(scale) <= 0:
        return float("nan")
    return abs(float(realized) - float(consensus)) / float(scale)


def coverage(values: Iterable[float]) -> float:
    """Fraction of a derived variable that is actually defined.

    Reported wherever the variable is used. A state variable covering 30% of
    task-days is not the same evidence as one covering 100%, and complete-case
    regression silently hides the difference unless the number is stated.
    """
    arr = np.asarray(list(values), dtype=float)
    return float(np.sum(~np.isnan(arr)) / arr.size) if arr.size else 0.0


def complete_cases(columns: Dict[str, np.ndarray]) -> np.ndarray:
    """Row mask where EVERY named state variable is defined.

    §11 deviation 8 registers complete-case handling for the H1 regression, with
    coverage reported alongside. The alternative -- imputing a missing state --
    invents the very quantity the regression is asking about.
    """
    if not columns:
        return np.zeros(0, dtype=bool)
    stacked = np.vstack([np.asarray(c, dtype=float) for c in columns.values()])
    return ~np.any(np.isnan(stacked), axis=0)

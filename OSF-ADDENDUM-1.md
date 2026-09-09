# OSF addendum 1 — ready to paste

**Three steps. Two pastes and one upload. Roughly twenty minutes.**

| Step | Where | What |
|---|---|---|
| 1 | Zenodo — DOI `10.5281/zenodo.22220263` → **New version** | **Upload** `OSF-ADDENDUM-1.md` (this file) and `PREREGISTRATION.md`, then Publish |
| 2 | Your OSF **project** (not the frozen registration) | **Upload** the same two files, then **paste** the wiki entry at the end of this file |
| 3 | osf.io/x6kqg — only if it offers an update option | **Paste** the title and body below |

**Do not withdraw the registration.** Its immutability is the asset. Steps 1 and
2 put the record beside it; they do not touch it.

This reports a specification error we found in our own registered analysis plan,
and what we are doing about it. It does **not** revise the registered analysis.

| | |
|---|---|
| Registration | osf.io/x6kqg, registered 2026-08-29 14:44 UTC |
| Plan frozen | 2026-08-29 03:54 UTC |
| Registered SHA-256 | `90a7e7de5980a80bef786e87b938495d7a08e10234032a11c5d67e8ce1c70009` |
| Addendum date | 2026-09-09 |
| Also recorded at | PREREGISTRATION.md §11, deviations 5 and 6 |

**Why now:** posting this while the outcomes it could affect do not yet exist is
the whole of its value. Eight collection days exist and five resolved task-days
enter the primary panel. The code that computes the primary estimate
(`neff/analysis.py`) did not exist before 2026-09-09 and is blind by default, so
that it has only ever been run on permuted outcomes is checkable in the commit
history rather than asserted. In November the same disclosure would be
unfalsifiable.

---

## Paste below this line

### Title of update

```
Addendum 1: a specification error in the §5.2 event-clustered interval, and a qualification to the §6 stress-leg power rationale — both found before any primary estimate was computed
```

### Body

```
WHAT WE FOUND

Section 5.2 of the registered plan requires two confidence intervals for every
primary estimate, reported together: a day-blocked moving-block bootstrap, and a
cluster bootstrap over resolution events. It designates the second as the
conservative bound and states that where the two disagree materially, the
event-clustered interval governs the claim.

Section 5.2 justifies that second interval as follows:

    "Many questions share one underlying resolution event -- every strike on a
    CPI ladder settles against a single print and therefore shares a single
    surprise"

and then operationalises it as "all task-days of all questions sharing a
source_ref".

Those two are not the same grouping, and we did not notice at freeze time.

A Kalshi ticker has the form SERIES-EXPIRY-STRIKE. The source_ref therefore
CONTAINS the strike. Grouping on it splits the very ladder the justifying
sentence names back into one cluster per rung -- the opposite of what the
sentence describes.

Measured on the 241 tasks collected through 2026-09-08: 80 distinct source_refs
against 40 distinct settlements. A concrete instance already in the public
record: the five KXAAAGASWNJ-26SEP07 rungs at thresholds 4.15 through 4.19 are
five separate clusters under the registered grouping, and all five resolved to
1.0 on 2026-09-07 against a single AAA gas price print. They are one surprise
observed five times.

The consequence is that the interval we registered as the conservative bound,
and which our own plan says governs the claim, treats roughly twice as many
clusters as independent as actually exist. It understates uncertainty in exactly
the way it was registered to prevent.

WHAT WE ARE NOT DOING

We are not revising the registered analysis. Section 9 of the plan lists the
researcher degrees of freedom we gave up, and it names "the block-bootstrap
parameters, including the event-clustered interval reported alongside the
day-blocked one (5.2)". That commitment stands. Both registered intervals will
be computed exactly as registered, and the registered event-clustered interval
still governs the claim wherever the plan says it does.

We are aware that we could argue the intent of 5.2 supports regrouping. We are
not making that argument. A pre-registration whose operationalisations can be
corrected after the fact by appeal to their own stated intent is not a
pre-registration, and the correction would be indistinguishable from the many
other post-hoc choices that a frozen plan exists to rule out.

WHAT WE ARE DOING

A third interval, clustered on actual settlements rather than on source_ref, is
computed alongside the two registered ones and reported with them. It is
labelled unregistered wherever it appears. Because it groups strictly more
task-days into each cluster, it can only widen an interval relative to the
registered one; it cannot narrow a claim or manufacture a result.

If the registered and settlement-clustered intervals agree, nothing turns on
this. If they disagree, we will report both and the weaker claim.

HOW THIS WAS FOUND, AND WHAT WE COULD SEE WHEN WE FOUND IT

It was found by running the registered analysis end to end for the first time,
on the data collected so far, with OUTCOMES PERMUTED. The code that does so was
written on 2026-09-09 and committed publicly the same day; it has never been run
against real outcomes, which the commit history shows. The analysis driver
(neff/analysis.py) is blind by default: it shuffles outcomes unless explicitly
told not to, so the pipeline can be exercised without the effect being seen.
Every analytic choice is already fixed by the registered plan, so there is
nothing legitimate to gain by looking early, and a pipeline whose bugs are found
by their effect on the answer is a pipeline that has been tuned to the answer.

The same first blind run also surfaced two reporting hazards, now guarded: at
the five resolved task-days then available the estimator returned N_eff = 17.6
against a nine-model panel, and a bootstrap upper bound of 1.1e12. Neither is an
estimator error -- mean pairwise error correlation can be negative at that
sample size, and our N_eff implementation clamps at the -1/(M-1) floor exactly
as documented -- but both are values that would have printed. The driver now
refuses to report an N_eff sitting on that clamp, flags N_eff exceeding the
panel size, and names a panel whose rows all trace to a single settlement.

A SECOND, SMALLER DISCLOSURE

The same review found that 29.4% of our collection days carry a market state
that is not their own. Markets are shut at our 13:10 UTC collection time on
weekends and holidays, so FRED and the VIX return the prior close and that day's
questions are stamped with it. Observed directly: 2026-09-05 (Saturday),
2026-09-06 (Sunday) and 2026-09-07 (Labor Day) all carry VIX 14.32, which is
Friday 2026-09-04's value. Eight collection days produced five distinct market
states. Across the full 2026-09-01 to 2026-12-11 window this is 30 of 102 days.

This biases nothing -- the duplicated state is the correct state, because no
trading occurred -- and it is confined to the stress leg of H1. Of the seven
registered state variables, three are market-derived and go stale (VIX level,
20-day realised volatility, |macro surprise|); the other four do not. Ladder
distance is set per question, cross-model dispersion is computed from that day's
own forecasts, days-to-resolution decrements daily, and novelty grows with the
corpus. The ambiguity leg of H1, which is the experimentally varied one, is
untouched.

The stress leg still clears its registered requirement. Section 6 requires
roughly 300 task-days per stress tercile and about 600 remain informative. What
is narrower than the sentence in section 6 implies is the margin, not the power:
about 2x the requirement rather than the ~2.9x a reader would compute from the
raw task-day count. We are stating this before the terciles are formed rather
than defending it afterwards.

We are changing nothing in response to it. Collecting seven days a week remains
correct: the forecasts themselves are not stale, only the market covariates are,
and dropping weekend days would break the continuity of the daily public record
that makes our timestamps checkable.

VERIFICATION

Everything above is checkable without taking our word for it.

  Repository:   https://github.com/rara-bot/correlated-minds
  Recorded at:  PREREGISTRATION.md section 11, deviations 5 and 6
  Code:         neff/analysis.py, tests/test_analysis_driver.py

The registered plan is unchanged outside section 11, which the plan itself
requires deviations to be written into. This is verifiable independently of us:

  ./.venv/bin/python scripts/freeze_prereg.py --check

It reports "intact outside section 11" and prints the registered hash above. The
text as registered is public at commit a300cb58b593 if you would rather diff it
than trust the check.

Data, tasks and resolutions are committed daily to that public repository as
append-only JSONL, so the claim that no outcome existed for the affected
questions when this was written is checkable against the commit history rather
than asserted.
```

---

## Step 2 — paste this as the OSF project wiki entry

Title the wiki page **`Addendum 1 — 2026-09-09`**, then paste:

```
ADDENDUM 1 -- 9 September 2026

Two disclosures about the registered plan, both found before any primary
estimate had been computed on real outcomes.

1. A SPECIFICATION ERROR IN THE SECTION 5.2 EVENT-CLUSTERED INTERVAL.

Section 5.2 justifies its cluster bootstrap by noting that every strike on a
ladder settles against a single print, then operationalises the clustering on
`source_ref`. A Kalshi ticker is SERIES-EXPIRY-STRIKE, so `source_ref` contains
the strike and splits the very ladder the justification names. Measured on the
241 tasks collected through 8 September: 80 distinct source_refs against 40
distinct settlements.

The interval registered as the conservative bound -- the one section 5.2 says
governs the claim -- therefore treats about twice as many clusters as
independent as exist.

We are NOT revising it. Section 9 gives up the right to, and that commitment
stands. A settlement-clustered interval is computed alongside and reported with
it, always labelled unregistered. Because it groups strictly more task-days per
cluster it can only widen an interval, never narrow a claim.

2. STALE MARKET STATE ON NON-TRADING DAYS.

Markets are shut at our 13:10 UTC collection time on weekends and holidays, so
29.4% of collection days (30 of 102) carry the prior close. It biases nothing --
the duplicated state is the correct state -- and it is confined to the stress
leg. The stress leg still clears its registered requirement; the margin is
narrower than the sentence in section 6 implies.

HOW THESE WERE FOUND

By running the registered analysis end to end for the first time with OUTCOMES
PERMUTED. The analysis driver is blind by default and has never been run against
real outcomes, which the public commit history shows.

VERIFICATION

  Repository:  https://github.com/rara-bot/correlated-minds
  Recorded at: PREREGISTRATION.md section 11, deviations 5 and 6
  Zenodo:      10.5281/zenodo.22220263 (see the latest version)

The registered plan is unchanged outside section 11, which the plan itself
requires deviations to be written into:

  ./.venv/bin/python scripts/freeze_prereg.py --check

reports "intact outside section 11" and prints the registered hash. The text as
registered is public at commit a300cb58b593.
```

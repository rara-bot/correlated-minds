# OSF addendum 1 — ready to post

**Three steps, about 25 minutes.** Do them in this order, on the same day.

| Step | Where | What |
|---|---|---|
| 1 | **Zenodo** — open DOI `10.5281/zenodo.22220263` → **New version** | Upload `PREREGISTRATION.md` (the current one, with §11) and `OSF-ADDENDUM-1.md` (this file). Set version to `1.1-addendum-1`. Publish |
| 2 | **Your OSF project** (osf.io/965dz — the project, *not* the frozen registration) | Upload the same two files. Then **Wiki** → new page titled `Addendum 1 — 2026-09-14` → paste the wiki entry at the end of this file |
| 3 | **osf.io/x6kqg** (the registration) | Only if it offers a way to attach a note or comment without changing any registered answer: paste the title and body below. If the only option is "Update" of the registered answers, **skip this step** |

**Do not withdraw or edit the registration.** Its immutability is the asset. Steps
1 and 2 put the record beside it; they change nothing in it.

| | |
|---|---|
| Registration | osf.io/x6kqg, registered 2026-08-29 14:44 UTC |
| Plan frozen | 2026-08-29 03:54 UTC |
| Registered SHA-256 | `90a7e7de5980a80bef786e87b938495d7a08e10234032a11c5d67e8ce1c70009` |
| Addendum date | 2026-09-14 |
| Recorded at | PREREGISTRATION.md §11, deviations 1-20 |

**Why post it before 2 Oct:** its value is that it is public while the outcomes it
could affect are still unknown. On 2026-09-13, 13 collection days exist, 21
task-days in the primary panel have an outcome, and every analysis in the
repository has been run only on permuted outcomes. The Week-5 prediction is made
on 2 Oct; this addendum fixes the rules it will be made under.

---

## Paste below this line

### Title of update

```
Addendum 1 (14 Sep 2026): twenty dated deviations and disclosures, all recorded before any primary estimate was computed on real outcomes
```

### Body

```
WHAT THIS IS

Section 11 of the registered plan requires every change after the freeze to be
logged as a dated, numbered deviation. By 14 September 2026 there were twenty.
This addendum summarises all of them in one public place. The full text of each is
in PREREGISTRATION.md section 11 in the repository and in the Zenodo deposit.

None of them changes a hypothesis, a falsification clause, the model roster, the
sampling temperature, the task mix, the primary outcome or the multiple-testing
correction. Every analysis choice below was fixed while the analysis code had only
ever been run on permuted outcomes.

A. THE REGISTRATION RECORD ITSELF (deviation 13)

1. The PREREGISTRATION.md file attached to this OSF registration is the 23 August
   freeze (hash 2189f8c6...), not the plan registered on 29 August (hash
   90a7e7de...). The plan was re-frozen on 29 August to move the collection window
   five days later, and the copy in the OSF project was not replaced before
   registering. The two files differ in seven lines, all of them dates:
   collection start 24 Aug -> 29 Aug, calibration end 27 Sep -> 2 Oct, data freeze
   6 Dec -> 11 Dec, in the header, section 3.3, section 5.3 and section 5.4(b). The
   text of this registration form carries the 29 August dates and cites
   90a7e7de...; the Zenodo deposit and the repository hold the 29 August file.

2. The registered hash is computed over the plan with its three stamp lines
   (Status, Frozen on, SHA-256 of frozen version) removed and no final newline,
   because a document cannot contain its own hash. A plain SHA-256 of the file
   gives a different number. The repository README gives a one-line check that
   needs none of the project's own code.

3. Collection began on 1 September 2026, not 29 August: the registration awaited
   approval, and collection is locked in code until it is on record. The window
   is 102 days, not 105.

4. Section 3.5 says the ledger held 228 pre-registration entries; it held 208.
   Twenty further task rows dated 17 August belong to a mock rehearsal whose
   fabricated observations were archived separately. A verification run on
   2 September booked ten more calls (about $0.002) to the pilot arm. None of these
   rows can enter any analysis.

5. Two quotations in section 1 and section 4 (H6) are not exact: arXiv 2605.00844
   reads "epistemic monoculture that is built but not yet activated", and the
   sentence attributed to arXiv 2607.20768 is not in its abstract.

B. CHANGES TO THE INSTRUMENT DURING COLLECTION

Each is transport or record-keeping unless stated. No change alters the question a
model is asked or how it is asked, except where a registered arm was missing.

- Dev 1 (3 Sep): the output-token ceiling was raised from 400 to 1000 after one
  model was cut off before finishing its answer on 7 of 54 calls.
- Dev 2 (3 Sep): a backup run added 5 questions to one day (30 instead of 25); a
  rerun now finishes a day and can no longer extend it.
- Dev 4 (9 Sep): OpenRouter routing excludes one host that rejected every qwen
  call on two days.
- Dev 7 (9 Sep): the upstream host that serves each open-weight model is recorded.
- Dev 10 (9 Sep): logprobs, which section 5.4(a) relies on, had never been
  requested; they are requested from 9 September.
- Dev 11 (13 Sep): a rate-limited call is waited out, within a fixed time
  allowance, instead of being lost.
- Dev 14 (13 Sep): H3's intra-model arm -- one model under five prompt variants
  -- had never been collected. From 14 September gpt-4.1-mini answers every
  question under the four registered alternative framings. The first 13 days have
  no variant data; H3(a) is estimated from 14 September.
- Dev 15 (13 Sep): Kalshi prices are public (the API renamed its fields, and the
  code read the old names). Each question now records the market's price when it
  is asked, never shown to a model, and the shape of its strike ladder.
- Dev 16 (13 Sep): 13 filing questions about ExxonMobil asked about a quarter the
  company had already filed, because its second-quarter figure is not
  machine-readable where the study reads it. They are excluded; any question
  asked after its target quarter's SEC filing deadline is now refused and
  excluded; the resolver scores only the quarter asked about; Chevron replaces
  ExxonMobil so the registered 60/40 mix holds.

C. ANALYSES THAT WERE MISSING, IMPLEMENTED BLIND

- Dev 3 (8 Sep): filing questions built on a reporting series that ended years ago
  (JPMorgan, 2014) are excluded; they asked about a quarter the models could recall.
- Dev 5 (9 Sep): the section 5.2 event-clustered interval is operationalised on
  source_ref, which splits one release's strike ladder into one cluster per
  strike. It is computed as registered; an interval clustered on the actual
  settlement is reported beside it, and where they disagree the weaker claim is
  reported.
- Dev 8 (9 Sep): the three analysis-time state variables were defined.
- Dev 9 (9 Sep): the section 5.6 coverage floor had never been applied; it is now.
  On current data it removes qwen (M falls from 9 to 8), recomputed on every run.
- Dev 17 (13 Sep): H1 and every quantity the plan says is "reported always" had
  no implementation. They are implemented, with every open choice fixed: the
  pairwise error-product regression (standardisation, clustering on the question,
  BH over all seven variables with any untestable variable counted at p = 1); the
  tercile rules; what is reported beside every headroom; H4 recomputed at the
  surviving panel size if a model is removed; and ladder_distance treated as
  undefined for questions with no numeric strike ladder (49 of 200 event
  task-days, such as Fed decisions). Because a blind run on 14 question clusters
  called three variables significant on permuted outcomes, every verdict from
  fewer than 30 questions or 10 settlements is labelled provisional, and the claim
  is the weaker of two clusterings.
- Dev 19 (13 Sep): the human benchmark is computed from pinned copies of its
  inputs -- the SPF workbook of 17 August, and FRED as served at 01:58 UTC on
  14 September -- and on them the registered SPF RECESS table reproduces
  exactly. A quarter is averaged only once all three of its months are
  published, which moves the secondary point-forecast baselines of section 2.1
  (their band, 0.083-0.192, becomes 0.086-0.200). The benchmark at M = 8 is
  fixed now, in case section 5.6 keeps a model out. The section 5.4(a) logprob
  leg gets a validity rule (a model-and-host source counts only if, on every
  row, the token emitted is the likeliest one listed) and a definition of the
  logprob-derived probability.
- Dev 20 (14 Sep): H2 to H6 and the section 5.4(a) re-estimate on logprob-derived
  probabilities had no implementation. They are implemented with every open
  choice fixed. H2's category is the Kalshi series, and its base rate is the share
  of that series' markets that settled YES in the twelve months before collection,
  read from Kalshi and pinned. H3 compares its three arms at a panel size of two,
  with an exact permutation over family labels (1260 labelings at nine models).
  H4 is compared at all five SPF RECESS horizons and claimed only if it holds at
  each, matched on Brier skill in three strata, and is uninformative where the
  matched human headroom is below 0.01. H5 gets its interval. H6 is refitted under
  every family labeling with the capability terms held fixed. The logprob
  re-estimate compares derived and emitted probabilities on identical cells.

D. DISCLOSURES

- Dev 6 (9 Sep), corrected by dev 13: weekend and holiday tasks repeat the last
  published market state. The repeated VIX value of 5-7 September was Thursday
  3 September's close, not Friday's as first stated; the count is unchanged. The
  stress leg still clears its registered sample requirement.
- Dev 12 (13 Sep): most deepseek rows arrive without logprobs because most hosts
  that serve it send none; routing was deliberately not changed mid-panel.
- Dev 13: the market state on each task is the latest value published when the
  question was asked (the previous trading day's close or older), and jobs start
  hours after the scheduled 13:10 UTC. Section 10's limitation 1 (Kalshi prices
  not public) is wrong. "20-day realised volatility" is the volatility of the VIX
  itself, as implemented at registration.
- Dev 17: from late October each company's next target quarter falls due after
  the freeze, so late-window filing questions cannot resolve and are excluded by
  section 3.3; the 60/40 mix is kept at collection.
- Dev 19: deepseek's logprobs fail that rule on both hosts that send any (one
  lists alternatives that belong to a different token), so the logprob
  sensitivity rests on three models -- gpt-4.1-mini, gpt-4.1-nano and Llama --
  not the four section 5.4(a) names.
- Dev 20: on a strike ladder the most ambiguous strikes are those whose true
  probability sits nearest a base rate near one half, so H2's registered contrast
  can lean toward H2 for a mechanical reason. The same contrast measured against
  the market's own distance from the base rate is reported beside it as a
  sensitivity that cannot change the verdict.

E. THE WEEK-5 PREDICTION (deviation 18)

Section 5.3 registers the date (2 Oct 2026), the fit (H1 on weeks 1-5) and the form
of the sentence, and left open every choice that decides whether it can be
tested. They are fixed now:

- A macro release is a Kalshi event in one of nine series settled by a scheduled
  US official statistic: CPI and core CPI year on year, PPI month on month and
  year on year, the unemployment rate (two contract styles), nonfarm payrolls,
  advance GDP, and housing starts.
- Its surprise is the Brier score of the market against the print: for each
  strike the market was unsure about (price between 0.05 and 0.95 a day before
  the close, quoted no more than 20 cents wide), the squared difference between
  the settlement and that price, averaged. It uses market prices and settlements
  only, never a model's forecast. This also replaces the earlier definition of the
  H1 state variable |macro surprise|, which had no working consensus source.
- The 80th percentile is fixed now as a number: 0.2425625, over all 66 listed
  releases that closed in the twelve months before collection began.
- X and Y are the medians of headroom and rho_bar over the eligible releases that
  settle by 2 October; a fit on surprise may make them stricter, never easier.
- The prediction is published on or after 2 October 2026 20:00 UTC by a script
  that refuses to run earlier or twice, committed to the repository and deposited
  on Zenodo the same day with its SHA-256.
- The holdout uses only questions asked from 3 October. The first release after
  2 October with a surprise of at least 0.2425625 decides it: HIT if headroom is
  below X and rho_bar above Y, otherwise MISS. If no such release settles by
  11 December, the prediction is reported as untested.

WHAT WE ARE NOT DOING

We are not revising any hypothesis, falsification condition, registered interval,
or the model roster. Where a registered operationalisation turned out to be
flawed (the event-clustered interval of section 5.2), it is still computed exactly
as registered, and the flaw is reported beside it rather than repaired in place.
Where data was lost -- days without logprobs, days without the H3 arm -- nothing is
reconstructed; the gap is stated.

HOW THIS WAS FOUND

By running the registered analysis end to end on permuted outcomes, and by
auditing every registered commitment -- hypotheses, state variables, arms, sample
requirements, citations and the registration files themselves -- against the code,
the data and the public record. Every analysis in the repository is blind by
default: it shuffles outcomes unless explicitly told not to, and has never been
run otherwise.

VERIFICATION

  Repository:  https://github.com/rara-bot/correlated-minds
  Recorded at: PREREGISTRATION.md section 11, deviations 1-20
  Zenodo:      10.5281/zenodo.22220263 (latest version)

The plan outside section 11 is unchanged since registration:

  ./.venv/bin/python scripts/freeze_prereg.py --check

reports "intact outside section 11" and the registered hash. The text as registered
is public at commit a300cb58b593. Data, tasks and resolutions are committed daily as
append-only files, so what existed on any date is checkable from the commit history.
```

---

## Step 2 — paste this as the OSF project wiki entry

Title the page **`Addendum 1 — 2026-09-14`**, then paste:

```
ADDENDUM 1 -- 14 September 2026

Twenty dated deviations and disclosures, all logged in PREREGISTRATION.md
section 11 before any primary estimate was computed on real outcomes. No
hypothesis, falsification clause, model, temperature, task mix, primary outcome or
multiple-testing correction has changed.

THE REGISTRATION RECORD
- The file attached to the registration is the 23 Aug freeze; the registered plan
  is the 29 Aug freeze. They differ only in the dates of the five-day window slip.
  The form's text and the Zenodo deposit carry the 29 Aug plan and its hash.
- The registered hash excludes the three stamp lines; see the README for a
  one-line check.
- Collection began 1 Sep, not 29 Aug.

INSTRUMENT (all from the dates stated)
- 3 Sep: output-token ceiling 400 -> 1000; a rerun can no longer add questions.
- 9 Sep: OpenRouter host filter; upstream host recorded; logprobs requested.
- 13 Sep: rate limits waited out; H3 prompt-variant arm collected (it never had
  been); Kalshi prices recorded (they were public under renamed fields);
  questions past their SEC filing deadline refused and excluded (13 ExxonMobil
  task-days); Chevron replaces ExxonMobil to keep the 60/40 mix.

ANALYSIS, FIXED BLIND
- Missing implementations added: the 5.6 coverage floor, the derived state
  variables, H1's regression and tercile contrasts, and every quantity reported
  always. Choices left open by the plan are fixed in deviation 17, including a
  provisional label and a weaker-of-two-clusterings rule for small samples.
- Deviation 19: the human benchmark reads pinned copies of its inputs and
  reproduces the registered SPF table exactly; a quarter is averaged only when
  complete, which moves the secondary SPF baselines slightly; deepseek's
  logprobs fail a validity check, so the logprob sensitivity uses three models.
- Deviation 20: H2 to H6 and the logprob re-estimate implemented blind. H2's base
  rate comes from Kalshi settlements before the study; H4 must hold at all five
  SPF horizons; H3 and H6 use exact permutations over family labels.

THE 2 OCT PREDICTION (deviation 18)
- Macro release: one of nine Kalshi series settled by US official statistics.
- Surprise: the market's Brier score against the print, from prices a day before.
- 80th percentile, fixed now: 0.2425625 (66 releases, Sep 2025 - Aug 2026).
- X, Y: medians over releases settling by 2 Oct, tightened but never loosened by
  a fit. Holdout: questions asked from 3 Oct; first release at or above the
  threshold decides; untested if none by 11 Dec.

VERIFICATION
  Repository:  https://github.com/rara-bot/correlated-minds
  Zenodo:      10.5281/zenodo.22220263 (latest version)
  ./.venv/bin/python scripts/freeze_prereg.py --check  ->  "intact outside section 11"
```

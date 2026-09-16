# Correlated Minds

**How many genuinely independent judgements is an AI-mediated market actually
getting — and does that number collapse precisely when markets are under stress?**

A prospective, pre-registered study measuring error correlation across nine
large language models on real financial forecasting questions, benchmarked
against human professional forecasters.

**Pre-registered:** [osf.io/x6kqg](https://osf.io/x6kqg/) · registered 2026-08-29 14:44 UTC
· mirror [10.5281/zenodo.22220263](https://doi.org/10.5281/zenodo.22220263)
· plan hash `90a7e7de5980a80bef786e87b938495d7a08e10234032a11c5d67e8ce1c70009`

The analysis plan was frozen and hashed on 29 Aug 2026 at 03:54 UTC, before any
study data existed. It was registered on OSF the same day, three days before the
first observation was collected on 1 Sep; it is public in this repository at
commit `a300cb58b593`; and it was deposited on Zenodo on 1 Sep.

Two details a careful reader will find, both recorded in the plan's own deviation
log (PREREGISTRATION.md §11, deviation 13):

- **The file attached to the OSF registration is the 23 Aug freeze**, which the
  29 Aug freeze replaced before registering. The two differ in seven lines, all of
  them dates, from slipping the collection window by five days. The registration
  form's own text carries the 29 Aug dates and cites the hash above, and the
  Zenodo deposit and git both hold the 29 Aug file.
- **The hash is not `shasum` of the file.** A document cannot contain its own
  hash, so it is taken with the three stamp lines removed. On the file downloaded
  from Zenodo, this reproduces it without trusting any code in this repository:

```bash
grep -v -e '^\*\*Frozen on:\*\*' -e '^\*\*SHA-256 of frozen version:\*\*' -e '^\*\*Status:\*\*' PREREGISTRATION.md | perl -pe 'chomp if eof' | shasum -a 256
```

The copy in this repository also carries the deviation log: the plan requires
every change after the freeze to be written into §11 as a dated row. To check that
nothing outside that table has changed since registration:

```bash
./.venv/bin/python scripts/freeze_prereg.py --check
```

It prints `status : intact outside section 11` and lists every deviation.

---

## The idea in one paragraph

Banks and investment firms are replacing human analysts with AI. Different firms
use different AI systems, which looks like a market full of independent opinions.
But these systems learned from heavily overlapping data, so when a question gets
genuinely hard they may fall back on the same absorbed assumptions and be **wrong
in the same way at the same time**. Markets only function when participants
disagree. This study measures how much genuine independence is actually there,
and whether it disappears under stress.

The Financial Stability Board, the Bank of England and the IMF have each named
this a systemic risk. A handful of recent papers have measured how often language
models err together — on questions that had already been answered, in simulation,
or outside finance (PREREGISTRATION.md §1). **None has measured it prospectively
on financial questions, against human professionals, while asking whether it
rises under stress.** That is this study.

---

## The estimator

For M forecasters whose errors have mean pairwise correlation `rho_bar`:

```
N_eff = M / (1 + (M - 1) * rho_bar)
```

"How many independent opinions is this panel actually worth?" At `rho_bar = 0`,
N_eff = M. At `rho_bar = 1`, N_eff = 1.

**We correlate errors, not forecasts.** Two forecasters who are both right agree
strongly but are not redundant — the question simply had a knowable answer.
Correlating errors isolates *shared wrongness*, which is the only kind that
creates systemic risk. Because Pearson correlation cannot see a bias every model
shares, the plan also reports the model-free `n_eff_mse` beside it (§4.2).

---

## How it runs

Every day, automatically:

1. Build the day's 25 questions: Kalshi event contracts (economics, financials)
   that resolve before the **11 Dec data freeze**, and questions about companies'
   next, not-yet-filed quarterly revenue from their SEC filings — 60% and 40%.
2. Ask all ten models the same questions at temperature 0, with a fixed JSON
   schema. Nine are the registered primary panel; the tenth, a second frontier
   model, is collected and excluded from every primary estimate (§3.1). One model
   also answers every question under four more registered prompt framings, for H3.
3. Record the market's own price for each Kalshi question when it is asked. It is
   stored beside the question and never shown to a model.
4. Append every answer to a public, timestamped, append-only record, and commit it.
5. Score the questions that have settled, and record how much each settled macro
   release surprised the market.

**Every question is registered before its outcome exists.** That is the study's
core defence: an LLM cannot recall an event that has not happened, and the daily
commit makes the timestamp checkable rather than merely asserted. The one place
this failed was found and excluded: 13 questions about ExxonMobil asked about a
quarter it had already filed, which the study's data source could not see
(deviation 16). The generator now refuses any question asked after its target
quarter's SEC filing deadline.

---

## Status

**Collecting daily since 1 Sep 2026.** Next: the pre-registered out-of-sample
prediction on **2 Oct 2026**. Data freeze: **11 Dec 2026**. Every change to the
instrument or the analysis since registration is a dated row in
PREREGISTRATION.md §11.

| Component | Status |
|---|---|
| Daily collection: 10 models, 25 questions, test-retest replicates | ✅ running (GitHub Actions) |
| H3 prompt-variant arm; Kalshi prices on every question | ✅ from the first run after 13 Sep (deviations 14, 15) |
| Estimators: N_eff, block and cluster bootstrap, Benjamini-Hochberg | ✅ tested |
| Registered exclusions (§3.3, §5.6, deviations 3 and 16) | ✅ applied by the analysis |
| Primary estimate and every quantity "reported always" | ✅ built; run blind with `scripts/analyze.py` |
| H1 regression and tercile contrasts | ✅ built; run blind (`neff/h1.py`, deviation 17) |
| Week-5 prediction | ✅ built and registered (deviation 18); published 2 Oct |
| H2 to H6, and the §5.4(a) logprob re-estimate | ✅ built; run blind (`neff/h2.py` to `neff/h6.py`, deviation 20) |
| SPF human baseline | ✅ read from pinned inputs; reproduces the registered table exactly (deviation 19) |

The analysis is **blind**: until the registered looks — the Week-5 fit on 2 Oct and
the final analysis after 11 Dec — every analysis run permutes the outcomes, so the
code is exercised on real shapes without anyone seeing the effect.

---

## Quick start

```bash
python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pytest tests/ -q
```

Run a full day offline, with zero spend and no API keys. Every forecast it
produces is fabricated, so it writes to `data/mock/` — never to the study
record, and `data/mock/` is gitignored:

```bash
./.venv/bin/python -m neff.collect --mock --tasks 8 --arm pilot
```

Price a real day without spending (it prices every call at 300 output tokens, so
it reads about twice the real cost):

```bash
./.venv/bin/python -m neff.collect --dry-run --tasks 25
```

Run the registered analysis, blind:

```bash
./.venv/bin/python scripts/analyze.py
```

---

## What things cost

**Every data source is free.** Kalshi, FRED, the Philadelphia Fed SPF, SEC EDGAR
and GitHub Actions need no keys and no fees. The budget goes to one thing: paying
the models to answer.

| | Cost |
|---|---|
| Actually spent, 1–13 Sep (13 collection days) | **$2.82**, about $0.22 a day |
| Projected to the 11 Dec freeze, with replicates and the H3 arm | about **$25** in total |
| `ws1_prospective` arm cap, enforced in code | $110 |
| Budget cap, enforced in code | $200 |

---

## What Week 0 already found

Measuring the human baseline before collecting anything produced a result that
changed the design:

| Variable | Horizon | Human `rho_bar` |
|---|---|---|
| Unemployment | nowcast | 0.996 |
| Unemployment | 3 quarters ahead | 0.876 |
| CPI | nowcast | 0.999 |

Human forecast errors are *already* nearly perfectly correlated at short
horizons, because errors are dominated by the common surprise nobody saw coming.

**Consequence:** a naive "AI is more correlated than humans" hypothesis is
untestable at short horizons — the metric saturates and leaves no room. So the
primary outcome is **diversification headroom, `N_eff - 1`**, and task selection
excludes near-settled questions.

(An intermediate fix — correlating residuals after removing the panel's mean
error, "excess correlation over the common component" — was itself found to be
broken and dropped: residuals sum to zero by construction, so their pairwise
correlation is exactly `-1/(M-1)` whatever the truth is. §2.3 records it.) See
[PREREGISTRATION.md](PREREGISTRATION.md) §2.

---

## Layout

```
neff/
  stats.py         N_eff, block bootstrap, BH correction, uncentred estimators
  metrics.py       variance reduction, MSE-scale N_eff, the human-vs-AI statistic
  ledger.py        cost accounting with a hard, code-enforced cap
  store.py         append-only JSONL: tasks, observations, resolutions
  config.py        the pinned model roster and run constants
  providers.py     multi-provider LLM client (+ offline mock)
  tasks.py         daily task battery construction, prompt variants
  collect.py       the daily runner
  panel.py         observations -> matrices; the registered exclusions
  analysis.py      the primary estimate, composed; blind by default
  report.py        everything the plan reports always
  h1.py            the primary hypothesis: regression and tercile contrasts
  h2.py            H2: does the panel converge on the base rate as ambiguity rises
  h3.py            H3: one model's prompt variants against within- and cross-family pairs
  h4.py            H4: AI against SPF RECESS forecasters, at matched accuracy
  h5.py            H5: macro against filing tasks
  h6.py            H6: lineage or capability, by exact permutation over family labels
  state.py         the three state variables derived at analysis time
  surprise.py      how much a macro release surprised the market
  prediction.py    the Week-5 out-of-sample prediction
  logprobs.py      which stored logprobs are valid, and the probability they imply
  verify.py        live pre-flight check of every pinned model
  sources/
    kalshi.py      questions, prices, strike ladders, settlement
    edgar.py       SEC filing questions and their resolution
    fred.py        market state
    spf.py         the human baseline, from pinned inputs in data/spf/
    http.py        retries, backoff, body verification
scripts/
  freeze_prereg.py        freeze and check the plan
  check_days.py           is the daily record unbroken?
  analyze.py              run the registered analysis, blind
  week5_prediction.py     rehearse, publish or evaluate the 2 Oct prediction
  release_surprise.py     market surprise of settled macro releases
  category_base_rates.py  H2's pre-study base rate for each Kalshi series
  snapshot_kalshi_ladders.py  strike structure of questions asked before 14 Sep
  pin_spf_inputs.py       the human benchmark's inputs, pinned once
tests/             about 765 tests, run before every collection
```

---

## Documents

| File | What it is |
|---|---|
| [EXPLAINER.md](EXPLAINER.md) | Plain-language version — not for use as an abstract |
| [PREREGISTRATION.md](PREREGISTRATION.md) | The frozen scientific commitment, with its deviation log |
| [OSF-ADDENDUM-1.md](OSF-ADDENDUM-1.md) | The public addendum reporting deviations 1-19, ready to post |
| [VALIDITY.md](VALIDITY.md) | Do the tasks match how AI is used in finance? Limitations |
| [AI-USE-LOG.md](AI-USE-LOG.md) | Which parts were written with an AI assistant, for the ISEF rules |
| [AUDIT.md](AUDIT.md) | 28 defects found before collection, and how |
| [PRIOR-ART.md](PRIOR-ART.md) | What is already claimed, with verification flags |
| [RESEARCH-DOSSIER.md](RESEARCH-DOSSIER.md) | Full program spec |
| [ELEVATION.md](ELEVATION.md) | How this becomes a discovery, not a measurement |
| [STRATEGY.md](STRATEGY.md) | The four-year arc |
| [SUBMISSION-TARGETS.md](SUBMISSION-TARGETS.md) | Competitions and conferences |
| [BUDGET.md](BUDGET.md) | Cost model, as planned in August |
| [GO-LIVE.md](GO-LIVE.md), [SETUP.md](SETUP.md) | Historical: how collection was set up |

---

## A note on verification

Two sources in this project return **HTTP 200 with a body that is not the data
you asked for**: Stooq serves a JavaScript challenge, and the Philadelphia Fed's
per-variable SPF URLs serve HTML. A third changed shape silently: Kalshi renamed
its price fields, and for two weeks the code read the missing old names as
"quotes are not public" (deviation 15). Status codes were checked *and* bodies
inspected for every source here, and `sources/http.py` enforces the first half of
that, because a source that fails silently is worse than one that fails loudly.

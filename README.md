# Correlated Minds

**How many genuinely independent judgements is an AI-mediated market actually
getting — and does that number collapse precisely when markets are under stress?**

A prospective, pre-registered study measuring error correlation across nine
large language models on real financial forecasting questions, benchmarked
against human professional forecasters.

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
this a systemic risk. Every existing paper *assumes* a number for how correlated
AI systems are. **This measures it.**

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
creates systemic risk.

---

## How it runs

Every day, automatically:

1. Pull open event contracts from Kalshi (economics, financials) that resolve
   **before the 6 Dec data freeze**.
2. Ask all ten models the same questions, at temperature 0, with a fixed JSON
   schema. Nine are the registered primary panel; the tenth is a second
   frontier model, collected daily and excluded from every primary estimate
   (PREREGISTRATION.md §3.1).
3. Append every answer to a public, timestamped, append-only record.
4. Check which past questions have settled and score them.

**Every question is registered before its outcome exists.** That is the study's
core defence: an LLM cannot recall an event that has not happened. The daily
git commit makes the timestamp externally checkable rather than merely asserted.

---

## Status

**Week 0 of 19 — instrument built, collection not yet started.**

| Component | Status |
|---|---|
| N_eff estimator, block bootstrap, BH correction | ✅ tested |
| Cost ledger, hard $200 cap | ✅ tested (concurrency, restart, torn writes) |
| Append-only store | ✅ tested (crash-safe, idempotent) |
| Kalshi tasks + settlement | ✅ live |
| FRED outcomes + market state | ✅ live, no API key required |
| SPF human baseline | ✅ live |
| Multi-provider LLM client | ✅ built, mock-tested |
| Panel assembly → analysis | ✅ end-to-end verified |
| Pre-registration | ✅ drafted and audited, awaiting freeze |
| Daily automation | ✅ workflow written |

---

## Quick start

```bash
python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pytest tests/ -q
```

Run a full day offline, with zero spend and no API keys:

```bash
./.venv/bin/python -m neff.collect --mock --tasks 8 --arm pilot
```

Price a real day without spending:

```bash
./.venv/bin/python -m neff.collect --dry-run --tasks 25
```

Then copy `.env.example` to `.env`, add keys, and drop `--mock`.

---

## What things cost

**Every data source is free.** Kalshi, FRED, the Philadelphia Fed SPF,
Polymarket, SEC EDGAR, GitHub Actions — no keys, no fees, no subscriptions. FRED
needs no API key at all via its CSV endpoint.

The entire budget goes to one thing: paying the models to answer.

| | Measured cost |
|---|---|
| One day, 25 tasks × 10 models | **$0.44** |
| Full 15-week panel (105 days) | **$47** |
| 5 prompt variants of one model (the H3 arm) | **$3** |
| `ws1_prospective` arm cap, enforced in code | $100 |
| Budget cap, enforced in code | $200 |

Priced on 21 Aug 2026 by `neff.collect --dry-run --tasks 25` against the live
task battery and the real ten-model roster. The figure this replaces, $0.24/day
for $25 total, was for a nine-model panel and understated the true cost by about
half — which mattered, because the arm cap it was set against is a hard stop that
would have ended collection in November rather than warning about it.

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
primary outcome is now **excess correlation over the common component**, and task
selection excludes near-settled questions. See
[PREREGISTRATION.md](PREREGISTRATION.md) §2.

Finding this in Week 0, rather than in November after 15 weeks of collection, is
exactly why a calibration phase exists.

---

## Layout

```
neff/
  stats.py       N_eff, block bootstrap, BH correction, signal/error decomposition
  ledger.py      cost accounting with a hard, code-enforced cap
  store.py       append-only JSONL: tasks, observations, resolutions
  config.py      the pinned model roster and run constants
  providers.py   multi-provider LLM client (+ offline mock)
  tasks.py       daily task battery construction
  collect.py     the daily runner
  panel.py       observations -> matrices for analysis
  sources/
    kalshi.py    questions + ground-truth settlement
    fred.py      realized outcomes + market state
    spf.py       the human baseline
    http.py      retries, backoff, body verification
tests/           232 tests
```

---

## Documents

| File | What it is |
|---|---|
| [GO-LIVE.md](GO-LIVE.md) | **The launch checklist — read this first if collection has not started** |
| [EXPLAINER.md](EXPLAINER.md) | Plain-language version — start here |
| [PREREGISTRATION.md](PREREGISTRATION.md) | The frozen scientific commitment |
| [RESEARCH-DOSSIER.md](RESEARCH-DOSSIER.md) | Full program spec |
| [PRIOR-ART.md](PRIOR-ART.md) | What is already claimed, with confidence flags |
| [ELEVATION.md](ELEVATION.md) | How this becomes a discovery, not a measurement |
| [STRATEGY.md](STRATEGY.md) | The four-year arc |
| [BUDGET.md](BUDGET.md) | Cost model |
| [AUDIT.md](AUDIT.md) | 23 defects found before collection, and how |
| [SUBMISSION-TARGETS.md](SUBMISSION-TARGETS.md) | Competitions and conferences |

---

## A note on verification

Three sources in this project return **HTTP 200 with a body that is not the data
you asked for**: Stooq serves a JavaScript challenge, and the Philadelphia Fed's
per-variable SPF URLs serve HTML. Status codes were checked *and* bodies
inspected for every source here. `sources/http.py` enforces this, because a
source that fails silently is worse than one that fails loudly.

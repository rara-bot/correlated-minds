# Budget & Resourcing — Correlated Minds

> ## ⚠️ SUPERSEDED BY MEASURED COSTS — 17 Aug 2026
>
> The estimates below were made before the instrument existed. Now that it does,
> the real per-call cost has been measured with a live dry run, and **I was wrong
> by roughly a factor of ten.**
>
> | | Estimated here | **Measured** |
> |---|---|---|
> | One day, 25 tasks × 7 models | ~$2 | **$0.22** |
> | Full 15-week panel | $178 | **$23** |
> | Plus 5 prompt variants (full H3 arm) | "~$2,000, maximal tier" | **$113** |
>
> **Why the error:** these estimates assumed ~6,000 input and ~1,500 output tokens
> per call, with extended reasoning on. The structured-output design that survived
> Week 0 uses ~500 input and ~250 output on mid-tier models — 12× less input, 6× less
> output.
>
> **What it changes:** the five-variant H3 arm I deferred as unaffordable is
> affordable now. Year 1 can ship the *maximal* version of the study inside the $200
> cap, not a compromised one. Tiering by budget is no longer necessary; §3 below is
> retained only as a record of the original reasoning.
**Timeline:** 16 Aug → 31 Dec 2026 (19.5 weeks) · **Effort:** 15 h/week ≈ 290 hours

---

## 1. Two constraints found by checking, not assuming

### 1.1 Claude Pro cannot be the instrument

Claude Pro is a consumer subscription covering the Claude app and Claude Code. It is **not** API
credits, and the distinction is not just billing — it is methodological:

| The study needs | Pro gives |
|---|---|
| **7 model families** — the whole point is *cross-family* error correlation | One family |
| Pinned model IDs, logged per call | No version control or logging |
| Controlled sampling + reproducible parameters | Chat defaults |
| Raw request/response persisted for every observation | Nothing durable |
| ~58,000 programmatic calls | Not a programmatic surface |

A single-vendor panel cannot test H3 (the diversification illusion) at all — H3 *is* the
intra-model vs cross-family contrast.

**So:** Pro stays valuable for the work itself — building the harness in Claude Code, analysis,
drafting. The measurement instrument needs **separate API credits** (console.anthropic.com and the
other providers). Budget below is for those.

### 1.2 Local inference is largely closed on this machine

I checked rather than assumed, and it reverses my earlier suggestion:

```
Apple M1 · 8 GB RAM · 8 cores · 376 GB free
ollama / llama.cpp / lm-studio: none installed
```

**8 GB is the blocker.** It runs a 3B–7B model at Q4 quantisation, slowly, competing with
everything else on the machine. Two problems: 105 days of daily collection would take far longer in
wall-clock than the calendar allows, and a 3B quantised model is not representative of what
financial institutions actually deploy — which makes it a poor stand-in for the open-weight arm.

**So:** the "run open-weight locally for free" lever I floated earlier is off the table. Open-weight
families go to hosted inference instead. That is genuinely cheap (~$0.10–0.60/MTok), so the budget
impact is roughly **+$40**, not a rethink — but the $250 lean tier I quoted assumed local inference,
and that number was wrong for this hardware.

The M1 is entirely adequate for what it *does* need to do: async HTTP orchestration, JSON logging,
and pandas analysis over ~58k rows.

### 1.3 A reliability problem with a methodological upside

The panel must fire every day for 105 days. A laptop that sleeps or closes is not a dependable
scheduler. Best option: **GitHub Actions on a cron schedule** — free tier covers a daily batch job
easily, and the commit history becomes a **cryptographically timestamped, tamper-evident record that
each forecast was registered before the event resolved.**

That is not a workaround, it is a methodological asset. The single strongest objection to any
LLM-forecasting result is "how do we know you didn't run this after the fact?" A public commit log
answers it in one line. Pre-registration hash in Week 0, commits thereafter.

---

## 1.4 Revised to a $200 ceiling — and the constraint improves the instrument

Budget cap is **$200 total**, on top of Claude Pro. That is workable, and the redesign is genuinely
better science rather than a degraded version. Three moves:

### Move 1 — kill the reasoning tokens (this is ~80% of the saving)

The original model assumed 1,500 output tokens per call including extended thinking. Output bills at
roughly 5× input, so it dominated everything.

**Force a structured JSON response instead: probability, direction, confidence, one-sentence
rationale. ~200 tokens.**

This is not a compromise. It is what we should have specified anyway:
- We correlate **decisions**, not essays. The schema *is* the measurement.
- Free-text rationales vary in length and style across families, injecting measurement noise into
  exactly the quantity we're estimating.
- Structured output is machine-parseable with zero extraction error.

**Then take a 10% subsample with extended reasoning on** — that's where H2's mechanism analysis
lives. We need rationale text to test shared-prior fallback, but we need it from ~1,800 calls, not
18,000.

### Move 2 — a mid-tier roster, which is also more representative

Original: 3 frontier + 4 cheap. Revised: 7 families at mid-tier, with one frontier anchor.

The justification isn't only cost. **Mid-tier models are what institutions actually deploy for
high-volume tasks** — cost matters to them too. A roster of Haiku/Flash/8–70B-class models is a
*better* model of real deployment than an all-frontier roster, while Sonnet 5 anchors the top end so
we can test whether tier affects correlation.

| Family | Model tier | ~Rate (in/out per MTok) |
|---|---|---|
| Anthropic | Claude Haiku 4.5 | $1 / $5 |
| Anthropic | Claude Sonnet 5 *(frontier anchor)* | $3 / $15 |
| Google | Gemini 2.5 Flash-Lite | $0.10 / $0.40 · **free tier available** |
| OpenAI | mid-tier | verify at purchase |
| Meta | Llama, hosted | ~$0.20 / $0.60 |
| Alibaba | Qwen, hosted | ~$0.20 / $0.60 |
| DeepSeek | hosted | ~$0.30 / $0.90 |

Blended ≈ **$0.75 in / $3.40 out**.

### Move 3 — caching and batching, as before

4,000-token stable prefix at ~0.1× on reads; Batch API 50% off where offered.

### The arithmetic

Per structured call: input (4,000 cached → 400 effective + 2,000 fresh) = 2,400 eff × $0.75/M =
$0.0018; output 200 × $3.40/M = $0.0007. Sum $0.0025, batched → conservatively **$0.0018/call**.

| Arm | Calls | Cost |
|---|---|---|
| WS1 prospective — 7 families × 25 tasks/day × 105 days | 18,375 | $33 |
| WS2 retrospective | 10,000 | $18 |
| WS5 mitigation | 7,000 | $13 |
| H2 reasoning subsample — 10% of WS1, extended thinking | 1,800 | $36 |
| Subtotal | ~37,000 | **$100** |
| Contingency +100% — pilot, failed batches, prompt-version reruns | | $100 |
| **Total** | | **$200** |

**Free tiers (Gemini, Groq) can pull real spend toward $120.**

### What $200 costs us versus $700

| | Kept | Lost |
|---|---|---|
| Families | 7 (21 pairs) ✓ | — |
| Collection window | 15 weeks ✓ | — |
| Tasks/day | 25 | 30 |
| H1 conditional test | ✓ ~315 obs per stress quintile | ~65 obs/quintile of margin |
| H2 mechanism | ✓ via 10% subsample | full-sample rationale text |
| H3 diversification illusion | ✓ 2 variants | the 5-variant version that made it unassailable |

**All three hypotheses survive adequately powered.** The single real loss is the maximal H3 arm.
If the Week-5 interim read shows H3 is strong, the cheapest possible expansion is more prompt
variants on the *cheap* families only — roughly $25 — which recovers most of it.

---

## 2. Cost model (original $700 version, retained for reference)

**Volume** (15-week collection window, Aug 24 → Dec 6):

| Workstream | Calls |
|---|---|
| WS1 prospective — 7 families × 30 tasks/day × 105 days | 22,050 |
| WS2 retrospective | ~25,000 |
| WS5 mitigation — 5 conditions × 7 families × 300 tasks | 10,500 |
| **Total** | **~57,550** |

**Per-call shape** (frontier tier, reasoning enabled):
- Input 6,000 tokens — 4,000 stable instruction/schema prefix + 2,000 variable task context
- Output 1,500 tokens including thinking

**Two optimisations do the heavy lifting.** Both are unusually well-suited to this study:

- **Prompt caching.** The 4,000-token prefix is identical across every call. Cache reads bill at
  ~0.1× input. Cuts effective input by ~65%.
- **Batch API (50% off).** WS1 looks latency-sensitive but isn't — we only need the call *made*
  before the event resolves. Overnight batch is fine. WS2 and WS5 are trivially batchable.

Together these cut the bill by roughly **70%**, which is why the number below is lower than a
naive per-token estimate suggests.

| Tier | Blended rate | Effective cost/call |
|---|---|---|
| Frontier ×3 (Claude Opus 5 $5/$25; Claude Sonnet 5 $3/$15; Gemini 3.1 Pro $2/$12) | ~$3.30 / $17 | **$0.0167** |
| Open-weight ×4, hosted (Llama, Qwen, Mistral, DeepSeek) | ~$0.30 / $0.60 | **$0.0016** |

| Workstream | Cost |
|---|---|
| WS1 prospective | $178 |
| WS2 retrospective | $150 |
| WS5 mitigation (frontier-weighted — H3 is about families) | $120 |
| Subtotal | $448 |
| Contingency +40% — pilot, failed batches, prompt-version reruns | $180 |
| **Total** | **~$630** |

Infrastructure: **$0** on GitHub Actions free tier (a $5/mo VPS, ~$25 total, is the fallback).

---

## 3. Three tiers

| | **Lean** | **Recommended** | **Maximal** |
|---|---|---|---|
| Budget | **$250** | **$700** (cap $1,000) | **~$2,000** |
| Families | 5 (10 pairs) | **7 (21 pairs)** | 10 (45 pairs) |
| Tasks/day | 15 | **30** | 60 |
| Prompt variants per model | 1 | 2 | **5** |
| Replication arm | ✗ | ✗ | ✓ |
| **What you lose / gain** | Halves observations per stress bin — H1's conditional test loses most of its power. Core N_eff result survives; state-dependence becomes suggestive rather than demonstrated. | All three hypotheses adequately powered. ~380 observations per stress quintile. | H3 tested hard (5 intra-model variants vs 10 cross-family) — the diversification-illusion result becomes very difficult to argue with. |

---

## 4. The honest answer to "how much for optimal"

**~$700 buys the optimal version. Past roughly $1,000, money stops being the binding constraint.**

Beyond that the limits are two things you cannot purchase:

1. **The calendar.** 15 weeks of prospective collection cannot be bought faster. A week not started
   is a week gone — and the panel is the moat, so every day of delay costs more than any budget
   increase buys back. **Starting Week 0 next week is worth more than tripling the budget.**
2. **Researcher hours.** ~290 hours at 15 h/week. The maximal tier's 60 tasks/day generates twice
   the data to validate, monitor, and debug. More data than hours is a net negative.

The $2,000 tier is worth it for exactly one reason: it makes H3 nearly unassailable. If you want
one result that a skeptical judge or reviewer cannot wave away, that is where the extra money goes —
not into more of everything.

**Recommendation: approve $700 with a $1,000 hard cap**, enforced in code by the WS0 cost accountant,
with the option to spend up to $2,000 *only* on expanding the H3 arm if the Week-5 interim read shows
the effect is real and worth nailing down.

---

## 5. Revised schedule — 31 Dec deadline

The December deadline is a substantial upgrade over the STS-compressed plan: **15 weeks of
collection instead of 9.** H1 is a hypothesis about stress states, and longer windows contain more of
them — this is the single biggest quality gain available, and it costs nothing.

| Wk | Dates | Focus | h |
|---|---|---|---|
| 0 | Aug 17–23 | Env, venv + scientific stack, pre-registration hash, provider accounts, GitHub Actions cron, 200-call pilot | 15 |
| 1 | Aug 24–30 | **WS1 goes live** — daily collection begins | 15 |
| 2–4 | Aug 31–Sep 20 | WS2 build + collection; WS1 monitoring | 45 |
| 5 | Sep 21–27 | First $\bar\rho$ read; estimator validation; **H3 go/no-go on expansion** | 15 |
| 6–7 | Sep 28–Oct 11 | WS3 econometrics; interim preprint drafted | 30 |
| 8 | Oct 12–18 | **Preprint posted** — priority defence | 15 |
| 9–11 | Oct 19–Nov 8 | WS4 market model + calibration | 45 |
| 12–13 | Nov 9–22 | WS5 mitigation experiments | 30 |
| 14–15 | Nov 23–Dec 6 | Buffer; **data freeze Dec 6** | 30 |
| 16–17 | Dec 7–20 | Final analysis, all figures, paper draft | 30 |
| 18–19 | Dec 21–31 | Revision, artifacts, submission-ready package | 20 |

**290 hours.** Two weeks of genuine buffer before the freeze — which the 11-week version did not have.

Conference targets fall after this: ICLR 2027 workshops (~Feb), ICAIF'27 (~Aug). Preprint goes up
Week 8 regardless. See [SUBMISSION-TARGETS.md](SUBMISSION-TARGETS.md).

---

## 6. Week-0 purchase list — $200 plan

| Item | Cost | Note |
|---|---|---|
| Anthropic API credits | $60 | console.anthropic.com — **separate from Claude Pro** |
| OpenAI API credits | $40 | Verify current rates at purchase |
| Google AI Studio / Gemini | $20 | Start on the free tier; top up only if it throttles |
| Open-weight host — Together / DeepInfra / Groq / OpenRouter | $40 | Covers Llama, Qwen, DeepSeek |
| Reserve | $40 | Released only against the Week-5 interim read |
| **Total** | **$200** | |

Free and required in Week 0: FRED API key, GitHub Actions (cron + timestamped commit log),
Kalshi and Polymarket public endpoints (no auth), JKP factor data.

**Spend discipline.** The WS0 cost accountant enforces a hard per-arm ceiling and refuses calls past
it — the budget is a code-level invariant, not a spreadsheet. It logs cumulative spend per provider
per day, so a runaway loop or an accidental re-run cannot quietly drain the account. Week-1 pilot
spend gets reconciled against the model above before the full panel goes live; if real cost/call
exceeds the estimate by >30%, tasks/day drops from 25 to 20 rather than the window shortening.

**Never trade the collection window for anything.** It is the one input that cannot be bought back.

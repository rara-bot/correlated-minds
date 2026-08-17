# Topic Selection Dossier
**To:** Research Director · **From:** Researcher · **Date:** 16 Aug 2026
**Decision requested:** approve one of three programs; answer three questions in §11.

---

## 1. Summary

I surveyed the AI × finance frontier against what a 3-month / ~180-hour program can actually
produce. The main finding is **strategic, not topical**: the obvious topics closed during 2026.
Adversarial attacks on LLM traders, lookahead-bias benchmarks, LLM demographic bias in credit and
investment advice, and algorithmic collusion each now have multiple 2026 papers, several from
top-tier groups (an NBER working paper on AI collusion is under revision at *AER*). Full map in
[PRIOR-ART.md](PRIOR-ART.md).

Something more useful fell out of that survey. Three regulators — the **FSB** (Oct 2025), the
**Bank of England** (Jul 2026) and the **IMF** (Jul 2026) — have each named *correlated behaviour
across institutions running similar AI models* as a top-tier financial-stability risk. Two 2026
arXiv papers model the consequences of that correlation. The Bank of England says it is "pursuing
work on simulation methods… to understand conditions under which AI agents could demonstrate
correlated behaviour or herding."

**Every one of them treats the degree of correlation as an assumed parameter. Nobody has measured
it on financial decisions.** The metric exists — error correlation and effective ensemble size were
formalised in 2025–26 — but it has only been applied to general forecasting, LLM-as-judge panels
and prediction markets. Never to finance, and never *conditionally*.

That is the gap I recommend we take. It is a measurement problem sitting under a policy debate that
is already running without it, and measurement is exactly what a well-resourced 3-month program
with no institutional data access can do better than anyone.

---

## 2. The three candidates

| | **A — Correlated Minds** *(recommended)* | **B — Machine-Optimised Disclosure** | **C — Information Half-Life** |
|---|---|---|---|
| **Question** | How many *independent* decision-makers are there in an AI-mediated market, and does that number collapse under stress? | Are firms now writing filings for LLM readers, and is there an exploitable wedge between machine-read and human-read sentiment? | How much information survives the AI-to-AI financial content chain, and what does the loss cost? |
| Novelty | **High** — metric exists, never applied to finance, never conditionally | Medium — Cao et al. (*RFS* 2023) owns the pre-LLM version; an SSRN paper is adjacent | Low-Medium — the "AI telephone game" primitive is established (ACL 2025) |
| Scoop risk | **High** but defensible (§9) | Medium | Medium |
| Data risk | **Low** — all free, all verified | Medium — needs clean return data | Low |
| Null-result risk | **Low** — three independent publishable findings | High — wedge may not exist | Medium |
| Policy pull | **Very high** — 3 regulators actively asking | Medium | Low |
| Fair-judge legibility | **High** — one sentence, one chart | Medium — requires accounting background | High |
| **Score /50** | **44** | 31 | 27 |

Scoring detail in §10. Candidates B and C are real projects and I'd run either happily; A is
better on the dimensions that matter for both a competition and a preprint.

---

## 3. Program A — the research question

> **When AI systems make financial decisions, how many genuinely independent judgements is the
> market actually getting — and does that number fall precisely when diversity matters most?**

The finance analogue is well known: correlations go to 1 in a crisis, so diversification fails
exactly when it is needed. The hypothesis is that **AI cognition has the same pathology, for a
mechanistic reason.** When evidence is strong, models are driven by the evidence. When evidence is
weak or ambiguous, they fall back on priors — and because they share enormous overlap in
pretraining data, those priors are *shared*. So errors should decouple in calm states and lock
together in ambiguous, high-stress, novel states.

If true, the effective number of independent minds in an AI-mediated market is not a constant. It
is a **function of market state that declines exactly into the tail.** No one has tested this.

### Formal object

For models $m = 1..M$ on tasks $t$ with outcome $y_t$, define errors $e_{m,t}$ from a proper
scoring rule. With mean pairwise error correlation $\bar\rho$:

$$N_{\text{eff}} = \frac{M}{1 + (M-1)\bar\rho}$$

the standard equicorrelated-mean result: $M$ models with correlation $\bar\rho$ reduce variance as
if they were $N_{\text{eff}}$ independent ones. **Critically we correlate _errors_, not outputs.**
Output similarity is inflated by the task simply having a right answer; error correlation nets that
out and isolates *shared wrongness* — the only kind that is dangerous. The closest theory paper
(arXiv 2604.22818) draws exactly this distinction and then does not measure it.

### Hypotheses (to be pre-registered before data collection)

- **H1 — Conditional collapse.** $N_{\text{eff}}(s)$ declines in market stress and evidence
  ambiguity. *Falsified if* the stress-quintile coefficient is null at 95% after multiple-testing
  correction.
- **H2 — Shared-prior mechanism.** The collapse is driven by convergence to a common prior, so the
  consensus in high-ambiguity states is predictable from base rates and largely independent of the
  actual evidence presented.
- **H3 — The diversification illusion.** Intra-model diversity (prompt, persona, temperature on one
  model) buys $\Delta N_{\text{eff}} \approx 0$ compared with cross-*family* diversity. If true,
  every risk manager running "an ensemble" of one vendor's model has a diversification strategy that
  does nothing.

H3 is the finding with the shortest path to real-world consequence, and it is cheap to test.

---

## 4. Why this survives scrutiny

**What we concede.** The metric is not ours — correlated LLM errors and effective ensemble size are
established (arXiv 2506.07962, ICML 2025; 2605.00844; 2605.29800). Live contamination-free
evaluation is not ours either (ForecastBench, ICLR 2025). We must cite all of it prominently and
claim neither.

**What is genuinely ours.** Four things, none of which appear in any work I found:

1. **Financial decision tasks with economic loss functions** — existing measurements use general
   trivia, prediction-market questions and judge panels. Correlation on a Brier score is not
   correlation on a portfolio decision, because the second is weighted by money at risk.
2. **State-dependence.** Every existing measurement is *unconditional* — a single scalar $\bar\rho$.
   The conditional structure is the entire fragility story and is untouched.
3. **Empirical calibration of a parameter the theory literature assumes.** We supply the number that
   arXiv 2604.22818 and the FSB/BoE/IMF work currently have to guess.
4. **Transmission to prices,** so the measurement has an economic magnitude and not just a
   correlation coefficient.

**The contamination defence.** The standard kill-shot against LLM-finance work is that the model
already knows the answer. A 2026 ensemble paper (arXiv 2607.18269) calls contamination "a pervasive
confound." We defeat it *by construction*: Workstream 1 forecasts events that **have not happened
yet** at the moment of the call. No amount of pretraining can leak an outcome that does not exist.
This also creates a moat — see §9.

---

## 5. Workstreams

**WS0 · Instrument (Weeks 0–1).** Python venv + scientific stack (local Python is 3.9.6 with no
numpy/pandas). Unified multi-provider async client with pinned model IDs, full request/response
logging, cost accounting, retries, and a content-addressed cache. Pre-registration document frozen
and timestamped before any data is collected. *Tested.*

**WS1 · Prospective panel (Weeks 1–10, runs daily).** The spine. Every day, ~30 decisions × 7 model
families, on events not yet resolved:
- Scheduled macro releases (FRED: CPI, NFP, PPI, retail sales, FOMC) — direction and magnitude
- Upcoming earnings — surprise direction
- Kalshi / Polymarket financial contracts — probability judgements, **with a market-implied
  benchmark**, which additionally tells us whether AI consensus aggregates better or worse than a
  real market
- 8-K materiality judgements, ground-truthed on realised market reaction
- A fixed-scenario portfolio allocation, giving decision correlation weighted by money at risk

Model roster spans **7 families** (OpenAI, Anthropic, Google, Meta, Qwen, Mistral, DeepSeek) = 21
pairs. Open-weight members can run locally, which cuts cost and makes the study reproducible by
anyone without an API budget.

**WS2 · Retrospective panel (Weeks 2–5).** Historical tasks for statistical power and for stress
states the live window may not contain. Contaminated by construction — so it is used *only* for
power and for cross-checking WS1, never as a standalone claim. The WS1↔WS2 gap is itself a
measurement of contamination's effect on apparent diversity, which is a bonus result.

**WS3 · Econometrics (Weeks 5–9).** $N_{\text{eff}}$ estimation with block-bootstrap CIs;
state-dependence regressions on VIX, realised vol, expectation dispersion, |surprise|, news volume,
novelty; multiple-testing correction; the shared-signal / shared-error decomposition.

**WS4 · Transmission model (Weeks 7–10).** Measured $N_{\text{eff}}(s)$ enters a noisy
rational-expectations / Kyle-style market model (ABIDES available if we want a full limit-order
book). The point is the **feedback loop**: stress → higher $\bar\rho$ → lower $N_{\text{eff}}$ →
more correlated order flow → more price impact → more stress. If the measured state-dependence is
strong enough, the loop is self-reinforcing above some AI participation share — i.e. **a critical
threshold**. That phase diagram is the headline chart.

**WS5 · Mitigation (Weeks 8–10).** Test H3 and rank what actually buys independence: cross-family
> architecture > retrieval grounding > persona > prompt > temperature. Produces a practitioner
recommendation with numbers attached.

**WS6 · Artifacts + writing (Weeks 9–11).** Open dataset, open-source `neff` toolkit, preprint,
20-page competition paper, poster, talk.

---

## 6. Schedule (15 h/week, 31 Dec deadline)

Full week-by-week plan and rationale in [BUDGET.md](BUDGET.md) §5. Headline: the December deadline
gives **15 weeks of collection instead of 9** — the single biggest quality gain available, at zero
cost, because H1 is a hypothesis about stress states and longer windows contain more of them.

| Phase | Dates | h |
|---|---|---|
| Week 0 — env, pre-registration hash, GitHub Actions cron, 200-call pilot | Aug 17–23 | 15 |
| **WS1 live**, WS2 build + collection | Aug 24–Sep 20 | 60 |
| First $\bar\rho$ read; **H3 expansion go/no-go** | Sep 21–27 | 15 |
| WS3 econometrics; **preprint posted Week 8** | Sep 28–Oct 18 | 45 |
| WS4 market model + calibration | Oct 19–Nov 8 | 45 |
| WS5 mitigation | Nov 9–22 | 30 |
| Buffer; **data freeze Dec 6** | Nov 23–Dec 6 | 30 |
| Final analysis, figures, paper, artifacts | Dec 7–31 | 50 |

**290 hours, with two weeks of genuine buffer before the freeze** — which the STS-compressed plan
did not have.

---

## 7. Budget — see [BUDGET.md](BUDGET.md) for the full model

**~$700 buys the optimal version; past ~$1,000 money stops being the binding constraint.**

Two findings from checking rather than assuming:

- **Claude Pro cannot be the instrument.** It is a consumer subscription, not API credits — and the
  study needs 7 *different* model families with pinned IDs and logged raw responses. H3 is
  specifically the intra-model vs cross-family contrast, so a single-vendor panel cannot test it at
  all. Pro stays valuable for building the harness and doing the analysis; the measurement needs
  separate credits.
- **Local inference is largely closed** on this machine (M1, **8 GB RAM**). It reverses my earlier
  "$250 by running open-weight locally" suggestion — 8 GB runs a 3B–7B quantised model too slowly
  for a 105-day panel, and that tier isn't representative of deployed systems anyway. Open-weight
  families go to hosted inference: ~**+$40**, not a rethink, but the earlier number was wrong.

| Tier | Budget | Trade |
|---|---|---|
| Lean | $250 | 5 families, 15 tasks/day. Core N_eff survives; H1's conditional test loses most of its power |
| **Recommended** | **$700** (cap $1,000) | 7 families, 30 tasks/day. All three hypotheses adequately powered |
| Maximal | ~$2,000 | 10 families, 60 tasks/day, 5 prompt variants. Makes H3 nearly unassailable |

Prompt caching (stable 4,000-token prefix at ~0.1× reads) plus the Batch API (50% off — WS1 only
needs the call *made* before resolution, so overnight batching is fine) cut the bill ~70%.

**What money cannot buy:** 15 weeks of prospective collection cannot be purchased faster, and a week
not started is gone. Starting Week 0 next week is worth more than tripling the budget.

---

## 8. Risk register

| Risk | L | Impact | Mitigation |
|---|---|---|---|
| **Scooped** | High | High | Preprint at Week 6 on partial results; prospective dataset is not retro-buildable (§9) |
| H1 null | Med | Med | H3 + first financial $N_{\text{eff}}$ still stand alone. **No single-hypothesis dependency** |
| Provider silently updates a model mid-panel | **High** | Med | Pin + log model IDs daily; treat as covariate. Version drift inside a panel is itself a publishable finding |
| API cost overrun | Med | Low | Hard cap in code; open-weight fallback |
| Live window has no stress episode | Med | **High** | WS2 supplies historical stress; extend window if ISEF-only |
| Rate limits / outages | High | Low | Async with backoff, cache, overnight batch |
| Resolution lag | Med | Med | Weight task mix toward fast-resolving events |

The design has **no single point of failure**: three independent findings, two independent data
sources, and a theory component that stands even if an empirical arm underdelivers.

---

## 9. Scoop defence

This area is hot and we should assume someone else is circling. Three defences:

1. **The dataset cannot be built retroactively.** A prospective, pre-registered, multi-family panel
   of decisions on unresolved events is a wasting asset — a competitor starting in October cannot
   reconstruct our September observations at any price. Every day we run, the moat widens.
2. **Preprint early.** Week 6, on WS1+WS2 partial results, before WS4 is finished. Establishes
   priority on the measurement; WS4/WS5 land in v2.
3. **The conditional framing is the defensible claim.** If someone publishes an unconditional
   financial $\bar\rho$ first, our state-dependence result is *strengthened* by having their
   baseline to contrast against, not pre-empted.

---

## 10. Scoring detail

| Criterion (weight) | A | B | C |
|---|---|---|---|
| Novelty vs 2026 prior art (10) | 8 | 6 | 4 |
| Feasibility in 180 h, no institutional data (10) | 9 | 6 | 8 |
| Falsifiability / clean design (10) | 9 | 6 | 6 |
| Societal + policy significance (10) | 10 | 6 | 4 |
| Judge legibility & demo quality (5) | 4 | 3 | 3 |
| Null-result survivability (5) | 4 | 4 | 2 |
| **Total (50)** | **44** | **31** | **27** |

---

## 11. Decisions I need from you

1. **Primary venue — this sets the schedule.** STS 2027 (5 Nov, seniors only) forces the compressed
   11.4-week plan above. If the target is ISEF 2027 (regionals Jan–Mar, finals 8–14 May LA) and/or
   JSHS 2027, collection extends past 20 weeks and the paper gets materially stronger.
   *Is the student a senior applying to STS this cycle?*
2. **Budget** — approve $800 / $1,200 cap, or set lower and I shift to local open-weight inference.
3. **Confirm Program A**, or tell me to develop B or C instead.

On your go, Week 0 starts with the pre-registration document and the measurement harness — both
built and tested before a single data point is collected, so the analysis plan is frozen before we
can be tempted by the data.

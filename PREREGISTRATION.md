# Pre-Registration — Correlated Minds

**Study:** State-dependent error correlation across large language models in
financial forecasting, benchmarked against human professional forecasters.

**Status:** DRAFT — to be frozen, hashed, and registered on OSF before the first
observation is collected.
**Frozen on:** _(to be filled at registration)_
**SHA-256 of frozen version:** _(to be filled at registration)_
**Collection begins:** 24 Aug 2026 · **Calibration ends:** 27 Sep 2026 · **Data freeze:** 6 Dec 2026

> Nothing in this document may be edited after the freeze. Any change after that
> point goes in §11 as a dated, numbered deviation, with the reason. A study that
> quietly rewrites its hypotheses after seeing data is not evidence of anything.

---

## 1. Background and motivation

The Financial Stability Board (Oct 2025), the Bank of England (Jul 2026) and the
IMF (Jul 2026) have each identified correlated behaviour among financial
institutions running similar AI models as a systemic risk. Theoretical work
models the consequences of such correlation. **None of it measures the
correlation itself on financial decisions.** The metric — error correlation and
effective ensemble size — is established in general-domain work but has not been
applied to finance, and never conditionally on market state.

This study supplies that measurement.

---

## 2. What Week 0 already established, and how it changed the design

Before registering, we measured the human baseline (Philadelphia Fed Survey of
Professional Forecasters, individual responses, 2000–2026). **This produced a
finding that materially altered the hypotheses, and it is recorded here because
it was known before collection began.**

| Variable | Horizon | rho_bar (human) |
|---|---|---|
| Unemployment | 1 (nowcast) | 0.996 |
| Unemployment | 4 (3 quarters ahead) | 0.876 |
| CPI inflation | 1 (nowcast) | 0.999 |

Human forecast errors are *already* highly correlated, because errors are
dominated by the common surprise that nobody anticipated. Excluding 2020 does
not change this.

**A second calibration result then corrected the first.** The obvious fix --
correlating residuals after removing the cross-panel mean error ("excess
correlation over the common component") -- **is mathematically broken.**
Residuals sum to zero by construction, so for independent idiosyncratic parts
their pairwise correlation is exactly `-1/(M-1)`, regardless of the true
correlation. Simulation at rho_true = 0.0, 0.5, 0.9 for M = 3, 5, 7, 12 returned
`-1/(M-1)` to three decimals in every cell. That statistic carries no
information. **It appeared in an earlier draft of this document and has been
removed.**

The correct diagnosis is that raw correlation is not saturated, only badly
scaled. Writing rho = 1 - eps gives `N_eff - 1 ~ ((M-1)/M) * eps`, so the
practical benefit of ensembling is proportional to `(1 - rho)`. That quantity is
estimated to four decimal places with 400 tasks: rho = 0.996 separates from
0.990 at 7.7 sigma.

Measured human headroom, by horizon (7-forecaster matched panels):

| Variable | Horizon | rho_bar | N_eff | Headroom | Variance cut by ensembling |
|---|---|---|---|---|---|
| Unemployment | nowcast | 0.9961 | 1.003 | 0.003 | 0.3% |
| Unemployment | 3q ahead | 0.8666 | 1.126 | **0.126** | **11.2%** |
| CPI | nowcast | 0.9994 | 1.001 | 0.001 | 0.1% |
| CPI | 3q ahead | 0.9059 | 1.086 | **0.086** | **7.9%** |
| Payrolls | nowcast | 0.9975 | 1.002 | 0.002 | 0.2% |
| Real GDP | nowcast | 0.9999 | 1.000 | 0.000 | 0.0% |

**Three consequences, all incorporated below:**

1. **The primary outcome is diversification headroom, `N_eff - 1`,** reported
   alongside a model-free variance-reduction ratio. Not raw rho as a level, and
   not the residual metric.
2. **Tasks must be genuinely uncertain.** At nowcast horizons no panel -- human
   or machine -- has measurable headroom, so no comparison is possible there.
   Task selection targets the horizon-4 end, where human headroom is ~0.09-0.13.
3. **The headline claim is a RATIO of headroom**, human versus AI, because
   numbers that both "round to 1" can differ twentyfold in practical benefit.

This is exactly what a calibration phase is for, and it is disclosed rather than
discovered later.

---

## 3. Design

### 3.1 Panel
Seven model families, pinned by exact API id, logged per call: Anthropic
(Claude Sonnet 5, Claude Haiku 4.5), OpenAI (mid-tier), Google (Gemini Flash-Lite),
Meta (Llama), Alibaba (Qwen), DeepSeek. Seven families → 21 pairs. The two
Anthropic models form a deliberate **within-family control** for H3.

### 3.2 Questions
Kalshi event contracts in the Economics, Financials and Companies categories,
plus scheduled macro releases. All questions are registered **before resolution
exists**. Sampling is pinned at temperature 0 for every model.

### 3.3 Inclusion criteria (fixed in advance)
- Resolves between **3 and 120 days** after being asked.
- Resolves **on or before 6 Dec 2026**, or it is excluded from the primary analysis.
- Drawn from mid-ladder strikes where a strike ladder exists (proxy for genuine
  uncertainty, since Kalshi quotes are not public).
- **Excluded:** any question where the panel's median forecast is below 0.05 or
  above 0.95 on the first day asked. These are effectively settled and, per §2,
  compress error variance for uninteresting reasons.

### 3.4 Repeated measurement
Open questions are re-asked daily until resolution. Task-days are the unit of
observation; the repeated-measures structure is handled by the block bootstrap
(§5.2), not ignored.

---

## 4. Hypotheses

### 4.1 Primary outcome: diversification headroom

For task *t* and model *i*, error `e_it = f_it - y_t`. With mean pairwise error
correlation `rho_bar` across M forecasters:

    N_eff    = M / (1 + (M - 1) * rho_bar)
    headroom = N_eff - 1

`headroom` is the primary outcome. It is zero when the panel is worth exactly one
opinion, and near saturation it is approximately `((M-1)/M) * (1 - rho_bar)` --
linear in the quantity we can measure precisely.

Reported alongside it, always:

- **`variance_reduction`** -- the model-free ratio `Var(panel mean error) /
  mean(Var of individual errors)`. It assumes no correlation structure and simply
  measures what happens to error variance when the panel is averaged. Under
  equicorrelation it equals `1/N_eff`; **where the two diverge, the
  equicorrelation assumption is doing work and we report that divergence rather
  than concealing it.**
- **`rho_bar`** itself, to four decimal places, so nothing is hidden by scaling.

We correlate **errors, not forecasts**. Forecasters who agree because a question
had a knowable answer are not redundant; correlating errors isolates shared
*wrongness*, which is the only kind that creates systemic risk.

### H1 — Conditional collapse
`headroom` decreases (and `rho_bar` increases) with market stress and question
ambiguity. Tested as a *change* across states, which is unaffected by the level
sitting near saturation.

- **State variables (fixed, no additions permitted):** VIX level, 20-day realised
  volatility, cross-model forecast dispersion, |macro surprise|, days-to-resolution,
  novelty score.
- **Test:** regression of pairwise error products on standardised state
  variables with task-clustered standard errors; and comparison of `headroom`
  between top and bottom stress terciles with a block-bootstrap interval, on the
  `headroom` scale.
- **Correction:** Benjamini–Hochberg at FDR 0.05 across the six state variables.
- **FALSIFIED IF:** no state variable shows a positive, BH-surviving coefficient,
  and the tercile difference interval contains zero.

### H2 — Shared-prior mechanism
The collapse is driven by convergence on shared priors when evidence is weak.

- **Test:** on the 10% extended-reasoning subsample, in the top ambiguity
  tercile, (a) cross-model rationale similarity rises, and (b) the panel median
  forecast becomes less sensitive to question-specific evidence and closer to the
  category base rate.
- **FALSIFIED IF:** evidence-sensitivity does not differ across ambiguity terciles.

### H3 — The diversification illusion
Intra-model diversity buys materially less independence than cross-family diversity.

- **Test:** `N_eff` for (a) one model under 5 prompt variants, (b) two models from
  the same family, (c) two models from different families — matched on panel size.
- **FALSIFIED IF:** the intra-model and cross-family `N_eff` intervals overlap.

### H4 — Human comparison (confirmatory) — the headline
On matched questions and matched panel size (M = 7), **AI diversification
headroom is smaller than human headroom**, i.e.

    headroom_ratio = headroom(humans) / headroom(AI)  >  1

Human benchmarks are already measured (section 2): headroom 0.126 for
unemployment and 0.086 for CPI at three quarters ahead.

- **Matching:** SPF variables (unemployment, CPI, payrolls, GDP) at horizons whose
  uncertainty is comparable to our questions; human panels subsampled to 7 over
  500 random draws.
- **Reported regardless of direction.** If AI is *less* correlated than humans,
  that is a genuinely reassuring result and will be reported with equal emphasis.

---

## 5. Analysis plan (fixed before data)

### 5.1 Estimator
`N_eff = M / (1 + (M − 1) · rho_bar)`, correlating **errors, not forecasts**.
Missing observations handled pairwise; tasks are never dropped listwise, because
model failures cluster on busy market days.

### 5.2 Uncertainty
Moving-block bootstrap, block size 5 task-days, 2000 resamples, percentile
intervals. Blocks rather than i.i.d. resampling because task-days are serially
dependent; an ordinary bootstrap would understate uncertainty.

### 5.3 The out-of-sample prediction
On **27 Sep 2026** (end of Week 5) we fit H1 on weeks 1–5, then publish a hashed,
timestamped numerical prediction of the form:

> "On the next macro release with |surprise| above the 80th percentile,
> `headroom` will fall below X and `rho_bar` will exceed Y."

Weeks 6–15 are a genuine holdout. The prediction is never revised. A miss is
reported as a miss.

### 5.4 Exclusions
Observations with `error` set are excluded from estimation but **counted and
reported**. If usable coverage falls below 80% for any model, that model is
reported separately and excluded from the primary panel.

---

## 6. Sample size

Target ≈ 25 task-days × 7 models × 105 days ≈ 18,375 observations. Powering the
tercile contrast in H1 requires roughly 300 task-days per stress tercile; the
target provides ~600, giving headroom for attrition.

---

## 7. What would make us abandon a hypothesis

- **H1:** stated in §4. A null is publishable and will be published.
- **H4:** if matched questions turn out to have negligible headroom for humans
  too, we report the comparison as uninformative rather than straining for a
  difference. Section 2 shows this is a real risk at short horizons, which is
  precisely why task selection targets longer ones.
- **Whole study:** if usable coverage falls below 50% across the panel, we report
  a methods paper on why multi-provider panels are hard to run, and say so plainly.

---

## 8. Data and code availability

All code is public from day one. Observations, tasks and resolutions are
append-only JSONL committed daily by an automated job, which makes the
"registered before resolution" claim externally checkable rather than asserted.

---

## 9. Researcher degrees of freedom we are giving up

Fixed in advance and not revisable after the freeze: the model roster; sampling
temperature; the six state variables; the primary outcome; the block-bootstrap
parameters; the inclusion criteria; the multiple-testing correction; the
prediction date.

---

## 10. Known limitations

1. Kalshi quotes are not public, so the market-implied benchmark comes from
   Polymarket where topics overlap, and is unavailable for most questions.
2. Mid-tier models are used for cost reasons. This mirrors real high-volume
   deployment but is not the frontier; the Sonnet anchor partially addresses it.
3. The representation-level arm (CKA) is deferred to Year 2 — 8 GB of local RAM
   cannot run it at a defensible scale.
4. Providers may update models mid-panel. We log the served id every call and
   report drift; we cannot prevent it.
5. 15 weeks may contain no genuine market stress event. The graded ambiguity
   variation partly substitutes, but a real shock cannot be manufactured.

---

## 11. Deviations from this plan

_(Numbered and dated. Empty at registration.)_

| # | Date | Deviation | Reason |
|---|---|---|---|
| — | — | — | — |

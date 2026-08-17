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

**Three consequences, all incorporated below:**

1. **A naive "AI is more correlated than humans" hypothesis is untestable at
   short horizons** — the metric saturates near 1.0 for humans, leaving no room.
   H1 is therefore specified on *genuinely uncertain* questions only.
2. **Raw error correlation is the wrong primary outcome.** We pre-specify
   **excess correlation over the common component** (§4.1) as primary, with raw
   rho_bar reported as secondary.
3. **Task selection must exclude near-settled questions** (§3.3).

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

### 4.1 Primary outcome: excess correlation

For task *t* and models *i*, error `e_it = f_it − y_t`. Decompose

    e_it = c_t + u_it

where `c_t` is the cross-model mean error on task *t* (the common surprise, which
no forecaster could avoid) and `u_it` is the idiosyncratic residual.

**Excess correlation** is the mean pairwise correlation of `u_it`, and

    N_eff_excess = M / (1 + (M − 1) · rho_excess)

This isolates redundancy that is *not* explained by the question simply being
hard — which is the quantity relevant to systemic risk, and the one that does not
saturate.

### H1 — Conditional collapse
`rho_excess` increases, and `N_eff_excess` decreases, with market stress and
question ambiguity.

- **State variables (fixed, no additions permitted):** VIX level, 20-day realised
  volatility, cross-model forecast dispersion, |macro surprise|, days-to-resolution,
  novelty score.
- **Test:** regression of pairwise error products on standardised state
  variables with task-clustered standard errors; and comparison of `rho_excess`
  between top and bottom stress terciles with a block-bootstrap interval.
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

### H4 — Human comparison (confirmatory)
On matched questions and matched panel size (M = 7), `rho_excess` is higher for
the AI panel than for SPF human forecasters.

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
> `rho_excess` will exceed X and `N_eff_excess` will fall below Y."

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
- **H4:** if human `rho_excess` also saturates on matched questions, we report the
  comparison as uninformative rather than straining for a difference.
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

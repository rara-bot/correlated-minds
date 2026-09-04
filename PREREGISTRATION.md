# Pre-Registration — Correlated Minds

**Study:** State-dependent error correlation across large language models in
financial forecasting, benchmarked against human professional forecasters.

**Status:** FROZEN. No edits permitted; changes go in section 11 as dated deviations.
**Frozen on:** 2026-08-29 03:54 UTC
**SHA-256 of frozen version:** `90a7e7de5980a80bef786e87b938495d7a08e10234032a11c5d67e8ce1c70009`
**Collection begins:** 29 Aug 2026 · **Calibration ends:** 2 Oct 2026 · **Data freeze:** 11 Dec 2026

> Nothing in this document may be edited after the freeze. Any change after that
> point goes in §11 as a dated, numbered deviation, with the reason. A study that
> quietly rewrites its hypotheses after seeing data is not evidence of anything.

---

## 1. Background and motivation

The Financial Stability Board (*Monitoring Adoption of Artificial Intelligence
and Related Vulnerabilities in the Financial Sector*, 10 Oct 2025; building on
its 2024 report, which names market correlation as a vulnerability), the Bank of
England and the IMF have each identified correlated behaviour among financial
institutions running similar AI models as a systemic risk.

**An earlier draft of this document claimed nobody has measured this. That claim
was false, and it is withdrawn.** A literature check on 17 Aug 2026, before
collection, found four papers measuring LLM error correlation directly:

| Work | What it measured | Result | What it did not do |
|---|---|---|---|
| Kim et al., *Correlated Errors in LLMs*, ICML 2025 (arXiv 2506.07962) | 350+ models, general benchmarks | agree ~60% of the time when both err; larger/more accurate models correlate MORE | not finance, not prospective, no human panel, no state-dependence |
| *The Oracle's Fingerprint* (arXiv 2605.00844) | GPT-4o / Claude / Gemini on **568 already-resolved** binary questions | r = 0.77 (0.78 excluding likely-leaked items) | retrospective; general forecasting; no conditional test — its own stated gap is *"a monoculture built but not yet activated"* |
| *Preference Optimization Drives Monoculture in LLM Prediction Markets* (arXiv 2606.26583) | simulated DPO-tuned agents, 8B/70B | rho = 0.70; **10 agents ≈ 1.4 effective**; cross-model diversity cuts rho 0.68 → 0.40 | simulation, not live markets; no humans; no state-dependence |
| *Nine Judges, Two Effective Votes* (arXiv 2605.29800) | LLM-as-judge panels | 9 judges ≈ 2 effective votes | evaluation, not forecasting; no state-dependence |

Two consequences we accept rather than argue with:

1. **The headline number in our own pitch — "seven AI systems behave like about
   1.4" — is already in the literature and must be retired from our framing** (arXiv 2606.26583, for ten simulated
   agents). We must not present that figure as our discovery. Our contribution is
   not the existence of correlation; it is the *conditions under which it moves*.
2. **The level of correlation is not novel. Five things about this design still
   are**, and they define the contribution:

   - **Prospective and pre-registered.** Every existing measurement is either
     retrospective on already-resolved questions — where contamination is a live
     concern the authors themselves flag — or simulated. Here the outcome does
     not exist when the question is asked, so contamination is impossible by
     construction rather than by argument.
   - **Conditional on market state (H1).** No published work measures whether
     correlation *rises* under stress or ambiguity. The closest paper names this
     as the priority open question in its own conclusion. This is our primary
     hypothesis.
   - **A structurally matched human benchmark (H4).** No existing work compares
     LLM error correlation to individual human professionals producing the same
     object. SPF RECESS — individual probability forecasts of a binary event —
     makes that possible (§2.3).
   - **Capability-controlled (H6).** arXiv 2607.20768 shows diversity metrics are
     mostly a restatement of accuracy (Spearman rho = +0.99 against one minus
     mean accuracy). Any correlation finding that does not control for capability
     is not interpretable. We register the control in advance.
   - **Document-grounded finance tasks** whose targets are quarters not yet
     filed.

This study supplies the conditional, capability-controlled, human-benchmarked
measurement. It does not claim to be the first to observe that LLMs err together.

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

### 2.1 A units bug in that first measurement, found and fixed before freeze

Re-verifying the above on 17 Aug 2026 revealed that two of the four series were
scored against the wrong object. SPF reports CPI as an **annualised inflation
rate** (~2.7) and was being differenced against the **CPI index level** (~333);
SPF reports real GDP as a **level in the chain base current at survey time** and
was being differenced against a 2017-base series. Measured damage on 2000+ data:

| Series | median abs error | rho_bar | verdict |
|---|---|---|---|
| CPI h=1, as originally coded | **229.07** | **1.0000** | artifact |
| RGDP h=1, as originally coded | **3488.46** | **1.0000** | artifact |

Both produced a *perfect* correlation manufactured entirely by a units mismatch,
in the numbers that set this study's human benchmark. Corrected — comparing
annualised growth to annualised growth, which is invariant to the index base —
CPI h=4 headroom moves from 0.0047 to **0.0797**, a 17-fold change in a quantity
that appears in the headline comparison.

**Corrected human baselines (2000+, matched to the AI panel size M = 9):**

| Variable | h=2 rho_bar | h=2 headroom | h=4 rho_bar | h=4 headroom |
|---|---|---|---|---|
| Unemployment | 0.9026 | 0.0976 | 0.8760 | 0.1297 |
| CPI inflation | 0.8397 | 0.1688 | 0.9169 | 0.0826 |
| Real GDP | 0.8982 | 0.1050 | 0.9100 | 0.0942 |
| Payrolls | 0.8215 | 0.1915 | 0.8249 | 0.1903 |

The design conclusion survives and sharpens: **nowcasts saturate** (unemployment
h=1: rho 0.9960, headroom 0.0041) but **every horizon from h=2 out carries
measurable human headroom of roughly 0.08–0.19.** Task selection targets that band.

### 2.2 Why the old comparison was structurally unfair, in both directions

Our models emit a **probability of a binary event** (error `p − y`, `y ∈ {0,1}`);
SPF point forecasts are **continuous levels**. Headroom is approximately
`tau^2 / (sigma_c^2 + tau^2)` — the share of error variance that is
idiosyncratic — and the mechanical floor of `sigma_c^2` is not the same for a
Bernoulli outcome as for a continuous one. Comparing across that gap invites the
obvious objection that any human-versus-AI difference is a task-format artifact.

### 2.3 The fix: a structurally matched human panel (SPF RECESS)

Every quarter since 1968 the SPF asks each panelist for the **probability that
real GDP will decline** in the survey quarter and each of the next four. That is
a probability forecast of a binary event, at the individual level, resolved by
the national accounts — the same object our models produce, scored the same way,
by the professionals they are said to replace.

Measured (2000+, 106 quarterly rounds, ~31 forecasters per round, 13% base rate):

| Horizon | rho_bar | headroom @ M=9 | 95% CI |
|---|---|---|---|
| 1 (survey quarter) | 0.8417 | **0.1710** | [0.076, 0.356] |
| 2 | 0.8864 | 0.1206 | [0.044, 0.288] |
| 3 | 0.8949 | 0.1120 | [0.038, 0.288] |
| 4 | 0.8906 | 0.1222 | [0.028, 0.311] |
| 5 | 0.8844 | 0.1347 | [0.029, 0.393] |

**This is the primary human benchmark for H4.** That it lands in the same
0.08–0.19 band as the corrected point-forecast baselines, by a completely
different route, is the main reason we believe the corrected numbers.

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
estimated precisely with 400 tasks. Simulated separation of rho = 0.996 from
rho = 0.990 at M = 7, T = 400, by the serial dependence of the common component:

| AR(1) in the common component | separation |
|---|---|
| 0.0 (i.i.d. tasks) | 10.4 sigma |
| 0.5 | 8.3 sigma |
| 0.8 (strong) | 5.3 sigma |

An earlier draft quoted "7.7 sigma" with no dependence assumption stated. Because
questions are re-asked daily, tasks are *not* i.i.d.; **the honest figure is
"at least 5 sigma even under strong serial dependence."**

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
3. **The human-versus-AI comparison is reported as a bounded difference in
   variance reduction, not as a ratio** (§5.5), because a ratio whose
   denominator approaches zero is not a reportable headline.

This is exactly what a calibration phase is for, and it is disclosed rather than
discovered later.

---

## 3. Design

### 3.1 Panel

**Nine models across six vendor families** in the primary panel → **36 pairs**,
of which **three are within-family**. Every id below is the exact string sent to
the API, and the id the API *returns* is logged on every single call, so a
mid-panel vendor swap is detectable rather than merely disclaimed.

| # | key | provider | pinned API id | family | tier | panel |
|---|---|---|---|---|---|---|
| 1 | `claude_sonnet` | anthropic | `claude-sonnet-4-6` | anthropic | frontier | primary |
| 2 | `claude_haiku` | anthropic | `claude-haiku-4-5-20251001` | anthropic | mid | primary |
| 3 | `gpt_mid` | openai | `gpt-4.1-mini-2025-04-14` | openai | mid | primary |
| 4 | `gpt_small` | openai | `gpt-4.1-nano-2025-04-14` | openai | small | primary |
| 5 | `gemini_flash_pro` | google | `gemini-3.5-flash` | google | mid | primary |
| 6 | `gemini_flash` | google | `gemini-3.5-flash-lite` | google | small | primary |
| 7 | `llama` | openrouter | `meta-llama/llama-3.3-70b-instruct` | meta | mid | primary |
| 8 | `qwen` | openrouter | `qwen/qwen-2.5-72b-instruct` | alibaba | mid | primary |
| 9 | `deepseek` | openrouter | `deepseek/deepseek-v3.2` | deepseek | mid | primary |
| 10 | `gpt_frontier` | openai | `gpt-4.1-2025-04-14` | openai | frontier | **secondary** |

This table is the registered roster. `tests/test_roster.py` asserts it matches
`neff/config.py` exactly, so the document and the code cannot drift apart after
the freeze without a test failing.

**The frontier anchor is Sonnet 4.6, not Sonnet 5, and that is deliberate.**
`claude-sonnet-5` rejects the `temperature` parameter outright (HTTP 400,
*"temperature is deprecated for this model"*). §9 registers `TEMPERATURE = 0.0`
as a frozen commitment, so a panel member that cannot honour it would sample
adaptively while the other eight sampled at 0 — mixing a model difference with a
sampling difference on precisely the member H6 leans on for its capability
contrast. Sonnet 4.6 is the newest Anthropic model that still accepts the
parameter, at identical $3/$15 pricing, same family, same tier. Verified by live
call at `temperature=0`. The same constraint disqualified OpenAI's gpt-5 line
(see §5.4).

**The tenth model is collected but is not in the primary panel.** `gpt_frontier`
is queried every day alongside the nine and appears in the public logs, and it is
declared here so that a reader comparing the logs against this registration finds
ten model ids and an explanation rather than an undeclared extra arm. It is
**excluded from every primary estimate**, for a stated reason: H4 matches human
forecasters at M = 9 against SPF RECESS headroom measured at that same panel
size (0.112–0.171), and folding a tenth member in would make the AI panel M = 10
and silently unmatch the comparison. The exclusion is enforced in code —
`config.primary_panel()` returns the nine, and `panel.load_panel()` reads from
that function, not from the collected roster.

Its purpose is a confound the primary panel cannot address: the primary panel
holds exactly **one** frontier model, and it is Anthropic, so at the frontier
tier "capability" is perfectly confounded with "family" and *frontier models
behave differently* cannot be distinguished from *Anthropic behaves differently*.
A second frontier model from a different existing family breaks that confound.
It is registered now rather than added later because §9 freezes the roster and a
day not collected cannot be recollected, whereas a model collected and not needed
can simply be ignored. Any analysis using it is **exploratory and labelled as
such**, reported separately from the confirmatory results, and the primary
results stand or fall without it.

**Why three within-family pairs and not one.** H3 and H6 rest entirely on the
within-family contrast. With a single within-family pair (the original
seven-model panel) that contrast is close to undecidable:

- Cluster-robust inference is invalid. Clustering is by pair, so the
  `same_family` coefficient's variance would come from one cluster. Tested on
  synthetic data containing **no family structure at all**, the clustered
  t-statistic returned **+7.06** and declared the effect real — a false positive
  manufactured by the estimator, not by the data.
- The valid alternative, an exact permutation test over family labels, admits
  only C(7,2) = 21 distinct labelings, so its **best achievable p-value was
  1/21 = 0.048** — a headline hypothesis whose ceiling is the threshold.

Three within-family pairs (Anthropic, OpenAI, Google), each the same vendor at a
different tier so the pairs are structurally comparable, drop the permutation
floor below 0.001. Marginal cost is roughly $7 on a $30 study.

The panel is chosen to span **pretraining lineage**, which is the level at which
the shared-prior hypothesis lives, not to replicate any one institution's vendor
stack. These six families are the near-entirety of the 2026 enterprise supply;
firms reach them through resale channels (Azure OpenAI, AWS Bedrock, Google
Vertex) that serve the same weights under a different invoice. Rationale and
limitations: `VALIDITY.md` §4.

### 3.2 Questions — two registered task types

The daily battery is **60% macro / 40% filing**, fixed in advance. All questions
of both types are registered **before resolution exists**. Sampling is pinned at
temperature 0 for every model.

**Type A — macro (60%).** Kalshi event contracts in the Economics, Financials and
Companies categories, plus scheduled macro releases. Ground truth is the official
statistical release. This type carries the human benchmark: it is directly
matchable to the Philadelphia Fed Survey of Professional Forecasters, so **H4 is
estimated on Type A only.**

**Type B — document-grounded filing tasks (40%).** The model is given a company's
own historical financials from SEC EDGAR XBRL and asked to judge a threshold
question about its **next reported quarter**, which has not been filed. Ground
truth is that company's subsequent XBRL filing. Rationale: document-grounded
analysis of filings is the dominant real-world deployment of language models in
finance, whereas macro forecasting is not (`VALIDITY.md` §1–§3). This type has no
human benchmark; that is the acknowledged trade-off for ecological validity.

Two design constraints on Type B are fixed here because both could manufacture a
correlation result for trivial reasons:

- **Point-in-time discipline.** History is filtered on **filing date**, never on
  period end, so a quarter that has ended but has not been reported is invisible
  to the model. Filtering on period end would leak lookahead bias.
- **Balanced thresholds.** The threshold rule was backtested on 443 historical
  questions across 11 companies before registration; pooled YES rate **54%**. A
  rule yielding, say, 90% YES would drive every model to the same answer and
  inflate measured correlation for a reason that has nothing to do with shared
  priors.

### 3.3 Inclusion criteria (fixed in advance)
- Resolves between **3 and 120 days** after being asked.
- Resolves **on or before 11 Dec 2026**, or it is excluded from the primary analysis.
- Drawn from mid-ladder strikes where a strike ladder exists (proxy for genuine
  uncertainty, since Kalshi quotes are not public).
- **Excluded:** any question where the panel's median forecast is below 0.05 or
  above 0.95 on the first day asked. These are effectively settled and, per §2,
  compress error variance for uninteresting reasons.

For Type B additionally, fixed in advance:
- The target quarter must have an expected filing date **on or before 11 Dec 2026**.
- The company must have at least 8 usable point-in-time quarters of history under
  a single current XBRL tag.
- Quarters reconstructed by the identity `annual − (Q1+Q2+Q3)` are **flagged as
  derived** and carried in the primary analysis; a sensitivity analysis excluding
  them is reported.

### 3.4 Repeated measurement
Open questions are re-asked daily until resolution. Task-days are the unit of
observation; the repeated-measures structure is handled by the block bootstrap
(§5.2), not ignored.

### 3.5 Data collected before this registration — the pilot arm

**Real forecasts were collected on 21 and 22 Aug 2026, before this document was
frozen, and they are public.** They are declared here for the same reason §3.1
declares the tenth model: a reader comparing the public log against this
registration will find observations timestamped *before* it, and should find an
accounting rather than an undeclared arm.

Its exact extent, as at the moment of freezing — no further pilot day was
collected after this document was hashed:

| | |
|---|---|
| Tasks | 16 (10 macro event, 6 filing), 8 asked on each day |
| Observations | 180 — 160 at prompt variant 0, 20 at the reserved replicate variant 99 |
| Models | all ten collected, i.e. the registered nine plus `gpt_frontier` |
| Billed API calls | 208, all ledgered under `arm = "pilot"` |
| Recorded cost | $0.1224 |

The ledger reconciles against that table exactly, and a reader can check it from
the public files: **208 billed calls = 180 stored observations + 30 verification
calls (`neff.verify`, run three times) − 2 provider failures that were never
billed.** Synthetic `--mock` rows are archived under `data/pilot_mock/` and are
not in the ledger; the reconciliation above is how we found that a mock run had
booked $0.0102 of spend that never happened, and `tests/test_mock_never_bills.py`
now makes that impossible.

Its purpose was to establish that the instrument runs end to end against live
APIs before anything was committed to: that every pinned model id answers, that a
full day completes, and that measured cost matches the projection the arm cap is
set against. It did its job — defects it exposed are recorded in `AUDIT.md`,
including a Google billing tier that would have failed on day one.

**The pilot is excluded from every primary estimate**, and from every hypothesis
in §4. It is not a preliminary result and no claim rests on it; it is an
instrument check.

The exclusion is enforced in code rather than by intention, and the mechanism is
worth stating precisely because the pilot rows are *not* self-describing. Tasks
and observations now carry an `arm` field, and `panel.load_panel` is fail-closed:
it admits a row only if that row carries the registered arm. The pilot rows
predate the field and therefore carry no label at all — the store is append-only,
so they are excluded on read rather than rewritten to add one. An unlabelled row
is read as pilot, which is what it is: every one of the 228 pre-registration
ledger entries is `arm = "pilot"`. The property that matters holds in both
directions — nothing unlabelled can satisfy the primary arm, and asking for the
pilot explicitly still reaches it. Should we ever report anything from it, it is
**exploratory and labelled as such**, exactly as for the tenth model.

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

### 4.2 Co-primary: the same quantity on the uncentered scale

**Pearson correlation subtracts each forecaster's own mean error, so a bias the
whole panel shares is differenced away.** "Every model wrong in the same
direction" is precisely the failure this study exists to measure, so an
estimator blind to it cannot be the sole primary. Simulated at M = 7, T = 400,
independent idiosyncratic errors plus a common bias `b` added to all seven:

| common bias | Pearson rho | Pearson headroom | true N_eff (MSE) |
|---|---|---|---|
| 0.00 | +0.016 | 5.40 | 6.38 |
| 0.10 | −0.008 | 6.35 | 3.27 |
| 0.20 | +0.010 | 5.59 | 1.70 |
| 0.30 | +0.013 | 5.49 | 1.37 |

Pearson reports "seven nearly independent minds" at every bias level while the
panel is in fact collapsing to one. The registered `variance_reduction` is
centred too and is equally blind.

We therefore report, always and together:

- **`n_eff_mse` = mean_i MSE_i / MSE(panel mean)** — model-free, assumes neither
  equicorrelation nor zero bias. **This is the primary for the systemic-risk
  claim**, because it answers the operational question directly: by what factor
  does averaging this panel actually reduce squared error?
- **`rho_bar` and `headroom` (Pearson)** — kept because it is what the existing
  literature reports, so our numbers remain comparable to arXiv 2506.07962,
  2605.00844 and 2606.26583.
- **The gap between them.** Where the two diverge, the divergence *is* the
  shared-bias finding and is reported as such, not smoothed over.

### H1 — Conditional collapse — **PRIMARY HYPOTHESIS**
`headroom` decreases (and `rho_bar` increases) with market stress and question
ambiguity. Tested as a *change* across states, which is unaffected by the level
sitting near saturation.

**Why this is the primary, and not the human comparison.** H1 is a *within-panel*
contrast: the same nine models, the same questions, split by market state.
Model capability is held constant by construction. That matters because arXiv
2607.20768 shows cross-model correlation findings are largely a restatement of
model accuracy — a confound that undermines every *between*-panel comparison,
including our own H4. H1 cannot be explained that way: capability does not change
between Tuesday and Thursday. It is also the question the closest prior work
(arXiv 2605.00844) explicitly leaves open.

- **State variables (fixed, no additions permitted):** ladder distance, VIX level,
  20-day realised volatility, cross-model forecast dispersion, |macro surprise|,
  days-to-resolution, novelty score. **Seven**, and that count is the
  Benjamini–Hochberg denominator below. Four are recorded at ask time
  (`ladder_distance`, `vix_level`, `realized_vol_20d`, `days_out`) because they
  describe the world as it stood when the question was put and cannot be
  reconstructed afterwards; three are derived at analysis time from data already
  retained (cross-model dispersion from the panel's own forecasts, |macro
  surprise| from FRED vintages, novelty against the accumulated task corpus).
  The split is enforced in `config.STATE_COLLECTED_AT_ASK`.

- **Ambiguity is varied by design, not merely observed.** The single largest risk
  to H1 is that 15 weeks contain no genuine market stress event, leaving the
  hypothesis with no variation to consume. Market stress is not ours to
  manufacture — but *question* ambiguity is. Kalshi's strike ladders let us
  sample graded positions across each ladder's interior, and `ladder_distance`
  (normalised distance from the ladder median, in [0,1]) records where each
  question sat. This makes the ambiguity leg of H1 **partly experimental rather
  than purely observational**, and unlike VIX it is populated on every single day
  of collection regardless of what markets do. Extremes remain excluded by the
  [0.05, 0.95] rule in §3.3, so widening the range does not admit foregone
  conclusions. The VIX and realised-volatility legs remain observational and may
  simply fail to vary; that is disclosed here rather than discovered in December.
- **`ambiguity` is defined once, here, and used wherever this document says
  "ambiguity":** `ambiguity = 1 - ladder_distance`, so that a higher value means
  a question sat closer to the ladder median and was therefore *more* ambiguous.
  The definition is stated because `ladder_distance` runs the other way, and a
  tercile contrast built on the raw variable would invert the predicted sign of
  every ambiguity test in this document.
- **Test.** Two parts, both reported, and the variable forming each contrast is
  named here rather than chosen later:
  1. Regression of pairwise error products on the seven standardised state
     variables, with task-clustered standard errors.
  2. Comparison of `headroom` between the top and bottom terciles of **`vix_level`**
     (the stress leg) and, separately, of **`ambiguity`** (the ambiguity leg),
     each with a block-bootstrap interval on the `headroom` scale. H1 predicts
     **lower** `headroom` in the top tercile of each.

  Naming the two variables in advance matters more than it looks. Seven
  registered state variables could each form a tercile contrast, and two of them
  run in the opposite direction; leaving "stress terciles" undefined would have
  left the choice of contrast — and its sign — to be made after seeing the data,
  which is the specific freedom this document exists to give up. The stress leg
  may fail to vary in a calm 15 weeks (§10, limitation 5); the ambiguity leg is populated
  every day, which is why both are registered rather than one.
- **Registered direction, per state variable.** The seven do not all point the
  same way: two of them *fall* as ambiguity rises. A clause worded on the raw
  sign of the coefficient would therefore credit a contradiction of H1 and
  discard a confirmation of it, so the predicted direction is fixed here, before
  any data exists. Signs are for the regression of pairwise error products on the
  standardised variable.

  | State variable | A higher value means | H1 predicts |
  |---|---|---|
  | `ladder_distance` | strike sits further from the ladder median — **less** ambiguous | **negative** |
  | `vix_level` | more market stress | positive |
  | `realized_vol_20d` | more market stress | positive |
  | `expectation_dispersion` | the panel disagrees more | **negative** |
  | `abs_surprise` | the release surprised consensus by more | positive |
  | `days_out` | longer horizon, less resolved information | positive |
  | `novelty_score` | the question resembles nothing in the accumulated corpus | positive |

  **`days_out` is the one direction our own Week-0 data argues with, so it is
  registered with that argument on the record.** The corrected point-forecast
  baselines in §2.1 show human `rho_bar` *falling* as the horizon lengthens
  (unemployment 0.996 at nowcast against 0.876 at three quarters out) — the
  opposite sign. The structurally matched panel disagrees with them: SPF RECESS
  (§2.3), which is individual *probability* forecasts of a *binary* event and so
  is the same object our models produce, has `rho_bar` *rising* from 0.8417 at
  h=1 to 0.8949 at h=3. We register **positive** because RECESS is the matched
  object and the point forecasts are not, but the contrary evidence is named here
  so that a negative coefficient is a result we anticipated rather than one we
  explain afterwards.

  `expectation_dispersion` is retained because §9 fixes the seven and the count
  sets the BH denominator, but it is reported as **descriptive, not evidential**:
  `rho ~ sigma_c^2 / (sigma_c^2 + tau^2)` and cross-model dispersion *is* `tau^2`,
  so it is close to a transform of the dependent variable and would move in the
  registered direction almost mechanically. It cannot support H1 on its own.
- **Correction:** Benjamini–Hochberg at FDR 0.05 across the seven state variables.
- **FALSIFIED IF:** no state variable shows a BH-surviving coefficient **in the
  direction registered above**, *and* neither tercile contrast shows lower
  `headroom` in its top tercile with an interval excluding zero. A coefficient
  surviving correction in the *opposite* direction to the one registered counts
  against H1, not for it. If the stress leg has no usable variation, it is
  reported as untested rather than as a null, and the ambiguity leg carries the
  test (§10, limitation 5).

### H2 — Shared-prior mechanism
The collapse is driven by convergence on shared priors when evidence is weak.

- **Confirmatory test — base-rate convergence.** The panel median forecast moves
  closer to the category base rate as ambiguity rises: mean |panel median − base
  rate| is compared across terciles of **`ambiguity`** — as defined in H1, i.e.
  `1 - ladder_distance`, higher meaning more ambiguous — with a block-bootstrap
  interval on the top-minus-bottom difference. Measurable from forecasts alone —
  no text analysis, no judgement calls from us.
- **FALSIFIED IF:** the top-minus-bottom tercile difference in mean |panel
  median − base rate| is not negative with an interval excluding zero. Negative
  is the direction that confirms H2: the *most* ambiguous tercile sits *closer*
  to the base rate.
- **DEMOTED TO EXPLORATORY — rationale similarity.** The original plan also
  registered "cross-model rationale similarity rises" as confirmatory. Doing that
  honestly requires sentence embeddings plus a validation study of its own, and
  our rationales are capped at 25 words — thin evidence for a confirmatory claim.
  It is reported as exploratory and labelled as such. A registered analysis with
  no method is a promise, not a hypothesis.

### H3 — The diversification illusion
Intra-model diversity buys materially less independence than cross-family diversity.

- **Test:** `N_eff` for (a) one model under 5 prompt variants, (b) the three
  within-family pairs, (c) family-matched cross-family pairs — matched on panel
  size, with permutation inference.
- **FALSIFIED IF:** the intra-model and cross-family `N_eff` intervals overlap.

### H4 — Human comparison (confirmatory secondary)
On matched questions and matched panel size (M = 9), **AI diversification
headroom is smaller than human headroom**, i.e.

    benefit(humans) - benefit(AI)  >  0     [bounded; see 5.5]

**Primary human benchmark: SPF RECESS** (§2.3) — individual probability forecasts
of a binary event, structurally identical to our task. Measured headroom at
M = 9 is 0.112–0.171 across horizons 1–5. Corrected point-forecast baselines (§2.1)
serve as a secondary check and land in the same band (0.083–0.192).

**Accuracy control is mandatory here.** A panel can show low headroom simply by
being accurate: as forecasters converge on the true posterior, disagreement
`tau^2` shrinks while the irreducible common component `sigma_c^2` does not, so
`rho` rises. We therefore never report a human-versus-AI headroom difference
without reporting both panels' Brier scores, and we report the comparison
**at matched accuracy** — restricting the human panel to the accuracy stratum
closest to the AI panel's — as the confirmatory form of the test. If AI and human
accuracy do not overlap on matched questions, we report the comparison as
confounded and say so, rather than presenting it as clean.

- **Matching:** human panels subsampled to **M = 9**, the AI panel size, over 500
  random draws, so no part of the difference is a panel-size artifact. Matched
  human headroom on SPF RECESS at M = 9: 0.112–0.171 across horizons 1–5.
- **Reported regardless of direction.** If AI is *less* correlated than humans,
  that is a genuinely reassuring result and will be reported with equal emphasis.

**Estimated on Type A (macro) tasks only**, since the SPF has no filing-task
analogue.

### H5 — Task-format invariance (registered secondary)
Error correlation is a property of the models, not of one question format.

    headroom(Type A) ~= headroom(Type B)

Registered now rather than observed later, because the two task types were built
for different reasons and the contrast is informative in **either** direction: if
headroom is similar, the result generalises beyond the format we happened to
choose; if it differs sharply, format is a moderator and that is itself a finding
worth reporting.

- **Test:** headroom estimated separately by task type, block-bootstrap interval
  on the difference.
- **Reported regardless of direction.** No falsification clause: this is a
  descriptive contrast, not a directional claim.

### H6 — Lineage, not capability (registered confound control)
Measured error correlation reflects shared pretraining lineage over and above
shared capability.

arXiv 2607.20768 audited five diversity metrics across 31,900 subsets of 30 LLMs
and found them "heavily entangled with accuracy rather than measuring true
complementarity" (Spearman rho = +0.99 against one minus mean accuracy). Under
that critique, a raw finding that our nine models correlate is uninterpretable:
it may say only that they are all good.

- **Test:** regress pairwise error correlation on (a) a `same_family` indicator,
  (b) the pair's mean Brier skill score, (c) the absolute difference in the
  pair's Brier skill. **Inference is by exact permutation over family labels
  (family sizes held fixed), not by the cluster-robust t-statistic** — see §3.1
  for why the latter is invalid here. The lineage claim requires the same-family
  correlation gap to survive with the capability terms in the model.
- **Also reported:** correlation within accuracy-matched pairs drawn from
  different families versus the same family.
- **FALSIFIED IF:** the `same_family` coefficient is not distinguishable from
  zero once the capability terms are included. In that case we report that the
  measured correlation is a capability phenomenon, not a lineage phenomenon,
  and H3 is reinterpreted accordingly.

This hypothesis can overturn the study's framing. It is registered because a
result that survives it is worth far more than one that never faced it.

---

## 5. Analysis plan (fixed before data)

### 5.1 Estimator
`N_eff = M / (1 + (M − 1) · rho_bar)`, correlating **errors, not forecasts**.
Missing observations handled pairwise; tasks are never dropped listwise, because
model failures cluster on busy market days.

### 5.2 Uncertainty
Moving-block bootstrap, **block size 5 task-days**, 2000 resamples, percentile
intervals. Blocks rather than i.i.d. resampling because task-days are serially
dependent; an ordinary bootstrap would understate uncertainty.

**"Task-day" is the resampling unit, and it is not a row.** The panel carries ~25
tasks per day, and open questions are re-asked daily until they resolve, so one
question's successive observations sit ~25 rows apart. A block is therefore five
consecutive **days**, and every task belonging to a sampled day is resampled with
it; a block never splits a day. Blocking five *rows* instead would lie strictly
inside a single day, could never span two observations of the same question, and
would understate every interval by roughly half (measured: 0.0038 vs 0.0089 at the
real panel shape). Enforced by `stats._moving_block_indices`, which takes the day
labels explicitly rather than inferring them from row position.

**A day-block does not capture every dependence in this design, and the second
interval is registered now rather than added later.** Many questions share one
underlying resolution event — every strike on a CPI ladder settles against a
single print and therefore shares a single surprise — and a question open for
weeks spans many blocks. Neither dependence is grouped by a five-day block, so
the day-blocked interval is the *optimistic* one. Alongside it we therefore
report a **cluster bootstrap resampling whole resolution events** (all task-days
of all questions sharing a `source_ref`), which is the conservative bound. Both
intervals are reported for every primary estimate, always together. Where they
disagree materially, the event-clustered interval governs the claim.

### 5.3 The out-of-sample prediction
On **2 Oct 2026** (end of Week 5) we fit H1 on weeks 1–5, then publish a hashed,
timestamped numerical prediction of the form:

> "On the next macro release with |surprise| above the 80th percentile,
> `headroom` will fall below X and `rho_bar` will exceed Y."

Weeks 6–15 are a genuine holdout. The prediction is never revised. A miss is
reported as a miss.

### 5.4 Registered measurement threats and their pre-committed handling

Three artifacts could produce our predicted result for reasons unrelated to the
hypothesis. Each has a handling rule fixed now.

**(a) Forecast granularity.** Language models emit round probabilities (0.6,
0.70, 0.75). If several models land on the *same* round number, cross-model
dispersion `tau^2` collapses and `rho` rises for a reason that is about verbal
habit, not shared priors. Simulation shows independent rounding pushes the other
way (coarse rounding *adds* idiosyncratic noise: rho 0.9741 → 0.9582 on a 0.25
grid), so the threat is specifically **shared mass points**, not rounding as such.
Pre-committed: report the full distribution of emitted values and the **exact-tie
rate** (fraction of task-days where all responding models return an identical
value); re-estimate excluding exact ties as a registered sensitivity; and for the
models exposing logprobs, re-estimate on logprob-derived probabilities.

**Logprob coverage, measured 19 Aug 2026: four models** -- `gpt_mid`, `gpt_small`,
`llama` and `deepseek`. Confirmed by live call, not assumed. `qwen` returns none in
practice and is excluded from this leg.

This number was briefly in doubt. The roster originally pinned OpenAI's gpt-5 line,
which refuses logprobs outright (*"logprobs are not supported with reasoning
models"*), leaving only two. Repinning to the gpt-4.1 family -- forced independently
by the temperature requirement in §9 -- restored logprob support and with it the
four-model coverage this paragraph assumes.

**(b) Horizon drift toward the freeze.** Eligible questions must resolve on or
before 11 Dec 2026, so the maximum available horizon shrinks by one day per day
and reaches zero at the freeze. Since §2 shows nowcasts saturate, an unmanaged
panel drifts into exactly the regime where nothing is measurable, *as the sample
grows*. Pre-committed: **long-horizon enrolment is front-loaded** — questions
resolving more than 60 days out are enrolled preferentially in weeks 1–6, since
after ~mid-October none can be enrolled at all; days-to-resolution is already a
registered H1 state variable; and all primary estimates are reported **stratified
by horizon band** (3–14, 15–45, 46–90, 91+ days) so a composition shift cannot
masquerade as a state effect.

**Horizon banding and `days_out` are Type A only.** A filing task's target is the
next quarter a company reports, and the date it will actually file is not knowable
when the question is asked, so no honest days-to-resolution exists for Type B.
Horizon-stratified estimates and the `days_out` leg of H1 are therefore computed
on macro tasks; Type B is reported as a single unbanded stratum, and the Type B
eligibility rule in §3.3 is applied to the *expected* filing quarter rather than
to a specific date. This is a limit of the task type, stated in advance, not a
result-dependent choice.

**(c) Final-vintage outcomes for the human panel.** SPF errors are scored against
current FRED vintages, not the real-time data forecasters were judged on. Data
revisions add a common error component and therefore *inflate* human `rho`. This
biases H4 **against** our own hypothesis (it shrinks human headroom, the
numerator), so we report it rather than correct it, and note the direction.

**(d) Sampling noise that `temperature = 0` does not remove.** §9 registers
`TEMPERATURE = 0.0` so that cross-model differences reflect the models rather
than our sampling. Measured on 22 Aug 2026, before collection — 3 task prompts ×
4 repetitions of an identical prompt — that holds for only **five of the ten
models collected**:

| | mean spread | max spread | stable prompts |
|---|---|---|---|
| `claude_haiku`, `gpt_mid`, `qwen`, `deepseek`, `gpt_frontier` | 0.000 | 0.000 | 3/3 |
| `claude_sonnet` | 0.033 | 0.100 | 2/3 |
| `gpt_small` | 0.033 | 0.100 | 2/3 |
| `gemini_flash_pro` | 0.033 | 0.100 | 2/3 |
| `llama` | 0.040 | 0.120 | 2/3 |
| `gemini_flash` | 0.093 | 0.170 | 0/3 |

*(spread = max − min of the emitted probability across repetitions)*

Which models vary shifts between runs, so this is infrastructure — batched
inference, and backend routing on OpenRouter — not a property of any model, and
no available parameter removes it. We do not claim determinism we cannot deliver.

**Direction of the bias.** This noise is *idiosyncratic*: uncorrelated across
models by construction. It therefore dilutes every measured pairwise correlation
and **inflates apparent independence** — `rho_bar` too low, `N_eff` and
`headroom` too high. That runs **against** this study's own hypothesis, in the
same way as (c). But unlike (c), its magnitude is measurable, so we measure it
rather than merely noting the sign.

**Pre-committed handling.** `REPLICATES_PER_DAY = 2` questions each day are put
to every model **twice, identically**, selected by a seeded draw recorded in the
public code. Replicates are stored at a reserved `prompt_variant`
(`config.REPLICATE_VARIANT = 99`), outside H3's registered range of 0–4, and are
excluded from the primary panel by construction — `panel.load_panel` filters to
variant 0. From them we report, for every model:

- the **noise floor**, the standard deviation of a model's own disagreement with
  itself, in probability units; and
- **test-retest reliability**, `1 − Var(difference) / (2·Var(all))`.

`rho_bar` is then reported **both raw and disattenuated** for measurement noise
(`stats.disattenuate`, Spearman's correction). The raw value remains primary.
The correction moves `rho` **up** and `N_eff` **down** — toward our own
hypothesis — so reporting only the corrected figure would be arguing our case
with a statistical adjustment. Both are reported, always, with the per-model
reliabilities stated alongside.

If measured reliability is high for all models, this section costs roughly $4 and
closes a question a reviewer would otherwise be right to ask. If it is low for
some model, that is a finding about the instrument and is reported as one.

### 5.5 The reported comparison statistic

The headline human-versus-AI number is the **difference in variance reduction**
(fraction of squared error removed by averaging the panel), which is bounded in
[0, 1] and directly interpretable. The **ratio** of headroom is reported as a
secondary with its interval and the count of undefined bootstrap draws.

Reason, simulated: as the AI panel's headroom approaches zero — the outcome H4
predicts — the ratio runs away while the bounded statistic does not.

| rho_AI | benefit difference | ratio |
|---|---|---|
| 0.970 | 0.064 | 3.9 |
| 0.995 | 0.098 | 29.5 |
| 0.999 | 0.110 | 145.4 |
| 0.9999 | 0.103 | 1294.3 |

"AI is 1294 times less diversified" is arithmetically true and rhetorically
worthless. The bounded statistic says the same thing and survives scrutiny.

### 5.6 Exclusions
Observations with `error` set are excluded from estimation but **counted and
reported**. If usable coverage falls below 80% for any model, that model is
reported separately and excluded from the primary panel.

---

## 6. Sample size

Target ≈ 25 task-days × 9 models × 105 days ≈ 23,625 observations. Powering the
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

Fixed in advance and not revisable after the freeze: the model roster; the
60/40 macro/filing task mix; sampling temperature; the seven state variables **and
the direction H1 predicts for each of them (§4)**; the primary outcome (both scales); the capability
control in H6; the block-bootstrap parameters, **including the event-clustered
interval reported alongside the day-blocked one (§5.2)**; the inclusion criteria; the multiple-testing correction; the
prediction date; and the test-retest replicate design of §5.4(d) — its count per day, its
reserved variant, and the commitment to report `rho_bar` both raw and disattenuated.

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
5. 15 weeks may contain no genuine market stress event, which would leave the
   market-stress leg of H1 (now the primary hypothesis) untestable. The
   experimentally varied `ladder_distance` ambiguity leg is populated every day
   and does not depend on markets cooperating, so H1 remains testable in a calm
   regime — but a genuine shock cannot be manufactured, and if none occurs we
   report the stress leg as untested rather than straining a null out of a quiet
   market.

---

## 11. Deviations from this plan

_(Numbered and dated. Empty at registration.)_

| # | Date | Deviation | Reason |
|---|---|---|---|
| 2 | 2026-09-03 | **2026-09-03 carries 30 tasks rather than 25.** A backup collection run was added at 20:00 UTC on 2026-09-03 to protect against a first run dying on something transient. `neff.collect` is idempotent per observation but was not per task: `build_daily_tasks` selects from live sources, so the 22:24 UTC rerun registered 5 Kalshi housing-start ladder rungs (`KXHOUSINGSTART-26SEP17`, thresholds 1.300–1.500) that had not existed at 17:04, and collected 50 observations against them. | Operational fault, ours, found the same day. Nothing was lost, double-counted or back-dated: all 30 tasks were registered before any outcome existed and all 320 observations are real. What changed without being planned is the sampling design on one day — 5 extra tasks at a market state 5 hours removed from the other 25. Fixed in `neff.collect`: a day that already has registered tasks reuses exactly those, so a rerun finishes a day and can no longer extend one (`tests/test_rerun_does_not_extend_the_day.py`). **The 5 rows are kept, not deleted** — the record is append-only and removing real pre-outcome forecasts after the fact is a worse failure than the imbalance it would tidy. Any day-level analysis should weight by task count rather than assume 25. |
| 1 | 2026-09-03 | `MAX_OUTPUT_TOKENS` raised from 400 to 1000. Not a registered quantity; recorded here because it changes the instrument mid-collection. | At 400, `claude_sonnet` lost 7 of 54 observations on 1–2 Sep, each billed at exactly 400 output tokens: it reasons in prose before emitting the JSON object and was cut off before reaching it. The loss was **not at random** — the same questions (JPM, PG) truncated on both days, concentrating the loss on items that invite long reasoning, which is the subpopulation H2 is about. `max_tokens` is a stopping rule, not a sampling parameter: it cannot change the distribution generated, only halt it, so replies that finished inside 400 tokens (the panel median is 60–105) are unaffected. Days 1–2 were collected at 400 and that is stated wherever the affected coverage is reported. |

# Pre-Collection Audit — 17 Aug 2026

Everything below was found by deliberately attacking this project the day before
data collection was due to start, while every finding was still free to fix.
None of it caused a crash. Every one produced plausible-looking numbers.

**Ten defects. All fixed. Core estimator and panel defects are covered by
tests (`tests/test_regressions.py`); the design fixes are verified against live
data and synthetic ground truth.**

---

## 1. The primary estimator could not see the effect the study is about

Pearson correlation subtracts each forecaster's own mean error, so a bias shared
by the whole panel is differenced away. "Every model wrong in the same
direction" is exactly the systemic-risk story — and the registered primary metric
was blind to it. Simulated at M = 7, T = 400:

| common bias | Pearson rho | Pearson headroom | true N_eff (MSE) |
|---|---|---|---|
| 0.00 | +0.016 | 5.40 | 6.38 |
| 0.10 | −0.008 | 6.35 | 3.27 |
| 0.20 | +0.010 | 5.59 | 1.70 |
| 0.30 | +0.013 | 5.49 | 1.37 |

Pearson reports "seven nearly independent minds" at every bias level while the
panel collapses to one. `variance_reduction` was centred too, so equally blind.

**Fixed:** added `mean_uncentered_correlation`, `n_eff_mse`, `mse_reduction`.
The MSE-scale statistic is now co-primary and is the primary for the systemic-risk
claim. Pearson is retained for comparability with the literature. Where they
diverge, the divergence is reported as the shared-bias finding.

## 2. Two of four human baseline numbers were units artifacts

SPF reports CPI as an **annualised inflation rate** (~2.7); it was being
differenced against the **CPI index level** (~333). SPF reports real GDP as a
**level in the chain base current at survey time**; it was being differenced
against a 2017-base series.

| Series, as originally coded | median abs error | rho_bar |
|---|---|---|
| CPI h=1 | **229.07** | **1.0000** |
| RGDP h=1 | **3488.46** | **1.0000** |

A *perfect* correlation manufactured by a units mismatch — in the numbers that
set the study's human benchmark. Corrected CPI h=4 headroom moves 0.0047 → 0.0797,
**a 17-fold change in a quantity that sits in the headline comparison.**

**Fixed:** `VARIABLE_MAP` now carries unit semantics; growth variables are scored
growth-to-growth, which is invariant to the index base.

## 3. The human/AI comparison compared two different objects

Our models emit a **probability of a binary event**; SPF point forecasts are
**continuous levels**. Headroom is roughly `tau²/(sigma_c²+tau²)`, and the
mechanical floor of `sigma_c²` differs between a Bernoulli and a continuous
outcome — so the headline difference could have been a task-format artifact.

**Fixed:** SPF **RECESS** is now the primary human benchmark — individual
forecasters' probability that real GDP will decline, quarterly since 1968. Same
object, same scoring, same estimator. Measured at M = 9: rho 0.84–0.89,
headroom 0.112–0.171. That it lands in the same band as the corrected
point-forecast baselines, by a completely different route, is the main reason to
believe the corrected numbers.

## 4. The block bootstrap was not a block bootstrap

`load_panel` sorted rows by `task_id` — a SHA-256 hash — so rows arrived in an
order random with respect to time. The moving-block bootstrap resamples
*contiguous rows* to preserve serial dependence; under hash ordering those blocks
were unrelated days. Simulated on AR(0.9) data, T = 300, M = 7:

| row order | 95% CI | width |
|---|---|---|
| time-ordered | [0.8599, 0.9237] | 0.0638 |
| hash-ordered | [0.8781, 0.9136] | 0.0355 |

**Every interval in the paper would have been 44% too narrow.**

**Fixed:** panel rows are sorted by `(asked_on, question, task)`; `Panel` now
carries `question_ids` and `asked_on`; `describe()` asserts time ordering.

## 5. A registered exclusion rule was not implementable

§3.3 excludes questions whose panel median is outside [0.05, 0.95] **on the first
day asked** — which requires stable question identity across days. `task_id` is
date-stamped, so the data model could not express "the same question, asked
again."

**Fixed:** `apply_settled_question_exclusion()` operates on `question_ids` and
first-ask date, exactly as registered.

## 6. A headline hypothesis rested on a single pair — and its test was invalid

H3 ("intra-vendor diversity is an illusion") and H6 both rest on the
within-family contrast. The seven-model panel had **exactly one** within-family
pair.

- Cluster-robust inference clusters by pair, so that coefficient's variance came
  from **one cluster**. On synthetic data containing **no family structure at
  all**, the clustered t-statistic returned **+7.06** and declared the effect
  real — a false positive manufactured by the estimator.
- The valid alternative, exact permutation over family labels, admits only
  C(7,2) = 21 labelings → **best achievable p-value 1/21 = 0.048.** A headline
  hypothesis whose ceiling is the significance threshold.

**Fixed twice over:** inference is now `lineage_permutation_test` (verified to
separate real lineage, p = 0.048, from fabricated lineage, p = 0.48); and the
panel gained a second OpenAI and a second Google tier, giving **9 models, 36
pairs, 3 within-family pairs** and a permutation floor below 0.001. Marginal cost
≈ $7 on a $30 study.

## 7. The power claim assumed independence the design does not have

The plan quoted "7.7 sigma" with no dependence assumption stated, while questions
are re-asked daily and are therefore not i.i.d. Simulated separation of
rho = 0.996 from 0.990:

| AR(1) in the common component | separation |
|---|---|
| 0.0 | 10.4 sigma |
| 0.5 | 8.3 sigma |
| 0.8 | 5.3 sigma |

**Fixed:** restated as "at least 5 sigma even under strong serial dependence."

## 8. The headline statistic ran away exactly where the hypothesis predicts

`headroom_ratio` is unstable as its denominator approaches zero — the outcome H4
predicts:

| rho_AI | benefit difference | ratio |
|---|---|---|
| 0.970 | 0.064 | 3.9 |
| 0.999 | 0.110 | 145.4 |
| 0.9999 | 0.103 | **1294.3** |

"AI is 1294× less diversified" is arithmetically true and rhetorically worthless.

**Fixed:** the reported headline is now the **difference in variance reduction**,
bounded in [0,1]; the ratio is secondary, with its interval and its count of
undefined bootstrap draws.

## 9. Task selection suppressed the variance the primary hypothesis needs

`select_tasks` took only the strikes nearest each ladder's median — maximising
average uncertainty and thereby holding ambiguity nearly **constant**. H1, now
the primary hypothesis, predicts correlation *rises with ambiguity*. A sample
with no ambiguity variation cannot test it.

**Fixed:** graded sampling across each ladder's interior, with `ladder_distance`
(normalised distance from the ladder median) recorded per task and registered as
an H1 state variable. Live check: ladder_distance now spans 0.00–0.52 instead of
sitting at the median. Crucially it is populated **every day**, so H1's ambiguity
leg no longer depends on markets supplying a stress event — the study's single
largest un-fixable risk is now only half un-fixable.

## 10. H2 was registered with no method for either of its legs

Rationales were being *collected* but nothing measured "cross-model rationale
similarity" or "evidence sensitivity" — the same defect as H6.

**Fixed by splitting it.** The tractable leg, **base-rate convergence**, is now
implemented and confirmatory: does the panel median drift toward the category
base rate as ambiguity rises? Validated on synthetic ground truth (true case
−0.118, false case −0.017). The intractable leg, rationale similarity, is
**demoted to exploratory** — measuring it honestly needs sentence embeddings and
a validation study of its own, and 25-word rationales are thin evidence for a
confirmatory claim.

---

## 11. The block bootstrap still was not a block bootstrap

Finding 4 fixed the row *ordering*. It did not fix the block *unit*, and the
second error survived the first fix.

§5.2 registers "block size 5 task-days". The code passed `block_size=5` to a
resampler that counts **rows**. The panel carries ~25 tasks per day, so five rows
is a fifth of one day: a block could not span two days, and — because `tasks.py`
re-asks every open question daily, placing that question's successive
observations ~25 rows apart — it could never span two observations of the same
question. The dominant dependence in the entire design was invisible to the
bootstrap.

Simulated at the real panel shape (9 models, 25 tasks/day, 105 days, AR(.95)
per-question persistence):

| blocking | 95% CI | width |
|---|---|---|
| `block_size=5` rows (as coded) | [0.9578, 0.9616] | 0.0038 |
| `block_size=5` task-days (as registered) | [0.9558, 0.9647] | 0.0089 |

**Every interval would have been 57% too narrow** — worse than finding 4, and it
reached `metrics.headroom_ratio`, which §5.5 names as the headline comparison.
The point estimate was never affected; only the uncertainty around it.

Two things made this survive an audit that had already looked at this exact
function. The parameter name `block_size` is unit-free, so the code read as
correct against a registration that says "task-days". And the existing test
asserted only that `block_size=25` beat `block_size=1` — true under both the
broken and the fixed implementation, because it never varied the *unit*.

**Fixed:** `stats._moving_block_indices` takes explicit day labels (`groups=`);
`block_size` then counts task-days, a sampled day is indivisible, and passing a
mismatched label array raises rather than silently mis-blocking. Same treatment in
`metrics.headroom_ratio` for both panels. §5.2 now states the unit explicitly, so
the registration cannot be read the wrong way. Six regression tests, one of which
asserts the point estimate is unchanged — a fix that moved the measurement itself
would be a different bug.

## 12. H1's primary state variable was computed and then thrown away

`kalshi.select_tasks` computes `ladder_distance` for every market and uses it to
choose graded positions across each strike ladder. `tasks.py` then assembled the
task's `state` dict with `days_out`, `series`, `strike` and `asked_on` — and not
`ladder_distance`. It was calculated, carried on the candidate, and dropped one
line before it would have been persisted.

Nothing failed. Tasks built, the panel would have filled, and H1 would have
arrived at analysis in December missing the leg the design depends on most:

> §10.5: "The experimentally varied `ladder_distance` ambiguity leg is populated
> every day and does not depend on markets cooperating, so H1 remains testable in
> a calm regime."

It was populated on no days at all. Had the 15 weeks been calm — the scenario
§10.5 exists to survive — the primary hypothesis would have had no variation to
consume and the study would have had no headline result. It is also the one state
variable that **cannot be backfilled**: it needs the live strike ladder as it
stood on the ask date, and closed Kalshi ladders are not reliably re-queryable.

Auditing the rest of the list found the registration and the code disagreeing
three separate ways:

| | §4 registers | `config.py` had | Status |
|---|---|---|---|
| ladder distance | ✓ | ✓ | computed, **dropped before persistence** |
| VIX level | ✓ | ✓ | collected |
| 20-day realised vol | ✓ | ✓ | collected |
| cross-model dispersion | ✓ | ✓ | derived at analysis |
| \|macro surprise\| | ✓ | ✓ | derived at analysis |
| **days-to-resolution** | ✓ | **absent** | collected as `days_out`, unregistered in code |
| novelty score | ✓ | ✓ | derived at analysis |
| **news_volume** | **never registered** | ✓ | unregistered variable in the frozen set |

Both documents also said "**six** state variables" while the list held seven.
That count is the Benjamini–Hochberg denominator, so it sets H1's falsification
threshold directly — §4 states the correction is applied "across the six state
variables" and §9 freezes "the six state variables."

**Fixed:** `ladder_distance` is propagated into task state; `news_volume` removed
as unregistered under "no additions permitted"; `days_out` registered;
both documents corrected to seven; and `config.STATE_COLLECTED_AT_ASK` now names
the four that are irrecoverable if missed, separating them from the three that
are merely derived later. Six regression tests, including one asserting
`ladder_distance` carries its real value rather than a `setdefault(0.0)`, which
would zero the experimental leg just as effectively as dropping it.

## 13. The frontier anchor could not honour a registered parameter

`TEMPERATURE = 0.0` is registered in §9 as a frozen commitment, and `config.py`
states why: *"we want each model's modal judgement"*, so that cross-model
differences reflect the models rather than our sampling noise.

The pinned frontier anchor, `claude-sonnet-5`, **rejects the parameter outright**:

```
HTTP 400  `temperature` is deprecated for this model.
```

Newer reasoning models across the industry are removing sampling controls
entirely. On Anthropic's current line, `temperature`/`top_p`/`top_k` return 400 on
Sonnet 5, Opus 5, Opus 4.8, Opus 4.7 and Fable 5; they are still accepted on
Sonnet 4.6, Opus 4.6 and Haiku 4.5.

This is worse than a dead ID. A dead ID fails loudly and visibly. Here the
tempting fix -- drop `temperature` for the one model that refuses it -- would have
produced a panel where **eight members sample at temperature 0 and one samples
adaptively**. Every cross-model correlation involving the frontier anchor would
then mix a model difference with a sampling difference, and the anchor is
precisely the member H6 leans on for its capability contrast.

**Fixed:** `claude_sonnet` repinned to `claude-sonnet-4-6` -- the newest Anthropic
model that still accepts `temperature`, at identical $3/$15 pricing, same family,
same tier. Verified by live call at `temperature=0`. A roster constraint is now
recorded beside the `TEMPERATURE` constant, because this will recur: the industry
is moving away from sampling parameters, and a future roster edit that adds a
Claude 5 / Opus 5-class model would silently reintroduce the same defect.
`neff.verify` makes one real call per model and fails loudly on it.

## 14. A registered sensitivity analysis rested on a capability three models lack

§5.4(a) handles the shared-mass-point threat -- models converging on identical
round probabilities, which inflates correlation for reasons of verbal habit rather
than shared priors. One of its three pre-committed handlings was to *"re-estimate
on logprob-derived probabilities"* for **"the four models exposing logprobs."**

Three separate numbers, none of which agreed:

| | Count |
|---|---|
| PREREGISTRATION.md §5.4(a) claimed | 4 |
| `config.py` `supports_logprobs=True` | 5 |
| **Actually return logprobs** | **2** |

Measured by live call: `llama` and `deepseek` return them. `gpt_mid` and
`gpt_small` cannot -- OpenAI answers `logprobs are not supported with reasoning
models` -- and `qwen` returns none in practice.

Two models yield exactly one pairwise correlation, which is not a re-estimate of
panel-level `rho_bar` in any useful sense. The handling was not merely
over-counted; as a panel-wide sensitivity it does not exist.

This would have surfaced in December, while writing the sensitivity section
against data that could never have supported it.

**Fixed:** `supports_logprobs` corrected to the two models that actually have it;
§5.4(a) demotes the logprob leg to a stated two-model spot check. The threat is
still addressed -- the emitted-value distribution and the exact-tie exclusion are
full-panel checks needing no logprobs -- but by two routes rather than three, and
that reduction is now registered rather than discovered later.

## 15. A router silently discarded a registered parameter

The worst failure found in this project, because it produced no error at all.

`TEMPERATURE = 0.0` is registered in §9. Testing the OpenAI models revealed a
three-layer problem:

**Layer 1 -- the direct API refuses the parameter.** `gpt-5-mini` and `gpt-5-nano`
return HTTP 400: *"'temperature' does not support 0.0 with this model. Only the
default (1) value is supported."* Loud, visible, unmissable. Fine.

**Layer 2 -- the router accepts it and throws it away.** The same models via
OpenRouter return HTTP 200. The call succeeds. The parameter is silently dropped
and the model samples at temperature 1. Five calls at `temperature=0` with an
identical prompt:

| Route | Result |
|---|---|
| `openai/gpt-5-mini` via OpenRouter | Teal, Turquoise, teal, cerulean, Teal |
| `openai/gpt-5.1` via OpenRouter | Cyan, Cerulean, Teal, Cerulean, Cyan |
| `deepseek/deepseek-v3.2` via OpenRouter | Crimson x5 |

Two panel members would have sampled randomly for fifteen weeks while every log,
every stored record and the pre-registration itself said temperature 0. The
resulting correlations would have mixed genuine model differences with sampling
noise on exactly two members -- undetectable after the fact, because nothing was
ever recorded as wrong.

**Layer 3 -- the escape route had the same defect.** The frontier model added
hours earlier, `openai/gpt-5.1` via OpenRouter, was affected identically. So was
the fallback plan for routing the GPT pair through OpenRouter when direct billing
failed. Both were adopted for sound reasons and both silently broke a registered
parameter.

`llama`, `qwen` and `deepseek` route through OpenRouter and are all deterministic,
so this is specific to OpenAI's reasoning line, not to routing in general.

**Fixed:** the whole OpenAI family repinned to `gpt-4.1-mini-2025-04-14`,
`gpt-4.1-nano-2025-04-14` and `gpt-4.1-2025-04-14`, on the direct API. Verified
deterministic across five identical responses. Three side benefits fell out:
logprob support returned (restoring §5.4(a)'s four-model coverage, see finding
14), the provider mix rebalanced to 3/3/2/2 rather than concentrating six models
behind one router, and the dated snapshots removed three floating aliases -- the
undated ids resolved to `-2025-04-14` snapshots that OpenAI could repoint mid-panel.

Two further defects surfaced on the way: `max_tokens` is rejected by OpenAI's newer
line in favour of `max_completion_tokens` (a per-provider difference, since
OpenRouter still normalises the old name), and the drift check caught the alias
resolution. Both are now handled in `providers.py` and `config.py`.

**The generalisable lesson:** a proxy that accepts an unsupported parameter and
discards it is more dangerous than one that rejects it. Where a registered
parameter is involved, verify it took EFFECT -- do not settle for HTTP 200.

## Also corrected: the novelty claim

An earlier draft asserted that nobody has measured LLM error correlation. **That
was false.** Four papers do (`PRIOR-ART.md` §A7), and one of them publishes the
exact figure our pitch was using — *ten agents ≈ 1.4 effective forecasters*
(arXiv 2606.26583). A judge would have found this in five minutes.

The claim is withdrawn and replaced with a narrower one that survives scrutiny:
the *level* of correlation is known; the **conditions under which it moves** are
not. Prospective pre-registration, state-dependence, a structurally matched human
panel, and a capability control are what remain unoccupied — and the closest
paper (arXiv 2605.00844) names our H1 as its own open question.

## Also added: the confound that could have sunk the whole result

arXiv 2607.20768 shows diversity metrics are largely a restatement of accuracy
(Spearman rho = +0.99 against one minus mean accuracy). Under that critique a raw
correlation finding is uninterpretable — it may say only that the models are all
good. **H6** now registers the control in advance, and **H1 was promoted to
primary** precisely because it is a within-panel contrast: capability cannot vary
between Tuesday and Thursday, so H1 is structurally immune to the confound that
undermines every between-panel comparison, including our own H4.

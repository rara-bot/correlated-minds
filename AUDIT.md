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

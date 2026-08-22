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

---

# Freeze-Eve Audit — 21 Aug 2026

A second adversarial pass, run the night before the pre-registration was due to
be frozen and three days before collection opens. Same rule as the first pass:
attack the project while every finding is still free to fix.

**Eight defects. All fixed, all covered by tests — 288 tests, up from 113.** Two of them would
have been unfixable the following afternoon, because an OSF registration cannot
be edited after submission.

Nothing here crashed. Every one produced a green tick, a plausible number, or a
confident log line.

## 16. The freeze tool published a hash that did not match the document

The single worst defect found in this project, because it breaks the one claim
everything else rests on and it breaks it *permanently*.

`scripts/freeze_prereg.py` is what converts "we planned this in advance" from an
assertion into something a stranger can check: it stamps the plan, hashes it, and
the hash goes on OSF. Two independent bugs meant the hash it published was never
the hash of the document.

**Bug 1 — the hash was taken before the last edit.** The script rewrote
`**Status:** DRAFT …` to `**Status:** FROZEN …` *after* computing the digest.
`body_without_stamps` excludes the two stamp lines from the hash, but not the
status line, so the recorded hash was of a document that had already ceased to
exist. `--freeze` printed one hash and stored another:

| | Value |
|---|---|
| printed to the terminal, and pasted into OSF | `c7e8bcf248d18525…` |
| written into PREREGISTRATION.md | `b60927b7c0d3a232…` |

**Bug 2 — `--check` could never pass anyway.** The stored hash is wrapped in
backticks for markdown. The comparison was `recorded != h` against a bare hex
digest, so `"`b609…`" != "b609…"` was true for every document ever frozen.

Together: run `--freeze`, and the very next `--check` reports

```
!! HASH MISMATCH -- the document changed after freezing.
```

on a document nobody had touched. The first skeptic to verify the registration —
which is the entire point of publishing a hash — would have been told the plan
had been tampered with, against an immutable OSF record with no correction path.

**Fixed:** every mutation to the hashed body now happens before the digest is
taken; `recorded_hash()` extracts the hex by pattern rather than by `strip()`;
and `--freeze` verifies its own output in memory *and* re-reads the file to
confirm, restoring the original if the round trip disagrees. Anchor
substitutions raise instead of silently no-opping — the finding-15 lesson turned
on ourselves: confirm the change took EFFECT, do not settle for "no error".
19 regression tests (`tests/test_freeze.py`), including one asserting the printed
hash equals the stored hash, which is the exact thing that was wrong.

## 17. The document about to be frozen registered a model the study does not use

§3.1 named the frontier anchor as **Claude Sonnet 5**. `config.py` pins
**`claude-sonnet-4-6`**, and has since finding 13 — the repin reached the code
and never reached the registration.

§9 freezes the model roster. Freezing in that state would have permanently
registered a panel member the study never queries, and the mismatch is visible to
anyone who opens the public log.

Separately, and worse: the roster had grown to **ten** models. `gpt_frontier` is
collected daily and was **named nowhere in the registration at all**. A reviewer
comparing ten model ids in the public log against a registration that says nine
finds an undeclared arm — the one accusation a pre-registered study cannot
answer after the fact.

**Fixed:** §3.1 now carries an explicit roster table of all ten pinned ids with
provider, family, tier, and primary/secondary status; states why the anchor is
4.6 and not 5; and declares the tenth model, its exclusion from every primary
estimate, the reason (H4 matches humans at M = 9 against SPF headroom measured at
that panel size), and where that exclusion is enforced in code.
`tests/test_roster.py` holds the table to `config.py` in both directions, so the
document and the code cannot drift apart again — 21 tests, including one that
fails if the string "Claude Sonnet 5" reappears anywhere in the plan.

## 18. The paste-ready OSF text disagreed with the plan it was supposed to mirror

`OSF.md` carries field-by-field text to paste into the registration form. It is
the text that actually becomes immutable, and six fields were stale:

| Field | Said | Should say |
|---|---|---|
| Description | "seven language models" | nine |
| Sample size | 25 × **7** × 105 ≈ 18,375 | 25 × **9** × 105 ≈ 23,625 (§6) |
| Measured variables | six state variables | **seven** — `ladder_distance` was missing |
| Inference criteria | "across the **six** registered state variables" | seven |
| Study design | nine models, no mention of the tenth | discloses the secondary model |
| Data collection | "queries all nine models" | ten are queried |

The state-variable count is not cosmetic: it is the **Benjamini–Hochberg
denominator**, so registering six while the analysis corrects across seven sets
H1's falsification threshold to a value the study does not use. That is finding
12 all over again, in the one document where it could not be corrected later.

**Fixed:** all six fields rewritten against the plan.

## 19. H1's experimental leg was empty on every broadened task

Finding 12 fixed the *propagation* of `ladder_distance` — computed in
`kalshi.select_tasks`, dropped by `tasks.py`. The fix was real. It was also only
half the pipeline.

`select_tasks` computed ladder positions **only in the curated-series branch**.
When the priority series do not supply enough questions the selector widens to the
full Economics/Financials universe — "on many days", by its own comment — and
those markets were appended with no ladder position at all, reaching the task
record as `None`.

Measured against the live API on a 25-task day:

| | Before | After |
|---|---|---|
| event tasks | 15 | 15 |
| missing `ladder_distance` | **5 (33%)** | **0** |
| distinct ambiguity values | 5 | **9** |
| range | 0.00–0.52, clustered at 0.0 and 0.5 | 0.00–0.52, graded 0.1/0.2/0.3/0.4/0.5 |

`ladder_distance` is H1's *experimentally varied* leg — the one state variable
§10.5 says is populated every day regardless of whether markets supply a stress
event, and therefore the reason H1 survives a calm 15 weeks. A third of it was
missing, and it cannot be backfilled: it needs the live strike ladder as it stood
on the ask date, and closed Kalshi ladders are not reliably re-queryable.

The existing test could not have caught this. `tests/test_state_variables.py`
stubs out `kalshi.select_tasks` and feeds `tasks.py` a hand-written candidate
that already carries `ladder_distance` — it verifies the second half of the
pipeline using a fixture that assumes the first half worked.

**Fixed:** ladder assignment extracted into `assign_ladder_distance()` and called
from both paths; the broadening path now groups candidates by event before
selecting, so a market can see the rest of its own ladder; and `select_tasks`
raises rather than returning any market with an unset value. Fixing it also
*improved* the primary hypothesis's regressor — nine distinct ambiguity levels
instead of five. 11 tests (`tests/test_task_selection.py`) that exercise the real
selector against stubbed HTTP; 8 of them fail against the pre-fix code.

## 20. `--dry-run` wrote to the append-only study record

`--dry-run` is documented as "price the day, ask nothing", and the OSF gate lets
it through on the explicit grounds that it "touches nothing real". It registered
that day's 25 questions to `data/tasks.jsonl` before reaching the dry-run branch.

Those rows can never acquire observations, so they are permanent orphans in the
public record. And `SETUP.md` instructs the operator to smoke-test the workflow
with `dry_run` ticked — a workflow that ends in `git add -A data/` and a commit.
The rehearsal would have published a batch of questions to the public repository
**dated before the pre-registration was frozen**, in a study whose entire claim
is that the plan came first.

**Fixed:** task persistence is skipped on a dry run and the log says so. The
pricing arithmetic is untouched. 9 tests (`tests/test_dry_run.py`), including one
that the real run still registers tasks before observations — the guard has to be
specific to dry runs, or it breaks the ordering that makes "the question predates
the answer" checkable.

## 21. The registration gate could not see the registration

`neff.collect` refuses to write primary data until `.osf_url` exists. `.osf_url`
is untracked, and the scheduled job runs from a **fresh checkout**.

So the intended sequence — register on OSF, `echo <url> > .osf_url`, done — would
have left every automated collection day from 24 Aug failing with

```
REFUSING TO COLLECT -- OSF registration not confirmed.
```

on a registration that was live, public, and sitting in a file on the operator's
laptop. Silent unless someone watches the Actions tab, and every lost day is
unrecoverable.

A second, smaller hole in the same gate: the check was `len(text.strip()) > 0`,
which `echo pending > .osf_url` satisfies. A gate a typo opens is not a gate.

**Fixed:** the URL must parse as a URL; an `OSF_URL` environment variable is
accepted as a CI alternative; the workflow gained a first step that checks
visibility *before* loading any key and names the exact remedy; the failure
message says to commit the file and why; and `preflight.py` reports a `.osf_url`
that exists but is uncommitted as blocking. 24 tests (`tests/test_osf_gate.py`).

## 22. The cost model was half the real figure, against a cap that is a hard stop

Documented: $0.24/day, $25 for the panel. Re-priced on 21 Aug with a live dry run
against the real battery and the real roster: **$0.4442/day, $46.64** for the
105-day window. The published figure was for nine models and predated the tenth,
and nobody re-measured after the roster changed.

On its own that is a bookkeeping error on a $200 budget. What made it matter is
`ARM_CAPS_USD["ws1_prospective"] = 70`, set against the $25 projection.
`Ledger.check` **raises**; it does not warn. An arm cap is a hard stop. At the
true rate the prospective panel consumes two thirds of its own cap, and any
upward drift across 15 unattended weeks — longer prompts as filings accumulate,
more open questions re-asked daily — ends collection in November, at the far end
of the panel, on days that cannot be recollected.

**Fixed:** `config.MEASURED_DAILY_USD` records the measured figure and
`projected_ws1_usd()` derives the projection from the registered window, so it
cannot go stale silently again. The arm cap is now $100 (~2.1x the projection),
funded by rebalancing the later workstreams — **the global $200 cap and the $15
reserve are unchanged**, so total exposure did not move. 12 tests
(`tests/test_budget_headroom.py`), one of which simulates all 105 days at a 50%
cost overrun and asserts the panel still completes.

## 23. The readiness check reported a push that had never happened

`scripts/preflight.py` exists because a mock run once looked identical to a real
one and was mistaken for a completed setup. Step 6 then had the same defect: it
printed `[done] Pushed to a public GitHub repo` as soon as `git remote -v`
returned anything.

The remote was configured. The GitHub repository existed and returned HTTP 200.
It contained **no branches** — nothing had ever been pushed. The public,
timestamped commit history that the entire "registered in advance" claim depends
on did not exist, and the readiness check said it did.

Step 2 had the mirror-image defect: it asked whether every model had answered for
real by reading `observations.jsonl`, but `neff.verify` makes live calls and
writes no observations. The step could never pass, and its own remediation line
told the operator to run the command they had just run — the fastest way to teach
someone to ignore a blocking check.

**Fixed:** step 6 asks the remote (`git ls-remote`), distinguishes *no remote* /
*unreachable* / *empty* / *N commits unpushed* / *up to date*, and reports which.
`neff.verify` now writes a receipt per probe to `data/verification.jsonl` —
which is also dated evidence that every pinned id answered a live API before the
freeze, carrying the id each provider actually served — and step 2 reads that.
14 tests (`tests/test_preflight.py`) against real git repositories with a local
bare remote.

---

# Live-Fire Findings — 21 Aug 2026

The eight above were found by reading. These four were found by **spending $0.05
and actually calling the APIs**, which is the only way any of them could have
been found. Every one was invisible to every offline check in the project.

## 24. The pre-flight check tested a configuration collection never uses

`neff.verify` called each model with `max_tokens=100`. Collection uses
`MAX_OUTPUT_TOKENS = 400`.

`gemini-3.5-flash` is a reasoning model, and on Gemini `maxOutputTokens` is a
budget **shared between internal thinking and the visible answer**. At 100 the
thinking consumed it and verify reported the model **dead**.

A false failure here is not harmless. `gemini_flash_pro` is half of the Google
within-family pair, so "that model is broken" invites a roster change the night
before the freeze — to fix a model that was never broken. The mirror case is
worse: a model that passes at 100 tokens and truncates at 400 would have been
certified healthy the day before collection.

**Fixed:** verify uses the collection budget.

## 25. The drift detector reported every OpenRouter model as drifted

The check was

```python
drift = not served.startswith(spec.model_id.split("/")[-1][:12])
```

which strips the vendor prefix from the **pinned** id and compares against the
served id with its prefix still attached. So:

```
[WARN] qwen  served 'qwen/qwen-2.5-72b-instruct'
              (pinned 'qwen/qwen-2.5-72b-instruct')  <- ID MISMATCH
```

Identical strings, reported as a mismatch. Two of ten models crying wolf on every
run for fifteen weeks is how a detector becomes something you scroll past — and a
real mid-panel swap would have arrived wearing the same yellow flag as the two
already being ignored. This check underwrites a claim the study makes in public:
*"we log the served id every call and report drift."*

**Fixed:** `classify_served_id` normalises both sides, and an alias resolving to a
dated snapshot is reported as that rather than as a mismatch.

## 26. Gemini's thinking tokens were billed but not counted

The Google provider recorded `candidatesTokenCount` as output tokens. Google
**bills thinking tokens as output**, reported separately as
`thoughtsTokenCount`. Measured on a real task prompt:

| maxOutputTokens | thoughts | visible | recorded | actually billed |
|---|---|---|---|---|
| 400 | 383 | 13 | 13 | 396 |
| 1200 | 867 | 65 | 65 | 932 |

A **14x undercount**, on the panel's most expensive output rate ($9/Mtok). The
$200 cap is enforced against *recorded* spend, so this is not a bookkeeping nit:
it is the cap quietly ceasing to protect the account it exists to protect — the
exact failure `config.py`'s own header warns about, *"a wrong PRICE fails
silently and quietly drains the budget while every log looks healthy."*

**Fixed:** thinking tokens count toward output. Separately, a response that stops
on `finishReason=MAX_TOKENS` now raises with the token split rather than
returning truncated JSON for the parser to reject as a generic "unparseable
response" — naming our own cause instead of the model's symptom.

## 27. The panel's Google tier could not have survived first contact

The 21 Aug pilot scored `gemini_flash_pro` at **0 of 8 usable observations**. Two
causes, and the second is the one that matters.

**Truncation.** At the collection budget of 400, thinking took 383 tokens and the
answer arrived as `{"probability": 0.92,` — cut off mid-object. Fixed by
disabling extended thinking for that model (`thinking_budget=0`): 71 visible
tokens, parses cleanly, and 7x cheaper. The argument is finding 13's, reused:
eight panel members answer directly, and a ninth doing extended reasoning is not
a model difference but a **mode** difference, loading onto exactly the
cross-model correlations H6 uses for its capability contrast.

That fix then broke the *other* Google model — `gemini-3.5-flash-lite` answers
HTTP 400 to any request containing `thinkingConfig`. So the field is per-model,
for the same reason findings 13 and 15 record: within one vendor, one model
accepts a parameter and its sibling rejects it.

**The quota, which is not a code problem at all.** Read from the QuotaFailure
detail in Google's own 429:

```
quotaId    : GenerateRequestsPerDayPerProjectPerModel-FreeTier
quotaValue : 20
model      : gemini-3.5-flash
```

**20 requests per day. The panel asks 25.** On a perfect day that model tops out
at exactly 80% coverage — the floor at which §3.3 drops a model from the primary
panel — and any retry puts it under. It is half of the Google within-family pair,
so losing it takes H3 from three within-family pairs to two, undoing the fix that
took the panel from seven models to nine (finding 6).

No amount of code review finds this. It required one real day of collection.

**Not fixed in code, because it cannot be:** the remedy is to enable billing on
the Google Cloud project (~$3 for the entire study) or to change the roster
before the freeze. What *is* fixed is that the failure now names itself — a 429
carrying a daily quota is reported with the number, the shortfall against
`TASKS_PER_DAY`, the §3.3 consequence, and the deadline — instead of reading as a
transient rate limit. It is recorded as the first blocking decision in
`GO-LIVE.md`.

---

**Total: 27 defects found before collection, 0 after.** Twenty-three were found
by reading; four required spending five cents on live calls, and one of those
four — the quota — could not have been found any other way.

The number that matters is not 27. It is that every one of them was found while
it was still free to fix.

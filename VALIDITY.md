# Ecological Validity — do our tasks match how AI is really used in finance?

**The question:** *"How do you know these are the AI agents' real business use?"*

It is the right question, and it is the one an ISEF judge will ask. If banks do
not actually use language models the way we test them, our measurement may not
transfer to the systemic risk we claim to be measuring. This document sets out
the evidence, states honestly where our design fell short, and records what we
changed.

---

## 1. What financial institutions actually do with LLMs

**Bank of England / FCA joint survey (third edition, Nov 2024)**
- **75%** of UK financial firms already use AI; a further 10% plan to within three years.
- **Foundation models are 17% of all AI use cases** — the fastest-growing category.
- Greatest perceived benefits: data and analytical insight, AML/fraud, cybersecurity.
- Only **34%** of firms report "complete understanding" of the AI they use.

That last figure matters for us: most firms cannot fully characterise their own
models' behaviour, which is precisely why an external measurement of correlation
is worth producing.

**Industry data, 2026**
- **55%** of hedge-fund and banking investors have integrated AI into the
  *investment process* — research, due diligence, risk monitoring.
- **75%** use AI for non-investment workflows.

**What the models are actually asked to do**
- Analyse financial reports and earnings-call transcripts
- Extract sentiment from news and social media
- Retrieval-augmented pipelines that ingest financial statements and momentum
  features, then **classify direction**
- Hierarchical summarisation of earnings calls to predict volatility
- Multi-agent trading systems
- Due diligence and risk monitoring

**An important honest caveat from the same sources:** LLMs are reported to *not*
generate alpha on their own. They are used to scale analyst capacity, not to
replace judgement outright. We should not overstate what is being delegated.

---

## 2. Where our original design was weak

Our first task type asked models to forecast macro variables — CPI, payrolls,
Fed decisions.

**Strength:** directly comparable to the Philadelphia Fed's Survey of
Professional Forecasters, which is the study's headline human benchmark. We can
apply an identical estimator to humans and machines on the same questions.

**Weakness, stated plainly:** *macro forecasting is not the dominant real-world
use of LLMs in finance.* The evidence above puts **document-grounded analysis of
company filings and transcripts** at the centre. A study measuring only macro
questions would measure a real cognitive act, but not the one banks deploy — and
a judge would be right to press on that.

---

## 3. What we changed

We added a second task type that matches deployment far more closely.

| | Macro tasks | **Filing tasks (new)** |
|---|---|---|
| Source | Kalshi event contracts | **SEC EDGAR XBRL** |
| The model must | forecast an economic statistic | **read a company's own filed financials, then judge its next reported quarter** |
| Matches real use | partially | **directly** — "analysing financial reports" is the top-cited use case |
| Human benchmark | SPF professional forecasters | none (this is the trade-off) |
| Ground truth | BLS release via CFTC-regulated exchange | the company's own next XBRL filing |

The daily battery now runs **60% macro / 40% filing**.

**Why both rather than one:** they have complementary weaknesses. Macro tasks
have a human benchmark but weaker ecological validity; filing tasks have strong
ecological validity but no human comparison. Running both also lets us test
whether error correlation is a property **of the models** or an artefact **of one
task format** — which is itself a publishable result, and a question no existing
paper in this area asks.

---

## 4. Why these nine models, when no bank calls these APIs

**The question:** *"You're paying for four API keys. Banks don't buy from those
consoles, and they don't use those exact models. So what are you measuring?"*

This is the sharpest version of the validity question, and it has a real answer.

### 4.1 Firms buy the same models through a different door

Enterprise AI in finance is not bought from `platform.openai.com`. It is bought
through cloud resale: **Azure OpenAI** (GPT), **AWS Bedrock** (Claude, Llama),
**Google Vertex** (Gemini). Those channels add compliance paperwork, data
residency, VPC networking and an enterprise invoice. **They serve the same
weights.** `claude-haiku-4-5` on Bedrock and `claude-haiku-4-5` on the Anthropic
API are the same object with different billing.

So the gap between our panel and a bank's panel is a *procurement* gap, not a
*model* gap. We are not testing a proxy for what banks run. We are testing the
same artefacts, over a cheaper counter.

### 4.2 The hypothesis lives in the lineage, not the endpoint

Our claim is that shared pretraining ancestry produces shared priors, which
surface as identical errors under ambiguity. That property is in the weights.
Everything a bank adds on top — retrieval, system prompts, fine-tuning, human
review — sits *above* the layer we are measuring.

And whether those additions rescue independence is not an afterthought; it is
**H3**, tested directly:

| Diversification a firm might buy | Our test |
|---|---|
| "We use several prompts / personas" | one model, 5 prompt variants |
| "We use two models from one vendor" | three within-family pairs: Anthropic, OpenAI, Google |
| "We use different vendors" | six distinct families |

If prompt-level and within-family diversity buy materially less independence than
cross-family diversity, then a firm running "a diverse AI committee" from one
vendor is holding one opinion and paying for several. That is the finding, and it
is about lineage — which is exactly what our panel varies.

### 4.3 Six families is broader than any single institution's stack

As of 2026 the enterprise supply is essentially OpenAI, Anthropic, Google, Meta's
open weights, and the open-weight Chinese labs (Alibaba's Qwen, DeepSeek). Our
panel spans all six. A given bank typically runs **one or two**.

This inverts the objection. We are not testing a narrower slice than industry —
we are testing a **wider** one. If six families that share nothing but training
corpora still fail together, a two-vendor shop has no defence. Measuring across
the whole supply is what makes the result a statement about the market rather
than about one firm.

### 4.4 Mid-tier is the deployed tier

Frontier models are what firms demo. Mid-tier is what they run at volume, because
a research desk issuing tens of thousands of document queries a day is priced out
of frontier inference. Our panel is mid-tier by design, with **Claude Sonnet 4.6 as
a frontier anchor** so we can test whether capability tier changes correlation at
all — a question nobody has answered either way.

### 4.5 What we genuinely cannot do — and why nobody can

We cannot test any bank's actual production stack. Neither can any other external
researcher: those systems are proprietary, and the firms themselves report only
**34%** "complete understanding" of the AI they already use (§1). **That is
precisely why three regulators call this risk unmeasured.**

What we can measure from outside is the **vendor-lineage component** of error
correlation: the part that comes from the models themselves, shared across every
firm that buys from the same small set of labs. Deployment wrappers push it in
both directions — proprietary retrieval data pushes correlation **down**, while
shared data vendors, copied prompt cookbooks and convergent RLHF push it **up**.
We do not claim to know the net sign, and we do not report a bound we cannot
defend. We report the component that is common to every firm buying from these
labs, which is the component the systemic-risk argument actually rests on.

### 4.6 The money is not the design constraint

Four keys, **$30 of float, ~$30 measured cost for the full 15 weeks** — one
OpenRouter key covers three of the nine models. The panel was designed around
lineage coverage and then costed, not the reverse. Nothing in §4.1–§4.5 would
change if the budget were ten times larger; we would add frontier tiers, which is
the Year-2 extension, not a different study.

---

## 5. Why the filing task is well-designed

**Contamination-proof by construction.** The forecast target is a quarter that
has not been filed. No amount of pretraining can contain it.

**Unambiguous ground truth.** The outcome is a number the company reports itself,
in a structured XBRL field, with a filing date. No judgement call from us.

**Point-in-time discipline.** History is filtered on **filing date**, not period
end. A quarter that has ended but not yet been reported is invisible to the
model — filtering on period end instead would leak exactly the lookahead bias
that has invalidated published LLM-finance work.

**No price-data dependency.** Free daily equity prices proved unreliable (Stooq
serves a JavaScript challenge behind an HTTP 200). Anchoring on reported
fundamentals removes that dependency entirely.

**Empirically validated as uncertain.** We backtested the threshold rule across
**443 historical questions** spanning 11 companies:

| Pooled YES rate | 54% |
|---|---|

A coin flip is 50%. This matters because a rule producing 90% YES would have
every model answering "yes" and looking identical — inflating measured
correlation for a trivial reason rather than a scientific one.

---

## 6. Four bugs this exercise caught

Building the filing task surfaced errors that each produced *plausible-looking
but wrong* numbers — the dangerous kind.

1. **Stale XBRL tag.** Selecting the first revenue tag that returned data gave
   NVIDIA's series ending in 2020 at $3.1B, while its current tag runs to 2026 at
   $81.6B. Fixed by selecting the tag with the most recent data.

2. **Duration mixing.** XBRL reports a three-month figure and a year-to-date
   roll-up sharing one period-end date. Apple Q3 2026 is $109B quarterly and
   $364B cumulative. Fixed by keeping only ~90-day durations.

3. **Fiscal-year keying.** XBRL's `fy` field is the fiscal year of the *filing*,
   not of the period, and a 10-K carries three years of comparatives — so keying
   annual facts by `fy` collapsed three distinct years into one and attributed
   the wrong year's revenue. Fixed by keying on period end date.

4. **Missing Q4.** Filers like Apple and Microsoft never publish a standalone Q4;
   it exists only inside the annual 10-K. This silently dropped the two largest
   companies from the study. Fixed by reconstructing Q4 as
   `annual − (Q1 + Q2 + Q3)` — an exact identity, flagged as derived.

All four are covered by tests (`tests/test_edgar.py`).

---

## 7. Remaining limitations — stated, not hidden

1. **We test judgement, not workflow.** Real deployments wrap models in
   retrieval, tooling and human review. We measure the model's judgement in
   isolation. That is the right unit for a correlation study, but it is not a
   full deployment simulation.

2. **No earnings-call transcripts.** These are a major real use case, but
   reliable free bulk access does not exist. Filings are the closest free proxy.

3. **Mid-tier models.** Cost-driven, and defensible — mid-tier is what gets
   deployed at high volume — but not frontier. The Claude Sonnet anchor lets us
   test whether capability tier changes the result.

4. **Alpha generation is out of scope.** Sources agree LLMs do not generate alpha
   unaided. We make no claim about profitability; we measure independence of
   judgement.

5. **Days 1–2 carry a non-random hole, and the instrument changed to stop it.**
   `MAX_OUTPUT_TOKENS` was 400 for the first two collection days. Most of the
   panel answers in 60–105 output tokens, but `claude_sonnet` sometimes reasons
   in prose before emitting the object and was cut off before reaching it: 7
   lost observations across 1–2 Sep 2026, every one billed at exactly 400.

   The loss was **correlated with the question**. 1 Sep truncated on CAT, JNJ,
   JPM, PG and UNH; 2 Sep on JPM and PG — both repeats. A question that invites
   longer reasoning invites it again the next day, so the same items dropped out
   repeatedly rather than a random 13% of the sample, concentrating the loss on
   the harder end — precisely the subpopulation H2 is about.

   The cap was raised to 1000 on 3 Sep 2026 (§11, deviation 1). `max_tokens` is
   a stopping rule rather than a sampling parameter — it cannot change the
   distribution a model generates from, only halt it early — so replies that
   already finished inside 400 tokens are unaffected and the discontinuity is
   confined to replies that were being discarded. It is still a mid-collection
   change to the instrument, on 2 of ~101 days.

   **What this means for the analysis.** Any `rho_bar` including `claude_sonnet`
   should carry a sensitivity check computed without it, and the 1–2 Sep rows
   should be reported as collected under the smaller cap. Coverage never fell
   below the §3.3 floor, so this is a bias to state, not a model to drop.


6. **2026-09-03 carries 30 tasks, not 25.** A backup collection run added that
   day to protect against a transient first-run failure re-selected questions
   instead of reusing the ones already registered, and picked up 5 Kalshi
   housing-start ladder rungs that had appeared during the afternoon. All 30
   tasks were registered before any outcome existed and all 320 observations are
   real, so nothing is back-dated or double-counted — but 5 of that day's tasks
   carry a market state 5 hours removed from the other 25. Fixed the same day
   (§11, deviation 2); the rows are kept rather than deleted, because removing
   real pre-outcome forecasts after the fact is a worse failure than the
   imbalance. **Day-level analyses should weight by task count rather than
   assume a constant 25.**
---

## 8. The one-sentence answer for a judge

> Banks mainly use language models to read financial documents and make
> judgement calls, so we test exactly that — the models read companies' real SEC
> filings and forecast their next reported quarter — alongside macro questions
> that let us benchmark directly against the Federal Reserve's panel of human
> professional forecasters.

And if the judge presses on the models rather than the tasks:

> Banks buy these same models through Azure, Bedrock and Vertex — same weights,
> different invoice. We test six vendor families where a typical bank runs one or
> two, so if we find that shared training makes them fail together, a two-vendor
> firm has strictly less protection than our panel, not more.

**Sources:** Bank of England / FCA, *Artificial Intelligence in UK Financial
Services* (2024) · *2026 Global AI in Financial Services Report* (Cambridge
Centre for Alternative Finance / WEF) · 2026 hedge-fund AI adoption data ·
*A Review of Large Language Models for Stock Price Forecasting from a Hedge-Fund
Perspective*, IEEE CAI 2026 (arXiv 2605.05211)

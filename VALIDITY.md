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

## 4. Why the filing task is well-designed

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

## 5. Four bugs this exercise caught

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

## 6. Remaining limitations — stated, not hidden

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

---

## 7. The one-sentence answer for a judge

> Banks mainly use language models to read financial documents and make
> judgement calls, so we test exactly that — the models read companies' real SEC
> filings and forecast their next reported quarter — alongside macro questions
> that let us benchmark directly against the Federal Reserve's panel of human
> professional forecasters.

**Sources:** Bank of England / FCA, *Artificial Intelligence in UK Financial
Services* (2024) · *2026 Global AI in Financial Services Report* (Cambridge
Centre for Alternative Finance / WEF) · 2026 hedge-fund AI adoption data ·
*A Review of Large Language Models for Stock Price Forecasting from a Hedge-Fund
Perspective*, IEEE CAI 2026 (arXiv 2605.05211)

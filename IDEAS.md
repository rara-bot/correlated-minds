# Research Idea Slate — AI × Finance × Business
**Constraints applied to every entry:** done by 31 Dec 2026 · ≤$200 API spend · no institutional
data access (no WRDS/CRSP/Bloomberg) · M1 8 GB · ~290 researcher-hours · no human subjects (no IRB).

Every idea below was checked against the 2026 prior-art map in [PRIOR-ART.md](PRIOR-ART.md). Ideas
that failed that check are listed in §9 so we don't rediscover them.

---

## 1. Correlated Minds ★ recommended

> **How many genuinely independent judgements is an AI-mediated market actually getting — and does
> that number collapse exactly when diversity matters most?**

Finance knows one version of this: correlations go to 1 in a crisis, so diversification fails when
it's needed. The claim is that AI cognition has the same pathology for a mechanistic reason — when
evidence is weak or ambiguous, models fall back on priors, and pretraining overlap makes those
priors *shared*. So errors should decouple in calm states and lock together in stressed ones.

**Why it's open.** The FSB (Oct 2025), Bank of England and IMF (both Jul 2026) each name correlated
AI behaviour a top-tier stability risk. Two 2026 papers model its consequences. **All of them treat
the correlation as an assumed parameter.** The metric exists (effective ensemble size, formalised
2025–26) but has only been applied to trivia, judge panels and prediction markets — never finance,
never conditionally.

**Contribution:** measure `N_eff = M/(1+(M−1)ρ̄)` on financial decisions, conditional on market
state; supply the parameter the theory and the regulators are guessing at; transmit it to prices.

**Three hypotheses, independently publishable:** H1 conditional collapse · H2 shared-prior mechanism
· H3 the diversification illusion (intra-model "ensembles" buy ~nothing vs cross-family).

**Data:** free — FRED, EDGAR, Kalshi, Polymarket, JKP. **Cost:** ~$100. **Novelty: high.**
**Null-risk: low** — three independent findings, no single point of failure.

Full spec: [RESEARCH-DOSSIER.md](RESEARCH-DOSSIER.md).

---

## 2. The Novelty Penalty

> **Do LLMs fail systematically on financial events that are genuinely unlike anything in their
> pretraining — and can we predict which events those are, in advance?**

Build a novelty metric over financial events (distance from pretraining-era base rates, structural
break detection, unprecedented-language scoring on filings), then show forecast quality degrades as
a function of novelty. The prize is a **pre-hoc reliability signal**: knowing which decisions to
distrust *before* the outcome, rather than after.

**Why it's open.** Contamination work asks whether models *remember* the future. This asks the
inverse — what happens when there is nothing to remember. I found no paper doing this in finance.

**Cost:** ~$80. **Novelty: high.** **Risk:** the novelty metric is the whole project; if it doesn't
validate, there's no paper. Higher variance than #1. Also substantially overlaps #1's H2, which is
why I'd fold it in rather than run it standalone.

---

## 3. Reading the Fed

> **Do LLMs interpret central-bank communication the way markets do — and does divergence predict
> anything?**

FOMC statements, minutes and speeches are free and timestamped. Score LLM-inferred hawkishness on
each release, compare with the market's realised reaction (rates futures, equity move), and test
whether LLM–market divergence is (a) random noise, (b) a lagging error, or (c) a leading signal.

**Why it's open.** Dictionary-based Fed-tone measurement is a mature literature. The generative-LLM
version with a *market-reaction benchmark* is much thinner, and the divergence framing is cleaner
than the usual "can LLMs predict returns" framing that judges rightly distrust.

**Cost:** ~$40 — very few events, so this is cheap. **Novelty: medium-high.** **Risk:** ~8 FOMC
meetings/year means small-N on the headline event set; must broaden to speeches and minutes for
power. **Strong companion study to #1**, sharing infrastructure.

---

## 4. Machine-Optimised Disclosure

> **Are firms now writing filings for machine readers — and is there a measurable wedge between what
> an LLM reads and what a human reads?**

Cao, Jiang, Yang & Zhang (*RFS* 2023) showed firms adjust disclosure to machine readership in the
*dictionary* era. The generative-era successor: does a gap exist between LLM-assessed and
human/dictionary-assessed sentiment, is it growing, and is it larger where firms have more incentive?

**Cost:** ~$120. **Novelty: medium** — an SSRN paper (Plate/Voshaar/Zimmermann) sits adjacent on
investor reactions to GenAI-written MD&A. **Risk:** identification is genuinely hard without
institutional ownership data, and the wedge may simply not exist. Scored 31/50.

---

## 5. Evasion Detection in Earnings Calls

> **Can LLMs detect when an executive doesn't answer the question — and does detected evasion
> predict anything?**

Analyst Q&A is adversarial by construction. Build a non-answer classifier, validate against human
labels on a subsample, measure evasion rates, test whether they predict subsequent returns,
restatements or guidance revisions.

**Cost:** ~$100. **Novelty: medium.** **Risk:** transcript access is the blocker — the good sources
are paywalled, and free coverage is patchy and survivorship-biased. **Verify data access before
committing.** That single unknown is why this isn't ranked higher.

---

## 6. Information Half-Life

> **How much information survives the AI-to-AI financial content chain, and what does the loss cost?**

Company press release (increasingly LLM-written — 24% per Liang et al., *Patterns* 2025) → wire
summary → aggregator → investor's LLM analyst. Measure information retention and bias amplification
per hop, then price the decay.

**Cost:** ~$70. **Novelty: low-medium** — the telephone-game primitive is established (arXiv
2407.04503; ACL 2025), so this is an application. Scored 27/50.

---

## 7. Does Scale Buy Judgement?

> **Do institutions overpay? Does an 8B model match a frontier model on routine financial judgement?**

Practically valuable and very cheap. **Novelty: low** — reads as a benchmark paper, and benchmark
papers rarely win competitions because there's no discovery. Listed for completeness; I'd fold the
scale axis into #1's roster instead, where it costs nothing extra.

---

## 8. My ranking

| # | Idea | Novelty | Feasible ≤$200 | Null-risk | Verdict |
|---|---|---|---|---|---|
| **1** | **Correlated Minds** | High | ✓ ~$100 | Low | **Recommended** |
| 2 | The Novelty Penalty | High | ✓ ~$80 | High | Fold into #1 as H2 |
| 3 | Reading the Fed | Med-high | ✓ ~$40 | Med | Best standalone alternative |
| 4 | Machine-Optimised Disclosure | Med | ✓ ~$120 | High | Viable, harder |
| 5 | Evasion Detection | Med | ? data | Med | Verify transcripts first |
| 6 | Information Half-Life | Low-med | ✓ ~$70 | Med | Application, not discovery |
| 7 | Does Scale Buy Judgement | Low | ✓ ~$30 | Low | Fold into #1's roster |

**#1 wins on the thing that matters most:** it is the only one where a named, live policy question
is missing precisely the number we are positioned to produce. #3 is the strongest fallback and
shares infrastructure, so it can run as a companion at almost no marginal cost.

---

## 9. Checked and rejected — do not revisit

Each of these has multiple 2026 papers; full citations in [PRIOR-ART.md](PRIOR-ART.md).

| Lane | Why rejected |
|---|---|
| Adversarial attacks on LLM traders | Closed — headline manipulation, automated red-teaming, sentiment-model attacks all published |
| Lookahead bias / contamination | Closed — founding paper, benchmark, detector, mitigation |
| Algorithmic collusion | Closed — NBER WP under revision at *AER* |
| Demographic bias in credit/advice | Closed — mortgage, investment-advice, multi-agent audits all 2026 |
| LLM deception under pressure | Closed — Apollo demo + CEPR follow-up |
| "I built a trading bot that returned X%" | **Never viable.** Unfalsifiable, overfitting-prone, and fair judges are actively hostile to it |

That last row matters. The single most common AI-finance project is a backtested trading strategy,
and it is the single most reliable way to lose. Every idea above is framed as **measurement or
mechanism**, never as performance.

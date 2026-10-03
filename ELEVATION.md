# Elevating Correlated Minds to Grand-Award Shape

## 1. The honest diagnosis

The current spine is **"we measured a parameter well."** That earns respect in a journal and rarely
wins a fair. ISEF Grand Awards go to projects with a different shape:

| What wins | Do we have it? |
|---|---|
| A **discovery** — something surprising nobody knew | Partially. "Correlation is 0.7" isn't visceral |
| A **mechanism** — *why*, not just *that* | H2 is behavioural only. Weak |
| A **confirmed prediction** — said it first, then it happened | **No. This is the biggest gap** |
| A **new instrument** — you built the measuring device | Implicit, not foregrounded |
| A **live demonstration** — judge sees it in 30 seconds | **No** |
| **Stakes with a number** | Yes, via transmission |

Four elevations close every gap. Three cost ~$0.

---

## 2. Elevation 1 — the pre-registered out-of-sample prediction ★ highest value

**This is the single biggest upgrade available, it costs nothing, and it is uniquely ours.**

Every paper in this literature fits a correlation to data already collected. We have something none
of them have: a **prospective panel that hasn't happened yet.** So we do real science instead —

1. **Weeks 1–5 (calibration).** Fit the state-dependence relationship on the first five weeks.
2. **End of Week 5 — freeze and publish a numerical prediction**, hashed and committed publicly:
   > *"On the next macro release with |surprise| above the 80th percentile, mean pairwise error
   > correlation will exceed 0.__ and N_eff will fall below __."*
3. **Weeks 6–15 (holdout).** The prediction is tested on events that did not exist when it was made.

A confirmed *conditional, quantitative, timestamped* prediction is a categorically stronger claim
than a fitted coefficient — and it converts the project from measurement into science with a
falsifiable forecast. The GitHub commit log makes the timestamp independently verifiable.

**Cost: $0. Hours: ~10.** It reuses the panel we're already running.

> If the prediction *fails*, that is also a real result and we report it. A pre-registered miss is
> honest science and judges respect it far more than a suspiciously perfect fit. This is exactly
> why we pre-register.

---

## 3. Elevation 2 — the three-level correlation stack

Everyone measures agreement at the **decision** level. We measure at three, which no one has done in
finance:

| Level | What it captures | How | Cost |
|---|---|---|---|
| **Decision** | Do they reach the same call? | The structured JSON output | included |
| **Distribution** | Do they hold the same *uncertainty*? | **Token logprobs** on the decision token | ~$0 — returned with the response |
| **Representation** | Do they *encode the situation* the same way? | CKA over hidden states, open-weight subset, local forward passes | $0 — local |

**Why this matters enormously.** The closest theory paper (arXiv 2604.22818) builds its whole
argument on a distinction between *representation homogeneity* and *forecast overlap*, claims the
former drives instability — **and never measures either.** We can test its central claim directly:
does representational similarity predict error correlation?

Two models can agree on the answer while holding completely different confidence, or encode a
situation identically while diverging on output. The decision level alone is blind to both. This
turns H2 from a behavioural inference into a mechanism with internal evidence.

**Feasibility on 8 GB:** representation extraction needs *forward passes only*, not generation —
far cheaper than inference. Restricted to 1.5–3B open-weight models (Qwen 2.5 1.5B, Llama 3.2 3B) at
Q4, this runs locally. We state the caveat plainly: the representation arm is a mechanism probe on
small open models, and we test whether representation similarity predicts behavioural correlation
*within that subset*, then argue by extension rather than asserting it holds at frontier scale.

**Cost: $0. Hours: ~45.**

---

## 4. Elevation 3 — lineage as a risk predictor, not a discovery

**Checked, and this needs reframing.** Model phylogeny is claimed: PhyloLM (OpenReview), LLM DNA
(arXiv 2509.24496), and *When Agents Look the Same* (arXiv 2604.21255) — the last of which quantifies
distillation-induced behavioural similarity across 18 models from 8 providers and finds within-family
pairs more similar than cross-family.

So we do not claim the tree. We **use** it:

> Known training lineage (shared teachers, distillation ancestry, architecture family) should
> **predict which model pairs decorrelate under stress and which collapse together.**

That is a different and still-open claim, and it has a directly actionable payoff: a risk manager
choosing an ensemble gets a rule for which models actually buy independence. It also strengthens the
motivation — behavioural homogenization is now *documented*, which makes "does it become correlated
financial error when it matters?" the obvious next question rather than a speculative one.

**Cost: $0 — pure analysis on data we already have. Hours: ~15.**

---

## 5. Elevation 4 — the independence meter (the poster weapon)

Build the thing as a **deployable instrument**, not just an analysis:

> **A live meter that tells you how many independent minds your AI ensemble actually has.**

Judge walks up. Types a financial scenario. Nine models answer in real time. The N_eff dial reads
**6.2**. Then they drag the **ambiguity slider** — the scenario gets vaguer, the evidence weaker —
and they watch the models converge and the dial collapse toward **1.4** in front of them.

That is a thirty-second, visceral, unforgettable demonstration of the entire thesis. ISEF judges see
posters all day; they remember the one that *showed* them something. It also reframes the whole
project as **instrumentation** — "I built the device that measures this" is a classic Grand-Award
shape.

Ship it as an open-source package (`neff`) plus the live demo.

**Cost: ~$15 in demo calls. Hours: ~20.**

---

## 5b. Elevation 5 — THE HUMAN BASELINE ★★ the one I missed

**This is the single most important addition to the project, and I should have had it from the start.**

### The problem it fixes

Suppose we finish and report: *mean pairwise error correlation is 0.71, rising to 0.83 under stress.*

**A judge has no idea whether that is alarming.** Is 0.71 high? Compared to what? Every number in the
project is currently uncalibrated, and an uncalibrated number cannot carry a conclusion.

Worse — the actual policy question was never "are AI systems correlated?" It is **"are AI systems
*more* correlated than the human analysts they are replacing?"** Nothing in the design answers that.

### The fix, and it's free

The **Philadelphia Fed's Survey of Professional Forecasters** publishes **individual forecaster
responses** — not just the consensus — going back decades, publicly and free. Real professional
economists, forecasting **the exact macro variables our panel already covers**: GDP, inflation,
unemployment. Same questions, same resolution, known outcomes.

So we compute the **identical N_eff statistic on human forecasters** and set it beside the AI panel.

| | Effective independent forecasters |
|---|---|
| 7 professional human forecasters | *(measured from SPF)* |
| 7 frontier AI models | *(measured from our panel)* |

That single comparison does more work than everything else combined:

- **It calibrates every number in the paper.** "ρ̄ = 0.71" becomes "AI systems are N times more
  redundant than the humans they replace."
- **It answers the real policy question** the FSB, BoE and IMF are actually asking.
- **It is instantly legible.** A judge with no statistics background understands *"seven humans
  behave like four independent minds; the AI panel behaves like far fewer"* immediately — and
  **do not quote a specific N_eff until we have measured our own; "1.4" is already
  published (arXiv 2606.26583) and is not ours to claim** — and
  never forgets it.
- **It gives us a validated benchmark for the state-dependence claim too:** human forecaster
  correlation also rises in recessions. If AI's rises *faster*, that is the finding.

**Cost: $0. Hours: ~25.** The data is a free public download.

> If it turns out AI is *no more* correlated than humans, that is a genuinely important negative
> result that would reassure three regulators — and we would report it with the same emphasis. Either
> direction is publishable. That is what a good design looks like.

---

## 5c. Elevation 6 — make it exist in the world

Four moves, all cheap, that most student projects never make:

**Pre-register on OSF, not just GitHub** (~3h). The Open Science Framework is the actual scientific
standard for pre-registration — timestamped, immutable, free, citable. A GitHub commit is good; an
OSF registration is what a professional does. Do both.

**A public live dashboard** (~22h). Not only a poster demo — a real site updating daily with the
running 30-day N_eff. Anyone can watch it. It exists whether or not you're standing next to it,
and it is checkable by a judge, a reviewer, or a journalist.

**Write to the researchers** (~3h). Email the authors whose papers we build on — the correlated-errors
group, the representation-homogeneity author. Ask for critique of the design, not endorsement. Some
will reply. A substantive reply reshapes the work and is worth more than any amount of polish.

**Write to the institutions asking the question** (~2h). The **FSB ran a public consultation on
responsible AI adoption in finance in June 2026**; the Bank of England published that it is "pursuing
work on simulation methods… to understand conditions under which AI agents could demonstrate
correlated behaviour"; the OFR does financial-stability research. A short, substantive note from
someone actually producing the missing measurement is not a stunt — it is a reasonable thing for a
researcher to do. Low probability, near-zero cost, enormous upside. *(Check whether the FSB
consultation window is still open — it may have closed.)*

---

## 6. What we cut to make room

Elevations add ~90 hours. Two trims fund them, and both are *improvements*:

- **WS2 retrospective → validation set only** (−25h). It was supporting evidence; the prospective
  panel is the real contribution and contaminated historical data was always the weaker arm.
- **WS4 full agent simulation → closed-form transmission result** (−30h). State the price-impact and
  volatility scaling analytically as a function of N_eff instead of simulating an order book.
  **This is strictly better:** judges and reviewers are rightly sceptical of simulation black boxes,
  and a closed-form result cannot be accused of tuned parameters. Simulation becomes an optional
  robustness check if hours allow.

Net: ~290 hours, unchanged. Budget unchanged at $200 — three of four elevations cost nothing.

---

## 7. The elevated one-sentence hook

**Before:**
> "I measured how correlated AI financial decisions are."

**After:**
> **"Nine AI models from six different companies — and under market stress they stop being nine.
> I predicted when it would happen before it happened, traced it to how the models represent the
> situation internally, and built the instrument that measures it."**

Discovery · confirmed prediction · mechanism · instrument. That is the shape.

**Working title:** *The Illusion of Many Minds: State-Dependent Collapse of Independence in AI
Financial Judgement*

If ρ̄ reaches ~0.85 under stress, N_eff = 7/(1+6×0.85) ≈ **1.15**. The headline writes itself:
**seven minds, one answer.** We do not know yet whether it will. That is the point of measuring.

---

## 8. Revised contribution list

1. **First measurement** of cross-model error correlation on financial decisions with economic loss
   functions — conditional on market state.
2. **First pre-registered, out-of-sample confirmed (or refuted) prediction** of conditional
   correlation collapse in AI forecasting.
3. **First empirical test** of the representation-homogeneity-drives-instability claim that the 2026
   theory literature is built on and never tested.
4. **A lineage-based rule** for which model pairs actually buy ensemble independence.
5. **A closed-form transmission result** giving fragility as a function of N_eff.
6. **An open instrument and dataset** — `neff` plus a prospective panel nobody can rebuild
   retroactively.

Any two of these carry a paper. Together they are Grand-Award shaped.

---

## 9. Honest novelty accounting

| Element | Status |
|---|---|
| Effective ensemble size metric | **Established** (arXiv 2506.07962, ICML 2025). We apply, don't claim |
| CKA representational similarity | **Standard method.** We apply it |
| LLM phylogeny / lineage trees | **Claimed** (PhyloLM; LLM DNA; 2604.21255). We use as predictor only |
| Live contamination-free evaluation | **Established** (ForecastBench, ICLR 2025). Not our moat |
| Error correlation on *financial* decisions | **Open** |
| *State-dependent* error correlation | **Open — the core claim** |
| Pre-registered out-of-sample conditional prediction | **Open, and structurally unavailable to anyone without a prospective panel** |
| Representation similarity → error correlation, empirically | **Open — the theory literature's untested premise** |

Cite the first four prominently and claim none of them. The last four are ours.

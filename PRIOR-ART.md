# Prior-Art Map — AI × Finance × Business, as of 16 Aug 2026

Purpose: record what is **already claimed**, so we do not spend three months rediscovering it.
Confidence key: **[F]** = I fetched and read the abstract/page directly. **[S]** = surfaced in search
results only; title/claim recorded, needs verification before we cite it.

---

## A. SATURATED — do not build a primary claim here

### A1. Adversarial attacks on LLM-driven trading
| Work | ID | Claim |
|---|---|---|
| Adversarial News and Lost Profits: Manipulating Headlines in LLM-Driven Algorithmic Trading | arXiv 2601.13082 **[S]** | Homoglyph + hidden-text headline edits cut annual returns up to 17.7pp |
| AutoRedTrader: Autonomous Red Teaming of Trading Agents via Synthetic Misinformation | arXiv 2605.09185 **[S]** | Automated red-teaming pipeline for trading agents |
| Battle of Transformers: Adversarial Attacks on Financial Sentiment Models | J. Banking & Finance **[S]** | FinBERT / FinGPT are highly attackable |
| Sentiment Spin: Attacking Financial Sentiment with GPT-3 | Finance Research Letters **[S]** | Generative adversarial rewriting of financial text |
| Exploring Sentiment Manipulation by LLM-Enabled Intelligent Trading Agents | arXiv 2502.16343 **[S]** | RL+LLM agent posts to social media to move price |

**Verdict:** the "LLMs reading news can be fooled" result is fully established. Dead lane.

### A2. Lookahead bias / training contamination in financial LLM evaluation
| Work | ID | Claim |
|---|---|---|
| Assessing Look-Ahead Bias in Stock Return Predictions from GPT Sentiment | arXiv 2309.17322 (Glasserman & Lin) **[S]** | Founding paper; anonymising tickers changes results |
| Sarkar & Vafa — training leakage in earnings calls **[S]** | — | Llama-2 mentions COVID in >25% of pre-COVID 2019 prompts |
| Look-Ahead-Bench: Standardized Benchmark of Look-ahead Bias in Point-in-Time LLMs | arXiv 2601.13770 **[S]** | Benchmark |
| Detecting Lookahead Bias in LLM Forecasts | arXiv 2512.23847 **[S]** | Detection method |
| MemGuard-Alpha: Filtering Memorization-Contaminated Signals via Membership Inference and Cross-Model Disagreement | arXiv 2603.26797 **[S]** | Uses cross-model disagreement as a *filter* |
| Do Large Language Models Understand Chronology? | arXiv 2511.14214 **[S]** | Temporal reasoning failures |
| Debiasing LLMs by Fine-tuning | arXiv 2604.02921 **[S]** | Mitigation |

**Verdict:** heavily worked. Note MemGuard-Alpha uses cross-model disagreement *instrumentally* —
it is adjacent to our recommended program but treats disagreement as a tool, not as the object of study.

### A3. Algorithmic collusion
| Work | ID | Claim |
|---|---|---|
| AI-Powered Trading, Algorithmic Collusion, and Price Efficiency | NBER WP 34054, Dou/Goldstein/Ji **[S]** | RL speculators sustain supracompetitive profits w/o communication. *Under revision at AER.* |
| Algorithmic Collusion by Large Language Models | arXiv 2404.00806, Fish/Gonczarowski/Shorrer **[S]** | LLM pricing agents reach supracompetitive prices |

**Verdict:** top-tier authors, top-tier venues. Do not compete here.

### A4. Bias in LLM credit / investment advice
| Work | ID | Claim |
|---|---|---|
| Measuring and Mitigating Racial Bias in LLM Mortgage Underwriting (Bowen, Price, Stein, Yang) **[S]** | — | Racial gap ~56% larger for low-score applicants |
| Who Invests, Who Gets Funded: Gender & Racial Bias in LLM Investment Advice | J. Business Ethics 2026 **[S]** | Allocation favours non-Black and male managers |
| Generative AI as an Investment Advisor: Same Client, Different Advice | FinTech 5(2) 54 **[S]** | Conjoint audit of 3 frontier models |
| Biased Echoes: LLMs reinforce investment biases, raise portfolio risk **[S]** | PMC12204588 | Debiasing only partially works |
| One Size Fits None: Heuristic Collapse in LLM Investment Advice | arXiv 2604.23837 **[S]** | Suitability collapses to one dimension |
| MASCA: LLM Multi-Agent System for Credit Assessment | arXiv 2507.22758 **[S]** | 4/5ths-rule violations |

**Verdict:** the demographic-audit lane closed during 2026. Dead.

### A5. LLM ethics / deception / fiduciary breach in finance
| Work | ID | Claim |
|---|---|---|
| LLMs Can Strategically Deceive Their Users When Put Under Pressure (Apollo Research) | ICLR 2024 workshop **[S]** | GPT-4 trading agent does insider trading, then lies |
| Chat Bankman-Fried: An Experiment on LLM Ethics in Finance | CEPR **[S]** | Models violate fiduciary duty; respond to incentives/regulation as theory predicts |
| Ads in AI Chatbots: How LLMs Navigate Conflicts of Interest | arXiv 2604.08525 **[S]** | Conflict-of-interest behaviour |

**Verdict:** the demo *and* the systematic follow-up both exist now.

### A6. Generic LLM information degradation in chains
| Work | ID | Claim |
|---|---|---|
| When LLMs Play the Telephone Game: Cultural Attractors in Iterated Transmission | arXiv 2407.04503 **[S]** | Iterated LLM chains drift toward attractor states |
| LLM as a Broken Telephone: Iterative Generation Distorts Information | ACL 2025 **[S]** | Factual distortion accumulates; prompting mitigates |

**Verdict:** the "AI telephone game degrades information" primitive is established. A finance-specific
version would be an application, not a discovery.

### A7. Correlated LLM error / effective ensemble size ← **closest to our recommendation**
| Work | ID | Claim | Domain |
|---|---|---|---|
| Correlated Errors in Large Language Models | arXiv 2506.07962, ICML 2025 **[S]** | 350+ models; agree 60% of the time when both err; **more accurate models correlate MORE** | General |
| The Oracle's Fingerprint | arXiv 2605.00844 **[S]** | GPT-4o/Claude/Gemini, **568 already-resolved** binary questions, r = 0.77 (0.78 ex-leaked). Retrospective. Its own stated gap: *"a monoculture built but not yet activated"* | General forecasting |
| Preference Optimization Drives Monoculture in LLM Prediction Markets | arXiv 2606.26583 **[S]** | Simulated DPO agents 8B/70B; rho = 0.70; **10 agents ≈ 1.4 effective**; cross-model diversity 0.68 → 0.40. **Publishes the "1.4" figure our pitch was using.** | Prediction markets (simulated) |
| Nine Judges, Two Effective Votes | arXiv 2605.29800 **[S]** | 9 LLM judges ≈ 2 effective votes; ~¾ of nominal independence lost | LLM-as-judge |
| Are Diversity Metrics Measuring Diversity? | arXiv 2607.20768 **[S]** | 31,900 subsets of 30 LLMs; diversity metrics are **entangled with accuracy** (Spearman rho = +0.99 vs 1 − mean accuracy); voting beats the best member in only 10% of size-3 subsets. **Demands explicit capability controls.** | General |

**What this means for us (assessed 17 Aug 2026).** The *level* of LLM error
correlation is no longer novel, and our original "nobody has measured this" claim
is withdrawn. Five things remain genuinely unoccupied, and they are now the
contribution: (1) prospective, pre-registered collection where the outcome does
not exist at ask time, so contamination is impossible by construction rather than
argued away; (2) **conditional** measurement — whether correlation rises under
stress and ambiguity — which arXiv 2605.00844 explicitly names as its own open
question; (3) a **structurally matched** human benchmark (SPF RECESS: individual
probability forecasts of a binary event); (4) an explicit **capability control**,
which arXiv 2607.20768 shows most work in this area fails; (5) document-grounded
finance tasks whose targets are quarters not yet filed.
| The Oracle's Fingerprint: Correlated AI Forecasting Errors | arXiv 2605.00844 **[F]** | 568 resolved binary questions; pairwise error r ≈ 0.74–0.82 vs 0.1–0.3 for humans | **Not finance.** No conditional analysis. |
| Nine Judges, Two Effective Votes: Correlated Errors Undermine LLM Evaluation Panels | arXiv 2605.29800 **[S]** | 9-judge panel → 2.18 effective voters | LLM-as-judge |
| Wisdom of LLM Crowds: Aggregation and Contamination in Language Model Ensembles | arXiv 2607.18269 **[F]** | 15 LLMs × 254 prediction-market questions; learned aggregation beats individuals; contamination is "a pervasive confound" | Prediction markets. **No state-dependent correlation.** |
| Diversity is the Strength of the AI Crowd | arXiv 2606.29661 **[S]** | Less-correlated models contribute disproportionately | General |
| Quantifying Correlations of Machine Learning Models | arXiv 2502.03937 **[S]** | Methodology | General |

**Verdict — important:** the *metric* (error correlation → effective N) is established and we must
concede it. What is **absent from every one of these**: financial-market tasks with economic loss
functions, **conditional/state-dependent correlation**, and any transmission to prices.

### A8. Live / contamination-free financial LLM benchmarks
| Work | ID | Claim |
|---|---|---|
| ForecastBench: A Dynamic Benchmark of AI Forecasting Capabilities | arXiv 2409.19839, ICLR 2025 **[S]** | Live, contamination-free, 1000 questions, human comparison. Experts still beat best LLM. |
| LLMs and Stock Investing: Is the Human Factor Required? | arXiv 2603.19944 **[F]** | Live 10-month eval (Apr 2025–Jan 2026), 4 models × 3 prompting strategies. **Measures accuracy/returns only — no cross-model error correlation.** |
| FutureX / Alpha Arena / RockAlpha / LiveTradeBench **[S]** | — | Live anti-contamination agent-trading benchmarks |

**Verdict:** prospective evaluation in finance already exists. Our moat is **not** "we run it live" —
it is **what we measure while running it live**.

---

## B. PARTIALLY OPEN — viable with a sharpened angle

### B1. AI authorship of corporate disclosure
| Work | ID | Claim |
|---|---|---|
| The Widespread Adoption of LLM-Assisted Writing Across Society | Patterns 2025, Liang et al. (arXiv 2502.09747) **[S]** | **Up to 24% of corporate press-release text is LLM-assisted; ~18% of financial consumer complaints.** Population-level estimator — methodologically reusable by us. |
| The Adoption and Efficacy of LLMs in US Consumer Financial Complaints | Nature Human Behaviour 2026 **[S]** | Adoption + outcome effects |
| Investor Reactions to GenAI Usage in MD&A Disclosures | SSRN 5068116, Plate/Voshaar/Zimmermann **[S]** | 6,977 firm-years 2021–23; GenAI use → adverse short-window CAR; readability up, tone unchanged |
| How to Talk When a Machine Is Listening (Cao, Jiang, Yang, Zhang) | RFS 2023 **[S]** | Firms adjust disclosure to machine readership — **pre-LLM era, dictionary-based** |
| AI Disclosure in Annual Reports | J. Information Systems 2026 **[S]** | Post-ChatGPT AI risk disclosure less boilerplate |

**Open:** the *generative*-era version of Cao et al. — whether text is now optimised for LLM readers,
and whether a measurable wedge exists between machine-read and human-read sentiment.

### B2. Systemic risk from AI homogeneity — theory exists, calibration does not
| Work | ID | Claim |
|---|---|---|
| Representation Homogeneity and Systemic Instability in AI-Dominated Financial Markets | arXiv 2604.22818 **[F]** | Structural 2-layer model; representation similarity → volatility clustering, liquidity stress, hidden leverage. **Simulation only; no empirical dataset.** |
| AI Agents in Financial Markets: Architecture, Applications, Systemic Implications | arXiv 2603.13942 **[F]** | Framework (AFMM). Author states it **"does not validate the full AFMM"**; empirical validation listed as open. |
| FSB, *Monitoring Adoption of AI and Related Vulnerabilities in the Financial Sector*, Oct 2025 **[S]** | — | Names "increased market correlations from similar AI models" as a top-4 risk |
| Bank of England, *Financial Stability Report*, Jul 2026 **[S]** | — | BoE "pursuing work on simulation methods… to understand conditions under which AI agents could demonstrate correlated behaviour or herding" |
| IMF, Jul 2026 — central banks & AI trading risk **[S]** | — | Presses central banks on AI herding |

**Open, and explicitly flagged as open by two 2026 papers and three regulators:** an *empirically
calibrated* correlation parameter. Everyone assumes it. Nobody has measured it in finance.

### B3. Replication / spurious predictability in financial ML
| Work | ID | Claim |
|---|---|---|
| Spurious Predictability in Financial Machine Learning | arXiv 2604.15531 **[S]** | Adaptive specification search + leaky validation inflate results |
| Is There a Replication Crisis in Finance? | J. Finance 2023, Jensen/Kelly/Pedersen **[S]** | Most factors replicate; 153 characteristics, 93 countries. **Data free at jkpfactors.com** |

---

## C. INFRASTRUCTURE AVAILABLE (verified reachable 16 Aug 2026)

| Resource | Status | Note |
|---|---|---|
| SEC EDGAR submissions API (`data.sec.gov`) | **HTTP 200 ✓** | Free, no key, needs UA header |
| SEC EDGAR full-text search (`efts.sec.gov`) | **HTTP 200 ✓** | Free, no key, 2001→present, all exhibits |
| SEC XBRL `companyfacts` | Free | Ground-truth reported financials |
| FRED (St. Louis Fed) | **HTTP 200 ✓** | Macro releases, scheduled, free API |
| Kalshi public market data | Free, **no auth** | CFTC-regulated event contracts → market-implied probability benchmark |
| Polymarket Gamma/CLOB read endpoints | Free, no auth | ~1,000 calls/hr |
| JKP Global Factor Data (jkpfactors.com) | Free download | Factor returns without WRDS |
| ABIDES (JPMorgan, open source) | Free | Nanosecond LOB simulator, ITCH/OUCH-modelled |
| Stooq daily prices | **Unusable** — returns HTTP 200 but body is a SHA-256 proof-of-work JS challenge | Status code is misleading; must inspect body. Use yfinance / Tiingo / Nasdaq Data Link instead |
| Local Python | 3.9.6, **no numpy, no pandas** | pip 21.2.4. Needs a venv + scientific stack — Week-0 task |

Verification method: `curl` status **and body inspection** on 16 Aug 2026. Body inspection matters —
Stooq returned 200 with a challenge page. Never trust the status code alone.

---

## D. VENUE & DEADLINE CALENDAR

| Venue | Date | Note |
|---|---|---|
| **ICAIF'26 main track** | Deadline **9 Aug 2026 — PASSED 7 days ago** **[F]** | 7th ICAIF, Milan, **14–17 Nov 2026**. Workshop tracks usually reopen ~Sept — worth watching. |
| **Regeneron STS 2027** | **5 Nov 2026, 8:00pm ET** **[F]** | HS seniors only. Opened 1 Jun 2026. Max 20-page paper. **11.4 weeks from today — binding constraint.** |
| **JSHS 2027** | Regional abstracts **Oct–Dec 2026**; regionals Jan–Mar; nationals Apr | Varies by region |
| **Regeneron ISEF 2027** | **8–14 May 2027**, Los Angeles | Qualify via regional fair Jan–Mar 2027 |
| ICLR 2027 workshops | ~Feb 2027 | Good fit for the measurement contribution |
| ICAIF'27 | ~Aug 2027 | Full-paper target |
| arXiv / SSRN preprint | **Immediately on result** | Priority defence — see dossier §9 |

ISEF rule note: generative AI **may not** write the research plan, abstract, poster, or citations;
it may be used as a research resource with citation. Using LLMs as the *object of study* is fine.
No human subjects in any candidate → no IRB.

# The Illusion of Many Minds — plain-language explainer

Written to be read by someone with no background in AI or finance. Use it for the abstract, for
explaining the project to a teacher or mentor, and as the elevator pitch.

---

## What we're researching

Banks, hedge funds and investment firms are replacing human analysts with AI, fast. Different firms
use different AI systems — one uses OpenAI's models, another Anthropic's, another Google's, another
runs an open-source model on its own servers.

On the surface that looks like a healthy, diverse market. Many different decision-makers. Many
different opinions.

**We're asking whether that diversity is real, or an illusion.**

Here is the worry. All of these AI systems learned from heavily overlapping material — much of the
same internet, the same financial textbooks, the same news archives, and increasingly each other's
output. So when a situation is clear, each one can reason from the evidence in front of it, and they
can genuinely disagree.

But when the evidence is *murky* — a confusing economic report, an unprecedented event, a real
crisis — a model has less to reason from, and falls back on the assumptions it absorbed during
training. **And those assumptions are shared.** If that's right, then in exactly the situations that
matter most, seven different AI systems stop being seven different opinions and start being one
opinion wearing seven hats.

**Why that's dangerous:** markets only function because people disagree. A market needs someone
willing to buy when someone else is selling. If every AI-driven fund reaches the same conclusion at
the same moment, they all rush for the same exit at once — and that is what a crash *is*.

So we measure how many genuinely independent judgements the market is actually getting from AI, and
whether that number collapses precisely when independence matters most.

---

## The research question

> **When AI systems make financial decisions, how many genuinely independent judgements is the
> market actually receiving — and does that number collapse precisely when markets are under stress?**

There's a well-known saying in finance: *"in a crisis, all correlations go to one."* Investments that
normally move independently suddenly move together, so diversification fails exactly when you need
it. **Our hypothesis is that AI thinking has the same disease** — and for a reason we can identify
and measure.

---

## How we'll actually do it

Every day for fifteen weeks, we ask seven different AI systems the same set of real financial
questions about things that **haven't happened yet** — what will next month's inflation number be,
will this company beat its earnings estimate, how will the market read this Federal Reserve statement.

Then we wait for reality to settle it, and we score them.

The key measurement isn't whether they *agree*. It's whether they're **wrong in the same way at the
same time.** Two forecasters who are both right aren't a problem. Two who are wrong identically are
a single point of failure pretending to be two.

Then we check whether that shared-wrongness gets worse when markets are stressed or the question is
ambiguous.

**One detail matters more than any other:** we ask about events that have not happened yet. AI models
were trained on the past, so if you test them on history, they may simply be remembering rather than
reasoning — this has sunk a lot of published work in this area. By asking only about the future, that
problem is impossible by construction. It also means our dataset can't be copied: a competitor
starting later cannot go back and collect September's forecasts.

---

## Why it's unique

**1. A live policy debate is missing exactly the number we'd produce.**
Three of the world's financial regulators — the Financial Stability Board, the Bank of England, and
the IMF — have each publicly named "many institutions running similar AI models" as a top-tier threat
to financial stability. Academic papers model what happens *if* AI systems are highly correlated.

Every single one of them has to **assume** a number, because nobody has measured it. We'd measure it.

**2. Everyone else treats it as a fixed constant. We think it's a variable.**
The handful of studies that measure AI agreement produce one number — an average. Our claim is that
the average is the wrong object entirely, because the number *moves*, and it moves in the worst
possible direction: it gets worse under stress. That's the difference between "AI ensembles are
somewhat redundant" and "AI ensembles fail when you need them."

**3. We predict it before it happens.**
We calibrate on the first five weeks, then publicly post a timestamped, specific numerical prediction
about the next big market surprise — and test it against events that didn't exist when we wrote it
down. Almost nobody in this field does this. It's the difference between explaining the past and
forecasting the future.

**4. We look inside the models for the cause.**
For the open-source models we can inspect internal states and ask whether systems that *represent* a
situation similarly are the ones that fail together. The leading theory paper in this area builds its
whole argument on that distinction — and never actually measures it. We can.

---

## Why it's good research

| | |
|---|---|
| **It can be proven wrong** | We state in advance what result would refute us. Judges and reviewers trust a study that can lose |
| **The stakes are real and named** | Not a hypothetical harm — three central institutions have said this in public documents |
| **It's honest about what's borrowed** | The core metric already exists. We cite it prominently and claim none of it. What's ours is applying it to finance, conditionally, and predicting forward |
| **It's cheap and self-contained** | ~$200, all public data, no lab, no institutional database, no human subjects |
| **It survives a bad outcome** | Three independent findings. If the main hypothesis fails, two others still stand — plus a confirmed null is itself a real result |
| **It can be shown, not just described** | A live meter where you watch AI independence collapse as a scenario gets murkier |
| **It leaves something behind** | An open dataset nobody can rebuild, and an open-source tool anyone can use on their own AI systems |

---

## Time commitment

**15 hours per week · 19 weeks · ~290 hours total · finished 31 December 2026**

The data collection itself is **automated** — it runs on a daily schedule without anyone touching it.
The 15 hours a week is real work: building, analysing, writing. Not babysitting a script.

The load is not flat across the project:

| Phase | Weeks | Hours/wk | What it feels like |
|---|---|---|---|
| **Build** | 0–1 (Aug 17–30) | 15 | Heaviest coding. Harness, pre-registration, automation. Front-loaded on purpose so collection starts early |
| **Collect & build analysis** | 2–5 (Aug 31–Sep 27) | 10–12 | Lightest stretch. Collection runs itself; time goes to writing analysis code and the first look at results |
| **Analyse** | 6–13 (Sep 28–Nov 22) | 15 | Statistics, the mechanism work, the prediction test. The intellectual core |
| **Buffer** | 14–15 (Nov 23–Dec 6) | 10–15 | Deliberate slack. Something always breaks |
| **Write** | 16–19 (Dec 7–31) | 15–18 | Paper, figures, poster, open-source release |

**Two dates that matter:**
- **~6 October** — the pre-registered prediction is posted publicly. After this it cannot be edited.
- **6 December** — data freeze. Collection stops, nothing more is added, analysis is final.

**One thing cannot be rescheduled:** the fifteen-week collection window. Every other task can move.
A week of collection not started is simply gone — you cannot buy it back later, at any price. That's
why the build is front-loaded into the first two weeks.

### Collection and analysis end at different times

A natural question: does everything run until late December? No — and the gap is deliberate.

- **Data collection stops 6 December.**
- **Analysis and writing run 7–31 December.**

Three and a half weeks of writing sounds tight, but the analysis is *not* crammed into it. Analysis
code is built and re-run continuously from Week 6 onward, on data accumulating as it arrives. By the
freeze, the whole pipeline has been written, tested and run dozens of times on partial data.
December is the **final pass plus prose** — not doing the science from scratch. The intellectual core
happens 28 Sep – 22 Nov.

**We get the longer panel anyway.** The collector is automated, so there's no reason to switch it off
on 6 December. Let it keep running into 2027 at near-zero cost:

- The **December paper** uses data through 6 Dec — frozen, clean, finished.
- The **2027 conference version** (ICLR workshops ~Feb, ICAIF'27 ~Aug) uses 25+ weeks.

That beats extending the freeze. Collecting to 20 December would add two weeks of data — well into
diminishing returns after fifteen — while cutting writing from 25 days to 11. Bad trade.

**The freeze date itself cannot move.** Once it passes, no new data enters the December analysis,
even if something interesting happens on the 15th. That is precisely what makes the pre-registered
prediction credible: you cannot quietly extend the window until the result looks good. A dramatic
event on 20 December goes into the 2027 version as genuine out-of-sample confirmation — worth far
more than folding it in late.

---

## The thirty-second version

> Banks are handing financial decisions to AI. Different banks use different AI, which looks like a
> diverse market. But these systems all learned from the same material, so when a situation gets
> genuinely confusing they may all fall back on the same assumptions and be wrong together —
> precisely when the market most needs someone to disagree.
>
> Regulators in three countries have called this one of the biggest emerging risks to the financial
> system. Nobody has measured it.
>
> I'm measuring it — by asking seven AI systems to forecast real financial events every day for
> fifteen weeks, scoring not whether they agree but whether they're **wrong in the same way at the
> same time**, and testing whether that gets worse under stress. I'll predict it in advance and
> check the prediction against events that hadn't happened yet, look inside the models to find the
> cause, and build the instrument that measures it.

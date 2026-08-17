# Four-Year Strategy — Charlotte, NC · 9th grade, 2026–27

## 1. The insight that changes everything

You are in **ninth grade**. That means:

| School year | Grade | Cycle |
|---|---|---|
| 2026–27 | 9 | ISEF 2027 · NC JSHS 2027 · Davidson |
| 2027–28 | 10 | ISEF 2028 · JSHS · workshop papers |
| 2028–29 | 11 | ISEF 2029 · JSHS · full conference paper |
| 2029–30 | 12 | **ISEF 2030 · Regeneron STS 2030** (apply ~Nov 2029) |

**Four ISEF cycles. Three years before STS.** Nobody told you to think in these terms yet, so here it
is plainly:

> **This should not be a three-month project. It should be the first phase of a four-year research
> program, and the design we've built happens to be almost uniquely suited to that.**

### Why this specific project compounds

Most science-fair projects are disposable — you finish, you present, you start something unrelated
next year. **Ours has an asset that grows on its own: the prospective panel.**

If the collector runs continuously from September 2026 to November 2029, you arrive at your STS
application holding a **three-year daily record of cross-model financial forecasts.** That dataset:

- **Cannot be rebuilt by anyone, ever.** Not by a lab, not by a hedge fund, not for any amount of
  money. Retrospective reconstruction is impossible by construction.
- **Captures model generational change.** Over three years the frontier will turn over several
  times. You would hold a continuous record of whether cross-model correlation *rose or fell as
  models advanced* — which is the actual question regulators care about and which nobody is
  positioned to answer.
- **Costs almost nothing to maintain.** It's automated. Roughly $150–200/year and a few hours a
  month once built.

That last point is the whole trick. **The marginal cost of leaving it running is near zero, and the
value compounds annually.** A three-year panel isn't "impressive for a high schooler" — it would be
genuinely rare in the field.

---

## 2. The year-by-year arc

**Year 1 (now → Dec 2026) — establish the instrument.**
Build the panel, measure N_eff conditionally, run the pre-registered prediction, write the paper.
→ Region 6 fair (Jan 2027) → NCSEF state → **ISEF 2027**. NC JSHS 2027. arXiv preprint (Oct).
Davidson Fellows (~Feb 2027).

**Year 2 (2027–28) — the longitudinal turn.**
New question the panel alone can answer: *did correlation change as the models changed?* Add the
representation arm properly. Target an **ICLR or NeurIPS workshop** — the highest-leverage item on
the whole list.

**Year 3 (2028–29) — generational analysis.**
Two-plus years of data. Full **ICAIF** conference paper. This is where the work stops looking like a
student project and starts looking like a research program.

**Year 4 (2029–30) — the STS submission.**
Apply November 2029 with a three-year panel, multiple confirmed out-of-sample predictions, a
published preprint, and likely a peer-reviewed workshop paper. That is a categorically different
application from anything assembled in a single senior-year push.

---

## 3. Charlotte specifics

**Both your venues are at the same place — UNC Charlotte's Center for STEM Education.**

| Venue | Status |
|---|---|
| **Region 6 NC Science & Engineering Fair** (Southwest / Charlotte-Mecklenburg) | 2027 dates **TBD** — regional directors finalising, site updates expected **mid-September 2026** |
| **North Carolina JSHS** | Also hosted by UNC Charlotte CSTEM. 2027 details posted in fall 2026 |

**Path to ISEF:** Region 6 → **NCSEF state fair** → ISEF 2027 (8–14 May, Los Angeles).

**Registration runs through STEM Wizard** (`ncsefreg6.stemwizard.com`). Region 6 asks for a digital
project presentation and a **quad chart** — note that, it's a Region-6-specific format worth building
early rather than the night before.

**Week-0 action:** check both UNC Charlotte pages in mid-September for 2027 dates, and confirm
whether Region 6 requires a full research paper or abstract-only. That single answer sets the
December writing scope.

**One relationship, two venues, both local.** Worth being known there early — go to the fair as a
spectator in January if you can.

---

## 4. The honest part: you have to own the statistics

I described earlier why the paper matters — *it's how you come to own the argument.* In ninth grade
that stops being a nice principle and becomes the central risk of this plan.

The design calls for block-bootstrap confidence intervals, multiple-testing correction, CKA
representational similarity, and a closed-form market model. **A ninth grader can absolutely learn
all of this — but you have to actually learn it, not just run code I write.**

Two reasons, and the second is the one that decides outcomes:

1. **ISEF judging is an interview.** Judges probe exactly where a student is weakest: *why a block
   bootstrap instead of a standard one? what would falsify this? how do you know that's not an
   artifact of your task mix?* A ninth grader who can answer those will astonish a judging panel. One
   who can't gets found out in ninety seconds, and no amount of polish saves it.
2. **It's the difference between having done research and having watched research happen.**

**So the working split is explicit:**

| I do | You must own |
|---|---|
| Infrastructure, API plumbing, data pipelines, automation | **The statistics** — what each test does and why that one |
| Literature retrieval, prior-art checking | **The argument** — the hypotheses and what would refute them |
| Draft figures and analysis scaffolding | **The interpretation** — what the numbers mean |
| Boilerplate and formatting | **The writing** |

I'll build a learning track alongside the schedule: correlation and covariance → sampling
distributions → bootstrap → multiple testing → the specific estimators we use. Roughly 2–3 of your
15 weekly hours, front-loaded into Weeks 2–5 when collection is running itself and the workload is
lightest. That's the natural slot and it's already in the plan.

---

## 5. De-risking Year 1: must-ship vs stretch

The elevated design is genuinely demanding for 290 hours — for anyone, before adding a learning
curve. So we split it, and we decide in advance rather than in December:

**Revised after re-scoping — I was too conservative the first time.** Two of the three "stretch"
items are cheap: the transmission result is *mathematics*, and the lineage test is *analysis on data
we already have*. Both fit the light collection weeks. Only one item genuinely needs to defer.

**Year 1 ships all of this:**

| Component | Hours |
|---|---|
| Harness, OSF + GitHub pre-registration, automation | 22 |
| Panel operation and monitoring (15 weeks) | 35 |
| **Human baseline — SPF professional forecasters** ★ | 25 |
| Econometrics: N_eff, state-dependence, block bootstrap | 40 |
| Pre-registered out-of-sample prediction protocol | 10 |
| Distribution-level correlation (logprobs) | 8 |
| Lineage-as-predictor | 12 |
| Closed-form transmission result | 18 |
| Public live dashboard + poster demo | 22 |
| `neff` package: tests, docs, CI | 15 |
| Outreach — researchers, regulators | 5 |
| **Statistics learning track** (non-negotiable) | 25 |
| Paper, poster, quad chart | 53 |
| **Total** | **290** |

**Deferred to Year 2 — one item only:** the **CKA representation arm.** It needs local model
infrastructure on an 8 GB machine, and it is the only component whose hours are genuinely
unpredictable. The human baseline replaces it as the project's centrepiece — and is *better* for
that role, because a judge understands it instantly.

**Read the total honestly: 290 hours is exactly the budget, with zero slack.** So the cut order is
decided now, in advance, not in December:

1. **Dashboard** goes first — it is presentation, not science.
2. **Closed-form transmission** goes second.
3. **The statistics learning track and the paper are never cut.** They are what makes the work yours
   and what survives judging.

---

## 6. NCSSM — you likely have a year more than you think

**Verify this directly with admissions, because it changes your timeline by twelve months.**

NCSSM's published requirement: **"Applicants for the Residential and Online programs must be in
their second year of high school."** The cycle currently open — **Class of 2029, 15 Oct 2026 →
5 Jan 2027** — is for students who are sophomores *now*.

You are in ninth grade. So your cycle is almost certainly **Class of 2030, opening ~Oct 2027 and
closing ~Jan 2028.**

If that's right, the consequences are large and entirely good:

| Milestone | Date | Before your NCSSM app? |
|---|---|---|
| arXiv preprint | Oct 2026 | ✓ by ~15 months |
| Finished paper | Dec 2026 | ✓ |
| Region 6 fair | Jan 2027 | ✓ |
| NC JSHS | Feb–Mar 2027 | ✓ |
| **ISEF 2027** | **May 2027** | **✓ — results in hand** |
| ICLR workshop submission | Feb 2027 | ✓ |
| Year 2 work underway | Fall 2027 | ✓ |

You would apply holding a **completed, competition-tested, publicly published research program** —
not a project in progress. That is a categorically different application.

Also note: **NCSSM does not accept SAT or ACT scores at all** for this cycle. Test prep buys you
nothing there. Research does.

**Action:** email admissions@ncssm.edu and confirm which class year a current ninth grader applies
for. One email, and it settles whether your deadline is 4 months or 17.

---

## 7. Conference calendar — what's actually reachable

**Verified dates:**

| Venue | Deadline | Event | Reachable? |
|---|---|---|---|
| **arXiv / SSRN preprint** | none | immediate | **✓ Oct 2026** — do this first |
| ICLR 2027 **main track** | **24 Sep 2026** (abstract 19 Sep) | Apr 2027, Brazil | **✗** — five weeks away; our data would be ~20% collected |
| **ICLR 2027 workshops** | ~Feb 2027 | Apr 2027, Brazil | **✓ best first real target** |
| ICML 2027 main | ~22 Jan 2027 | Jul 2027 | ✓ timing works, but see below |
| **NeurIPS 2027** | abstracts **mid-May 2027**, papers ~1 wk later | Dec 2027, Europe | **✓** — we'd have Dec paper + 5 more months of data |
| NeurIPS 2027 workshops | ~Aug–Sep 2027 | Dec 2027 | ✓ |
| **ICAIF'27** | ~Aug 2027 | Nov 2027 | ✓ the natural home |

**One thing to be clear-eyed about:** NeurIPS, ICML and ICLR **main tracks** run ~20–30% acceptance
and are dominated by full-time researchers with lab resources. They are not a realistic first target,
and aiming there first mostly buys a rejection.

**Workshops are the real target** — genuine peer review, citable, listed on the conference site,
dramatically higher acceptance. *A ninth grader with an accepted ICLR workshop paper is a genuinely
remarkable line.* Main tracks become plausible in Year 3, on a two-year panel.

Order of operations: **preprint (Oct 2026) → ICLR workshop (Feb 2027) → ICAIF'27 or NeurIPS
workshop (Aug 2027) → main track, Year 3.**

---

## 8. Is Year 1 alone worth ISEF and JSHS nationals?

**Yes.** The must-ship set is a complete project, and here is the concrete case:

| What we'll have | How common at ISEF |
|---|---|
| A **pre-registered, timestamped, out-of-sample prediction** that was tested | **Very rare.** Most projects fit a model to data already in hand |
| 15 weeks of **prospective data no one can reconstruct** | Rare |
| A question **three financial regulators have publicly posed** | Rare |
| Stated refutation conditions — we say in advance what would prove us wrong | Uncommon |
| An open dataset and open-source instrument | Uncommon |

The ISEF median project is closer to *"I applied model X to dataset Y and got Z% accuracy."* Ours
sits well above that line, and the pre-registration alone distinguishes it from nearly everything in
the room.

**The honest caveat:** the topic gets you into the room. **Execution and your command of the material
decide the award.** A ninth grader who can explain why a block bootstrap rather than a standard one
will astonish a panel; one who can't will be found out regardless of how good the topic is. That is
exactly why §4's learning track is not optional.

---

## 9. What to do in the next two weeks

1. **Start the panel.** Every day of delay is a day of data that cannot be recovered. This dominates
   every other consideration.
2. **Mid-September:** check UNC Charlotte for Region 6 and NC JSHS 2027 dates; confirm the paper
   requirement.
3. **Decide the budget** ($200 cap) and buy credits.
4. **Begin the statistics track** in Week 2, when collection is self-running.

Being in ninth grade is not a handicap here. It's three extra years of compounding on an asset
nobody else is building.

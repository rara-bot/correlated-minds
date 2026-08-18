# OSF Pre-Registration — complete walkthrough

**Status: NOT DONE. This is the one thing I cannot do for you.**

I can't create accounts, and I shouldn't — a pre-registration is a signed
scientific commitment with your name on it. It has to be your account, your
click. Everything else below I've already prepared; your job is roughly
**35 minutes of typing and pasting.**

---

## OSF or Zenodo? Both — at different times

Asked and settled 18 Aug 2026.

| | OSF (now) | Zenodo (December) |
|---|---|---|
| Built for | **preregistration** | archiving research outputs |
| The object | a **Registration** — immutable, withdrawable only, leaves a tombstone | a versioned archive; new versions supersede old |
| Structure | forced fields: hypotheses, analysis plan, exclusions | free-form file upload |
| Indexed as | a preregistration, in OSF Registries | a dataset/software record |
| DOI | yes | yes |
| Cost | free | free |

The claim you must defend is *"I specified these hypotheses before any data
existed."* On OSF a reviewer reads `Registration · 22 Aug 2026` and knows exactly
what that means. Zenodo would prove the file existed on that date, but nothing
labels it a preregistration and a skeptic has to walk version history instead of
trusting immutability by design.

The less obvious reason, and the better one: **the OSF form is the value, not the
overhead.** Being forced to write your exclusion criteria into a box before you
have data is the mechanism that stops hypotheses drifting toward whatever the
data shows. Zenodo has no such box. Uploading a file skips the part that does the
work.

**Zenodo's turn comes in December** — see "Step 8" at the end of this document.

---

## Why this is worth 35 minutes

Your entire claim is *"I predicted this before it happened."* A judge's first
private thought is *how do I know you didn't write the prediction after seeing
the result?*

OSF answers that permanently. You upload your plan, OSF freezes it, and issues a
public URL with a DOI and a date stamp that **not even you can edit afterwards**.

You are doing it belt-and-braces: OSF **plus** a SHA-256 hash of the plan
committed to git. Two independent ways for a skeptic to verify.

---

## Do these in order. The order matters.

```
1. Fix nothing more in the plan      ← the plan is now final
2. Push to GitHub                    ← you need the repo URL in step 5
3. Freeze + hash + commit            ← generates the hash you'll paste
4. Make the OSF account & project
5. Create the registration
6. Submit it public
7. Save the URL
```

Step 3 before step 5 is non-negotiable: the hash you publish on OSF has to be the
hash of the document as frozen. If you register first and freeze after, the
numbers won't match and the whole point is lost.

---

## Step 1 — Read the plan once, properly

```bash
open PREREGISTRATION.md
```

**This is the last moment you can change anything.** After the freeze, every
change goes in §11 as a dated, numbered deviation, visible forever.

Read §4 (the hypotheses) and §7 (what would make us abandon a hypothesis). If
anything in there is something you would not be willing to publish when it comes
out *against* you — tell me now, before you freeze.

---

## Step 2 — Push to GitHub (~5 min)

You need a public repo URL to cite inside the OSF registration.

1. Go to **github.com/new**
2. Repository name: `correlated-minds` (anything works)
3. **Public** — this matters. The public commit history is what makes your daily
   timestamps independently checkable.
4. Do **not** tick "Add a README" — you already have one.
5. Click **Create repository**, then run (substituting your username):

```bash
git remote add origin https://github.com/YOUR-USERNAME/correlated-minds.git
git branch -M main && git push -u origin main
```

Copy the resulting URL. Call it **`GITHUB_URL`** — you'll paste it twice later.

> `.env` is git-ignored, so your API keys are not going public. Verify with
> `git status` — if `.env` ever appears in that list, stop and tell me.

---

## Step 3 — Freeze and hash (~2 min)

```bash
./.venv/bin/python scripts/freeze_prereg.py --freeze
```

This stamps the document with a UTC timestamp, computes a SHA-256 hash, and
prints it. It looks like `f4cfaec6dc25...` (64 hex characters).

**Copy that hash somewhere safe.** Call it **`HASH`**.

Then commit and push it:

```bash
git add -A && git commit -m "Freeze pre-registration" && git push
```

Anyone — including you, later — can verify nothing was tampered with:

```bash
./.venv/bin/python scripts/freeze_prereg.py --check
```

---

## Step 4 — OSF account and project (~8 min)

### 4a. Account
1. **osf.io** → **Sign Up** (top right). Free, no institution required.
2. Email + password. Use an email you'll still have in five years — not a school
   address that expires at graduation.
3. Check your inbox and click the verification link. **You cannot register
   anything until the email is verified.**

### 4b. Project
4. On your dashboard, click **Create new project**.
5. **Title:** `Correlated Minds: Error Correlation Across Language Models in Financial Forecasting`
6. **Storage location:** United States (default) is fine.
7. Click **Create**, then **Go to project**.

### 4c. Upload the plan
8. In the project, open the **Files** tab.
9. Click **OSF Storage**, then drag these three files in:
   - `PREREGISTRATION.md` ← the frozen one
   - `VALIDITY.md`
   - `SETUP.md`
10. Wait for each to show a green tick.

### 4d. Make the project public
11. Top right of the project page → the **Public / Private** toggle → set to
    **Public** → confirm.

---

## Step 5 — Create the registration (~15 min)

This is the part that actually freezes things.

1. In your project, open the **Registrations** tab (left sidebar or top nav).
2. Click **New registration** / **Add new registration**.
3. You'll be asked to pick a **template**. Choose **OSF Preregistration**.
   - If you don't see that exact name, **OSF-Standard Pre-Data Collection
     Registration** is an acceptable substitute.
   - Do *not* pick "Registered Report Protocol" — that's for journals that have
     already accepted a proposal.
4. It creates a **draft**. Drafts save automatically; you can leave and come back.

Now fill it in. Below is paste-ready text for every field. **Read each one before
pasting** — it's your name on it, and a judge may ask you to explain any sentence.

---

### Title
```
Correlated Minds: State-Dependent Error Correlation Across Large Language Models in Financial Forecasting, Benchmarked Against Human Professional Forecasters
```

### Description / Summary
```
Financial institutions are delegating analytical judgement to large language models from a small number of vendors. Because those models share overlapping pretraining data, their apparent diversity may not deliver genuine independence of judgement. This study measures, prospectively and daily for 15 weeks, whether seven language models across six vendor families make CORRELATED ERRORS on financial forecasting questions whose answers do not yet exist, and whether that correlation worsens under market stress and question ambiguity. The same estimator is applied to individual human forecasters from the Federal Reserve Bank of Philadelphia's Survey of Professional Forecasters, giving a direct human-versus-machine comparison of diversification headroom.

The Financial Stability Board (Oct 2025), the Bank of England (Jul 2026) and the IMF (Jul 2026) have each named correlated AI-driven behaviour as a systemic risk. None of them measures it. This study supplies the measurement.
```

### Hypotheses
> Copy §4 of `PREREGISTRATION.md` verbatim — H1 through H5 including the
> "FALSIFIED IF" clauses. **Do not summarise it.** The falsification clauses are
> the most valuable thing in the document; they are what make it a
> pre-registration rather than a plan.

### Study type
```
Observational study — prospective, repeated measures. No manipulation of human participants; no human subjects are involved.
```

### Blinding
```
Not applicable in the conventional sense. Structurally, outcome data cannot influence forecasts: every question is posed to every model before its answer exists in the world, and all responses are committed to a public append-only log with a timestamp on the day they are collected.
```

### Study design
> Paste §3 of `PREREGISTRATION.md` (Design), which covers the panel, both task
> types, inclusion criteria and repeated measurement. Then add:
```
Nine models across six vendor families (three of them represented at two tiers, giving three within-family pairs), each pinned to an exact API identifier which is logged on every call so that mid-study vendor model drift is detectable. Sampling temperature fixed at 0 for all models. The daily battery is 60% macro questions (Kalshi event contracts and scheduled statistical releases) and 40% document-grounded filing tasks (SEC EDGAR XBRL). Open questions are re-asked daily until resolution; the unit of observation is the task-day.
```

### Randomization
```
None. Question selection follows the fixed inclusion criteria in §3.3 rather than random assignment. The 10% extended-reasoning subsample used for H2 is drawn with a seeded pseudorandom generator; the seed is recorded in the public code.
```

### Existing data
> **Answer honestly here — this is the field reviewers check hardest.** Select
> **"Registration prior to creation of data"** for the primary data, then paste
> this into the explanation box:
```
The primary data — language model forecasts — do not exist at the time of registration and cannot exist, because every question concerns an event that has not yet occurred. Collection begins 24 Aug 2026.

Disclosed in full: one dataset used in this study DOES already exist and HAS already been analysed. The human benchmark comes from the Philadelphia Fed's Survey of Professional Forecasters (individual responses, 2000-2026), a public archive. We analysed it before registering, and that analysis materially changed this plan: it showed human forecast errors are themselves highly correlated (rho ~ 0.996 at nowcast horizons), which forced us to change the primary outcome from raw correlation to diversification headroom (N_eff - 1) and to target longer forecast horizons where headroom is measurable. This is documented in §2 of the attached plan. The measured human values are stated in advance here so they cannot be adjusted later: headroom 0.126 for unemployment and 0.086 for CPI at three quarters ahead.
```

### Data collection procedures
```
An automated job runs daily at 13:10 UTC, selects that day's questions under the fixed inclusion criteria, queries all nine models at temperature 0 with an identical prompt, and appends every response, token count and cost to public JSONL files committed to a public GitHub repository. Resolutions are ingested from official sources (statistical agency releases, SEC EDGAR filings, Kalshi settlements) once the outcome exists. Because collection and commits are automated and public, the claim that each forecast preceded its outcome is externally checkable from the commit history rather than asserted.
```

### Sample size
```
Target approximately 25 task-days x 7 models x 105 collection days ~ 18,375 observations, across roughly 400 distinct resolved questions.
```

### Sample size rationale
```
Powering the stress-tercile contrast in H1 requires roughly 300 task-days per tercile; the target supplies about 600, leaving margin for attrition and model failures. Separately, 400 resolved questions estimate mean pairwise error correlation precisely enough to distinguish rho = 0.996 from rho = 0.990 at approximately 7.7 sigma — a distinction that matters because those two values differ by a factor of about two in practical diversification benefit despite both rounding to 1.
```

### Stopping rule
```
Calendar-based and fixed in advance, never data-dependent. Collection stops at the data freeze on 6 Dec 2026 regardless of results. No interim result may extend, shorten or otherwise alter collection.
```

### Manipulated variables
```
Prompt variant (five registered variants of one question, used only for the H3 intra-model diversity arm) and model identity. No other manipulation.
```

### Measured variables
```
Primary outcome: diversification headroom, headroom = N_eff - 1, where N_eff = M / (1 + (M - 1) * rho_bar) and rho_bar is mean pairwise correlation of forecast ERRORS (e_it = f_it - y_t), not of forecasts.

Always reported alongside it: (a) variance_reduction, the model-free ratio Var(panel mean error) / mean(Var of individual errors), which assumes no correlation structure; and (b) rho_bar itself to four decimal places.

State variables for the H1 conditional test, fixed with no additions permitted: VIX level, 20-day realised volatility, cross-model forecast dispersion, absolute macro surprise, days to resolution, novelty score.
```

### Indices
```
N_eff is the standard effective-ensemble-size index under equicorrelation. Where N_eff and the model-free variance_reduction diverge, the equicorrelation assumption is doing work, and we report that divergence explicitly rather than concealing it behind a single number.
```

### Statistical models
```
H1: regression of pairwise error products on standardised state variables with task-clustered standard errors; plus a top-versus-bottom stress tercile comparison of headroom.
H2: on the 10% extended-reasoning subsample, comparison of cross-model rationale similarity and of evidence-sensitivity across ambiguity terciles.
H3: headroom compared across matched-size panels — one model under 5 prompt variants, the three within-family pairs, and family-matched cross-family pairs. Inference by exact permutation over family labels.
H6: pairwise error correlation regressed on a same-family indicator plus the pair's mean Brier skill and skill gap, to separate shared lineage from shared capability.
H4: difference in variance reduction, humans minus AI, on matched macro questions, with human panels subsampled to M = 9 over 500 random draws. The primary human benchmark is SPF RECESS (individual probability forecasts of a binary event), which is structurally identical to the AI task. Reported only alongside both panels' Brier scores, and at matched accuracy.
H5: headroom estimated separately for macro and filing task types, with a bootstrap interval on the difference.

Uncertainty throughout: moving-block bootstrap, block size 5 task-days, 2000 resamples, percentile intervals. Blocks rather than i.i.d. resampling because task-days are serially dependent and an ordinary bootstrap would understate uncertainty.
```

### Transformations
```
None beyond those stated. State variables are standardised before entering the H1 regression. Errors are used on their native scale.
```

### Inference criteria
```
Benjamini-Hochberg control of the false discovery rate at 0.05 across the six registered state variables for H1. Intervals are 95% block-bootstrap percentile intervals. Falsification conditions for each hypothesis are stated in §4 of the attached plan and are binding.

Additionally: on 27 Sep 2026 (end of Week 5) we fit H1 on weeks 1-5 and publish a hashed, timestamped numerical out-of-sample prediction. Weeks 6-15 are a genuine holdout. The prediction is never revised, and a miss is reported as a miss.
```

### Data exclusion
```
Fixed in advance: questions resolving fewer than 3 or more than 120 days after being asked; questions not resolving on or before 6 Dec 2026; and any question whose panel median forecast is below 0.05 or above 0.95 on the first day asked, since effectively settled questions compress error variance for reasons unrelated to the hypothesis.

Failed API calls are excluded from estimation but are counted and reported. If usable coverage falls below 80% for any model, that model is reported separately and excluded from the primary panel.
```

### Missing data
```
Handled pairwise. Tasks are never dropped listwise, because model failures (rate limits, timeouts) cluster on busy market days — exactly the high-stress conditions where H1 lives. Listwise deletion would therefore preferentially discard the observations most relevant to the hypothesis.
```

### Exploratory analyses
```
Any analysis not specified above is exploratory and will be labelled as such in the paper, reported separately from the confirmatory results, and not used to support the headline claim.
```

### Other / Notes
> **This is where the hash goes.** Substitute your real values:
```
The registered plan document is also version-controlled in public. SHA-256 of the frozen plan document (PREREGISTRATION.md) is:

HASH

The full commit history, all collection code, and the append-only daily data log are public at:

GITHUB_URL

The daily data commits provide an independent second timestamp: each forecast is committed publicly before its outcome exists.
```

---

## Step 6 — Submit (~2 min)

1. Click **Review** and read the whole thing once more. **After this, no edits.**
2. Click **Register**.
3. You'll be offered **Register now (public immediately)** or **Embargo**.
   → **Choose public immediately.** An embargoed registration is invisible to
   judges, which defeats the purpose.
4. Confirm. There is a short pending period (usually minutes, occasionally a day)
   before it goes live and gets its DOI.

---

## Step 7 — Save the URL

You'll get a permanent URL like `osf.io/ab12c` and a DOI like
`10.17605/OSF.IO/AB12C`.

Put it in all five places:
- The project README
- Your paper's methods section, first paragraph
- Your poster, bottom-right, as a QR code
- Every competition application form that has a "prior work / registration" field
- Your abstract

Then tell me the URL and I'll wire it into the README and paper scaffold.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| Can't find "New registration" | It's on the **Registrations** tab of the project, not the dashboard. Project must exist first. |
| "OSF Preregistration" template missing | Use **OSF-Standard Pre-Data Collection Registration**. Same effect. |
| Registration stuck "pending" | Normal. Usually minutes, sometimes ~24h. It will appear. |
| Realised you made a mistake after registering | You cannot edit. You can **withdraw**, which leaves a public tombstone. Better: log it in §11 of the plan as a dated deviation and explain it in the paper. Judges respect that far more than a withdrawal. |
| Hash doesn't match on `--check` | The file changed after freezing. Tell me — don't re-freeze silently, that destroys the guarantee. |
| Out of time before 24 Aug | Use **AsPredicted.org** instead: 8 questions, 10 minutes, still timestamped and public. Weaker than OSF, enormously better than nothing. You can add the full OSF registration later. |

---

## The one thing to remember

After you click Register, **do not edit `PREREGISTRATION.md` again.** Every later
change is a numbered, dated line in §11. That constraint is not bureaucracy — it
is the entire source of the document's value.


---

## Step 8 — Zenodo, in December (not now)

Once collection stops on 6 Dec and the paper is drafted, archive the outputs so
they are permanently citable. This is what Zenodo is genuinely better at.

1. Go to **zenodo.org** → log in **with GitHub** (top right).
2. **Settings → GitHub** → find your `correlated-minds` repo → flip the toggle **ON**.
   Zenodo now watches that repo for releases.
3. Back on GitHub: **Releases → Create a new release**, tag it `v1.0-data-freeze`,
   title it *Correlated Minds — data freeze*, publish.
4. Zenodo mints a DOI for that exact commit automatically, within minutes.
5. Add a second Zenodo deposit for the **paper PDF** (Upload → New upload →
   type: Publication → Preprint).
6. In the paper's metadata, put the **OSF registration URL** in the "Related
   identifiers" field as *"is supplemented by"*.

You then have three linked, permanent records — the frozen plan (OSF), the exact
data and code (Zenodo, via GitHub release), and the paper (Zenodo). Each cites
the others. That is what a complete, checkable research object looks like, and
almost nobody at a science fair has one.

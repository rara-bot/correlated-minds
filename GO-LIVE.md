# Go-Live — from "instrument built" to "collecting"

**Hard deadline: Monday 24 Aug 2026, 13:10 UTC.** That is when the first
scheduled collection run fires. Everything below has to be done before it.

**Total: about 50 minutes.** Roughly 15 of them are you reading the plan one last
time, and 25 are typing into OSF's form. The rest is running commands.

There is no rush. You have three days of slack for a 50-minute job. Do it awake.

---

## ⚠️ READ THIS FIRST — one decision has to be made before you freeze

**Google's free tier allows 20 requests per day for `gemini-3.5-flash`. The panel
asks 25 questions per day.**

Measured last night, from the quota detail in Google's own 429 response:

```
quotaId    : GenerateRequestsPerDayPerProjectPerModel-FreeTier
quotaValue : 20
model      : gemini-3.5-flash
```

25 > 20, so on a *perfect* day that model tops out at 80% coverage — exactly the
floor at which §3.3 drops a model from the primary panel. Any retry or hiccup
puts it under. The 21 Aug pilot scored it **0 of 8 usable**.

`gemini_flash_pro` is half of the Google within-family pair. Losing it takes H3
from **three** within-family pairs to **two** — and three is the entire reason
the panel went from seven models to nine (AUDIT.md finding 6). It also costs H6
its Google tier contrast.

**Two ways forward. Pick one before step 4, because step 4 freezes the roster.**

| | What to do | Cost | Consequence |
|---|---|---|---|
| **A — recommended** | Enable billing on the Google Cloud project at [console.cloud.google.com/billing](https://console.cloud.google.com/billing), then re-run steps 1–2 | **~$3** for the whole 15-week study | Roster stands exactly as registered. Nothing else changes |
| **B** | Tell me, and I swap `gemini_flash_pro` for a model that can serve 25/day | $0 | Roster changes tonight, before the freeze — not after |

**Do not freeze without resolving this.** After step 4 the roster is a §9 frozen
commitment, and a model that cannot answer 25 questions a day becomes a §11
deviation you write in November instead of a decision you make now.

Everything else below is unaffected — the other nine models verified green at
100% coverage.

---

## Where you are right now

```bash
./.venv/bin/python scripts/preflight.py
```

This is the only status report worth trusting — it reads the real state of the
repository rather than anyone's memory of it. It prints seven numbered checks and
then the exact next commands, in order. If it disagrees with anything in this
document, believe it, not this document.

Run it after every step below. It should never go backwards.

---

## Two moments you cannot undo

Everything else here is reversible. These two are not, so they get their own
warning:

| Step | Why it is permanent |
|---|---|
| **4 — Freeze** | Stamps and hashes the plan. Re-freezing would destroy the guarantee, so the script refuses. After this, changes go in §11 as dated deviations, visible forever. |
| **7 — Register** | An OSF registration cannot be edited. It can only be withdrawn, which leaves a public tombstone. |

Step 3 exists specifically so you hit those two having already read what you are
committing to.

---

## 1 — Verify the roster against live APIs · 2 min · ~$0.05

```bash
./.venv/bin/python -m neff.verify
```

One real call to each of the ten models, at `temperature=0`. **If you chose
option A above, enable billing first** — otherwise `gemini_flash_pro` will fail
here with the quota message, which is the check working, not a new problem.

**Expect:** every line `[OK  ]`, each showing the model id the provider actually
served next to the one you pinned.

**This writes `data/verification.jsonl`** — a dated receipt that every pinned id
answered a live API *before* the plan was frozen, carrying the served id for each.
That file is evidence, not bookkeeping: the study claims it can detect mid-panel
model drift, and this is where that claim starts.

- `WARN ... ID MISMATCH` → the provider served something other than what you
  pinned. Stop and tell me. Do not freeze a roster that is already drifting.
- `FAIL` on one model → a dead id or a bad key. Fixable now, not after the freeze.

---

## 2 — Collect one real pilot day · 3 min · ~$0.15

```bash
./.venv/bin/python -m neff.collect --tasks 8 --arm pilot
```

The pilot is a **separately registered arm, excluded from the primary analysis**,
which is exactly why it is allowed to run before the registration is public.

**Expect:** ~80 observations, coverage near 1.0, a few cents on the ledger.

This is the last chance to find out that a full day end-to-end does something you
did not expect, while it still costs nothing to discover.

---

## 3 — Read the plan · 10-15 min · the important one

```bash
open PREREGISTRATION.md
```

Read **§3.1** (the roster), **§4** (the hypotheses and their FALSIFIED IF
clauses), and **§7** (what would make you abandon a hypothesis).

The question to hold in your head is not "is this good" — it is:

> **If this comes out against me, am I willing to publish it?**

Every FALSIFIED IF clause is a promise you are making in public. They are the most
valuable thing in the document, and the reason it counts as a pre-registration
rather than a plan. If any of them is something you would want to soften later,
soften it **now**. After step 4 it is a numbered deviation in §11, permanently.

Also worth a look: **§10 Known limitations**. If a judge finds a limitation you
did not list, that is a bad afternoon. If it is already in §10, it is evidence you
understood your own design.

---

## 4 — Freeze and hash · 2 min · ⚠️ PERMANENT

```bash
./.venv/bin/python scripts/freeze_prereg.py --freeze
```

**Expect:**

```
FROZEN 2026-08-21 HH:MM UTC
sha256: <64 hex characters>

This hash is recorded in the document and verified against it.
```

Copy that hash. Call it **`HASH`** — you paste it into OSF in step 7.

Now confirm it, because the whole point is that a stranger can:

```bash
./.venv/bin/python scripts/freeze_prereg.py --check
```

**Expect `status : intact, matches recorded hash`.** It also prints the exact
block to paste into OSF's "Other / Notes" field.

> This step used to be broken. It printed one hash and wrote a different one into
> the document, so `--check` reported `HASH MISMATCH` on a file nobody had
> touched — and you would have published the printed hash to an immutable
> registration. Fixed and covered by 19 tests, but run `--check` anyway. It costs
> two seconds and it is the claim everything else rests on.

If `--check` ever says anything other than *intact*: **stop**, and do not
re-freeze. Tell me. Re-freezing destroys the guarantee.

---

## 5 — Push to GitHub · 5 min

The repo `github.com/rara-bot/correlated-minds` exists but is **empty** — nothing
has ever been pushed to it. The public commit history is what makes your daily
timestamps checkable by someone who does not trust you, so this matters as much
as the OSF record.

```bash
git add -A && git commit -m "Freeze pre-registration" && git push -u origin main
```

Then check on github.com that the repo is **Public** (Settings → General →
Danger Zone → Change visibility). A private repo proves nothing to a judge.

**Verify `.env` did not go with it:**

```bash
git ls-files | grep -c '^\.env$'
```

**Expect `0`.** If it ever prints `1`, stop and tell me — your API keys are
public and need rotating.

---

## 6 — OSF account, project, files · 8 min

Follow **`OSF.md` step 4**. In short: create the account (verify the email — you
cannot register anything until you do), create the project, upload
`PREREGISTRATION.md`, `VALIDITY.md` and `SETUP.md`, set the project **Public**.

---

## 7 — Create and submit the registration · 15 min · ⚠️ PERMANENT

**`OSF.md` step 5 has paste-ready text for every field.** Use it — those fields
have been checked line by line against the frozen plan, and `tests/
test_registration_text.py` fails if they ever drift apart again.

Three fields to slow down on:

- **Hypotheses** — paste §4 *verbatim*, including the FALSIFIED IF clauses. Do
  not summarise. Those clauses are the point.
- **Existing data** — select *"Registration prior to creation of data"*, and paste
  the disclosure text as written. It states plainly that the SPF human baseline
  already existed and was already analysed, and that it changed the design. That
  honesty is worth more than the field it sits in.
- **Other / Notes** — paste `HASH` from step 4 and the GitHub URL from step 5.

Then: **Register → Register now (public immediately)**. Not embargoed — an
embargoed registration is invisible to judges, which defeats the purpose.

Pending for a few minutes is normal. Occasionally ~24h.

---

## 8 — Unlock collection · 2 min

Collection is blocked in code until the registration is on record. Record it:

```bash
echo 'https://osf.io/XXXXX' > .osf_url
git add .osf_url && git commit -m "Record OSF registration" && git push
```

**The commit is not optional.** The scheduled job runs from a fresh checkout, so a
`.osf_url` that exists only on your laptop fails every single collection day with
a message about a missing registration that is, locally, plainly present. The
workflow now checks this as its first step and names the fix, but it is easier to
just commit it.

---

## 9 — Turn on the automation · 5 min

On GitHub, **Settings → Secrets and variables → Actions → New repository
secret**, add all four exactly:

```
ANTHROPIC_API_KEY
OPENAI_API_KEY
GOOGLE_API_KEY
OPENROUTER_API_KEY
```

Then **Settings → Actions → General → Workflow permissions → Read and write
permissions**. Without this the daily job cannot commit data, and a day that
cannot be committed is a day that cannot be proven.

---

## 10 — Rehearse the daily run · 3 min

**Actions** tab → *daily-collection* → **Run workflow** → tick `dry_run` → Run.

**Expect green.** A dry run prices the day and writes nothing — not to the
ledger, not to the task registry — so this rehearsal cannot put anything into the
public record ahead of your registration.

Watch that the step **"Confirm the pre-registration is visible to CI"** passes. If
it fails, step 8's commit did not land.

---

## 11 — Final check

```bash
./.venv/bin/python scripts/preflight.py
```

**Expect seven `[done]` and `Ready. Collection can start.`**

That is it. It runs itself at 13:10 UTC every day until **6 December**, committing
each day's forecasts to a public history before their outcomes exist.

---

## What to watch after go-live

| When | What | Why |
|---|---|---|
| 24 Aug, ~13:30 UTC | First real run is green | A silent failure on day one costs the whole first week before anyone notices |
| Weekly | `data/ledger.jsonl` total | Projected $47 against a $100 arm cap. The cap is a hard stop, not a warning |
| Weekly | Every model's coverage | Below 80% for any model and it leaves the primary panel (§3.3) |
| **27 Sep** | Week-5 interim read | Fit H1 on weeks 1-5, publish a hashed out-of-sample prediction. Never revised, and a miss is reported as a miss |
| **6 Dec** | Data freeze | Calendar-based, never data-dependent. Then Zenodo — `OSF.md` step 8 |

---

## If something goes wrong

| Symptom | Cause and fix |
|---|---|
| `HASH MISMATCH` from `--check` | The document changed after freezing. **Do not re-freeze.** Log it in §11 as a dated deviation and tell me |
| `REFUSING TO COLLECT` | `.osf_url` missing, uncommitted, or holding a placeholder rather than a URL |
| `No OSF registration URL visible to CI` | Step 8's commit did not land. Commit `.osf_url`, or set an `OSF_URL` repository variable |
| `ladder_distance missing` | Blocking on purpose: a registered H1 variable, recorded at ask time, that cannot be backfilled. Tell me rather than working around it |
| `BudgetExceeded` | Working as designed. Check `data/ledger.jsonl` before raising anything |
| One model at 0 coverage | Wrong id or bad key. `neff.verify` and send me the output |
| Workflow cannot push | Workflow permissions are not set to read/write |
| `FREE-TIER DAILY QUOTA: 20 requests/day` | The decision at the top of this document. Enable billing, or tell me to swap the model |
| Out of time before 24 Aug | `AsPredicted.org` — 8 questions, 10 minutes, still timestamped and public. Weaker than OSF, enormously better than nothing. Add the full OSF registration afterwards |

---

## The one thing to remember

After step 7, **do not edit `PREREGISTRATION.md` again.** Every later change is a
numbered, dated line in §11.

That constraint is not bureaucracy. It is the entire source of the document's
value, and the only reason anyone should believe the plan came before the data.

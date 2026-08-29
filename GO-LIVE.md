# Go-Live — from "instrument built" to "collecting"

**Hard deadline: Monday 29 Aug 2026, 13:10 UTC.** That is when the first
scheduled collection run fires. Everything below has to be done before it.

**Total: about 50 minutes.** Roughly 15 of them are you reading the plan one last
time, and 25 are typing into OSF's form. The rest is running commands.

As of 23 Aug 02:00 UTC there are about **35 hours** left, and an OSF registration
can sit pending for up to ~24 of them. The typing is still only ~30 minutes, but
the slack is spent — start the OSF steps today, not tomorrow morning.

---

## ✅ RESOLVED — the Google blocker is closed

`gemini-3.5-flash` was capped at 20 requests/day on the free tier against a panel
that asks 25, and scored **0/8** in the 21 Aug pilot.

Root cause was never the model. The API key sat in an **unbilled project**. Gemini
bills through **AI Studio prepay**, not Google Cloud pay-as-you-go, and the Cloud
trial's $300 does not apply to it. A key created in a billed project fixed it:

| | 21 Aug | 22 Aug |
|---|---|---|
| `gemini_flash_pro` coverage | 0/8 | **8/8** |
| rapid-call test (free tier caps at 5/min) | fails at #6 | **8/8 pass** |
| whole-panel pilot | 71/80 usable | **79/80 usable** |

**The roster is unchanged** — no model swap, H6 keeps its same-generation Google
tier contrast, M = 9 stands. `.env` and the `GOOGLE_API_KEY` GitHub secret both
carry the billed key.

**Steps 1, 2, 3, 5 and the GitHub setup are all done** — roster verified against
live APIs, pilot collected, plan read, repo public and current. What remains is
**step 4 (freeze)** and **steps 6-8 (OSF)**.

> **Do not re-run steps 1 or 2.** §3.5 of the plan records the pilot's exact
> size — 16 tasks, 180 observations, 208 billed calls, $0.1224 — as at the
> freeze, and the ledger is stated to reconcile against it. Another pilot
> day would add rows the frozen document does not account for, and a reviewer
> comparing the public log against the registration would find the discrepancy
> before you did.

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

One real call to each of the ten models, at `temperature=0`. Billing is already
enabled on the Google key (see the resolved section above); if it ever lapses,
`gemini_flash_pro` fails here with the quota message, which is the check working
rather than a new problem.

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
open -e PREREGISTRATION.md
```

(`open` without `-e` fails on this machine — no application claims `.md`.)

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
FROZEN 2026-08-23 HH:MM UTC
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
> registration. Fixed and covered by 29 tests, but run `--check` anyway. It costs
> two seconds and it is the claim everything else rests on.
>
> You can also run `--check` **before** freezing: it now prints the exact hash the
> freeze will publish, so the one irreversible step in this document has a
> rehearsal. That equality is itself tested.

If `--check` ever says anything other than *intact*: **stop**, and do not
re-freeze. Tell me. Re-freezing destroys the guarantee.

---

## 5 — Push to GitHub · 5 min

`origin` is already configured and `github.com/rara-bot/correlated-minds` is
current — the push itself is done. What this step is now for is committing the
freeze, and confirming the repo is public. The public commit history is what
makes your daily timestamps checkable by someone who does not trust you, so it
matters as much as the OSF record.

```bash
git add -A && git commit -m "Freeze pre-registration" && git push
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

That is it. It runs itself at 13:10 UTC every day until **11 December**, committing
each day's forecasts to a public history before their outcomes exist.

---

## What to watch after go-live

| When | What | Why |
|---|---|---|
| 29 Aug, ~13:30 UTC | First real run is green | A silent failure on day one costs the whole first week before anyone notices |
| Weekly | `data/ledger.jsonl` total | Projected **$50** against a **$110** arm cap — the projection includes the §5.4(d) replicates, because they are real calls on the same arm and excluding them is how the old $25 figure went stale. The cap is a hard stop, not a warning |
| Weekly | Every model's coverage | Below 80% for any model and it leaves the primary panel (§3.3) |
| **2 Oct** | Week-5 interim read | Fit H1 on weeks 1-5, publish a hashed out-of-sample prediction. Never revised, and a miss is reported as a miss |
| **11 Dec** | Data freeze | Calendar-based, never data-dependent. Then Zenodo — `OSF.md` step 8 |

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
| `FREE-TIER DAILY QUOTA: 20 requests/day` | Google billing has lapsed on the key. Gemini bills through **AI Studio prepay**, not Cloud pay-as-you-go — re-enable it there, and do not swap the model without telling me: the roster is registered |
| `load_panel: no rows admitted` | Working as designed. Rows must carry `arm="ws1_prospective"`; the pre-registration pilot carries none and is excluded (§3.5). Analyse it with `load_panel(arm="pilot")` |
| Out of time before 29 Aug | `AsPredicted.org` — 8 questions, 10 minutes, still timestamped and public. Weaker than OSF, enormously better than nothing. Add the full OSF registration afterwards |

---

## The one thing to remember

After step 7, **do not edit `PREREGISTRATION.md` again.** Every later change is a
numbered, dated line in §11.

That constraint is not bureaucracy. It is the entire source of the document's
value, and the only reason anyone should believe the plan came before the data.

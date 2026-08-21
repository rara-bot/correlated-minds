# Setup — exactly what to do, in order

**Total time: about 45 minutes.** Most of it is waiting for signup emails.

Split up front, so there is no ambiguity:

| | Who |
|---|---|
| All code, tests, data pipeline, automation, docs | ✅ **Done** |
| Creating accounts | **You** — I can't create accounts |
| Paying for API credits | **You** — I can't enter payment details |
| Entering API keys | **You** — keys are secrets; I shouldn't handle them |
| Publishing the OSF registration | **You** — it's your name on the science |

Everything else is finished and committed.

---

## What OSF is

**OSF = the Open Science Framework** (osf.io), a free service run by the
non-profit Center for Open Science.

It does one thing that matters here: **it lets you publicly timestamp your
research plan before you collect any data, in a way that cannot be edited
afterwards.** You upload your plan, OSF freezes it, and gives you a permanent
public URL with a date stamp. Not even you can change it after that.

**Why this matters more than anything else in your project:**

Your central claim is going to be *"I predicted this before it happened."* Anyone
can say that. A skeptical judge's first thought is: *how do I know you didn't
write the prediction after seeing the result?*

An OSF registration answers that in one line. It is the difference between a
claim and evidence, and it costs nothing.

It also protects you from yourself. Once the hypotheses are frozen, you can't
unconsciously drift them toward whatever the data happens to show — which is the
single most common way honest people produce wrong results.

We're doing it twice over: OSF **and** a hash of the document committed to git,
so the record is independently checkable two ways.

> Simpler alternative if OSF feels heavy: **AsPredicted.org** — 8 short questions,
> takes 10 minutes. Less standard, but far better than nothing. OSF is what
> reviewers expect.

---

## Step 1 — Get API keys (~20 min)

You need four accounts. **Put in $10 each; you do not need $200.**
Measured cost of the full 15-week study is **~$47** (ten models collected, re-priced 21 Aug 2026; see BUDGET.md).

| Provider | URL | Add |
|---|---|---|
| Anthropic | console.anthropic.com | $10 |
| OpenAI | platform.openai.com | $10 |
| Google AI Studio | aistudio.google.com/apikey | $0 — free tier likely covers it |
| OpenRouter | openrouter.ai/keys | $10 |

OpenRouter is one key covering Llama, Qwen and DeepSeek — three of our nine
models — so it's the best value of the four.

Then, in the project folder:

```bash
cp .env.example .env
```

Open `.env` in any text editor and paste each key after the `=`. No quotes, no
spaces. **Never commit this file** — `.gitignore` already blocks it.

---

## Step 2 — Verify before spending (~2 min)

```bash
./.venv/bin/python -m neff.verify
```

This makes **one real call per model** — a few cents total. It confirms every
pinned model ID actually resolves, and reports what the API really served.

This step exists because a wrong model ID fails loudly on day one, but a **wrong
price fails silently** and quietly drains the budget while every log looks fine.

If any row says `ID MISMATCH`, tell me the ID it reports and I'll update
`config.py`.

---

## Step 3 — One real pilot day (~5 min)

```bash
./.venv/bin/python -m neff.collect --tasks 8 --arm pilot
```

Expect ~72 observations for about 9 cents. Then check the panel is healthy:

```bash
./.venv/bin/python -c "
from neff.panel import load_panel, describe
import json; print(json.dumps(describe(load_panel(require_resolved=False)), indent=2))"
```

You want `coverage` near 1.0. If one model is missing lots of rows, its key or
ID is wrong.

---

## Step 4 — Freeze the pre-registration (~10 min)

**Do this before collection starts on 24 Aug. It cannot be undone.**

```bash
./.venv/bin/python scripts/freeze_prereg.py --freeze
```

This stamps `PREREGISTRATION.md` with a UTC timestamp and a SHA-256 hash, then
prints the hash. Commit it:

```bash
git add -A && git commit -m "Freeze pre-registration"
```

Then on OSF. **The full click-by-click walkthrough, with paste-ready text for
every field in the OSF form, is in [`OSF.md`](OSF.md) — follow that, not the
summary below.** In outline:

1. Create a free account at **osf.io**
2. **Create a Project** — name it *Correlated Minds*
3. Upload `PREREGISTRATION.md`
4. Left sidebar → **Registrations** → **New Registration**
5. Choose the **OSF Preregistration** template
6. Fill it in from PREREGISTRATION.md — the sections map directly:
   - *Hypotheses* → §4
   - *Design plan* → §3
   - *Analysis plan* → §5
   - *Sampling plan* → §6
7. **Paste the SHA-256 hash into the "Other" / notes field**, with the sentence:
   *"SHA-256 of the frozen plan document; the full version-controlled history is public at <your GitHub URL>."*
8. Submit. Choose **immediate** public registration, not embargoed.

Save the OSF URL — it goes on your poster, in your paper, and in every
competition application.

Anyone can then check the hash themselves:
```bash
./.venv/bin/python scripts/freeze_prereg.py --check
```

---

> **Order note:** do Step 5's GitHub push *before* the OSF registration — the
> registration asks for your public repo URL. `OSF.md` sequences this correctly.

---

## Step 5 — Turn on the automation (~10 min)

1. Create a **new GitHub repository**. Public is better — the public commit
   history is what makes your timestamps verifiable.
2. Push:

```bash
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git branch -M main
git push -u origin main
```

3. On GitHub: **Settings → Secrets and variables → Actions → New repository
   secret.** Add all four, named exactly:

```
ANTHROPIC_API_KEY
OPENAI_API_KEY
GOOGLE_API_KEY
OPENROUTER_API_KEY
```

4. **Settings → Actions → General → Workflow permissions** → select
   **Read and write permissions**. Without this the daily job can't commit data.
5. **Actions** tab → *daily-collection* → **Run workflow**, tick `dry_run`, and
   confirm it goes green. A dry run prices the day and writes nothing — not to
   the ledger and not to the task registry — so this rehearsal cannot put
   anything into the public record ahead of the registration.
6. Once the OSF registration is live, **commit `.osf_url`** (see `OSF.md` step 7).
   The daily job reads it from a fresh checkout, so a file that exists only on
   your laptop fails every scheduled run. The workflow's first step checks this
   explicitly and names the fix rather than failing deep inside collection.

From then on it runs itself at 13:10 UTC (9:10am ET) every day and commits the
data. Each commit is a timestamped proof that the forecast existed before the
outcome did.

---

## Checklist

- [ ] Four API keys, $50 of credit, in `.env`
- [ ] `neff.verify` all green (leaves receipts in `data/verification.jsonl`)
- [ ] Pilot day collected, coverage ~1.0
- [ ] Pre-registration frozen, hashed, committed — `freeze_prereg.py --check` says *intact*
- [ ] OSF registration public, URL saved **and committed** to `.osf_url`
- [ ] Repo pushed, four secrets set, write permissions on
- [ ] Dry-run workflow green
- [ ] `scripts/preflight.py` shows seven `[done]`

`scripts/preflight.py` is the single source of truth for this list — it reads the
real state rather than your memory of it.

Then it runs on its own until **6 December**.

---

## If something breaks

| Symptom | Cause |
|---|---|
| `ANTHROPIC_API_KEY not set` | `.env` not filled, or you're in the wrong folder |
| One model at 0 coverage | Wrong model ID — run `neff.verify` and send me the output |
| `BudgetExceeded` | Working as designed. Check `data/ledger.jsonl` |
| Workflow can't push | Workflow permissions not set to read/write |
| `No OSF registration URL visible to CI` | `.osf_url` written locally but never committed. Commit it, or set an `OSF_URL` repository variable |
| `REFUSING TO COLLECT` locally | Same cause, or `.osf_url` holds a placeholder rather than a URL |
| `ladder_distance missing` | A task source returned markets without a strike ladder position. This is deliberate and blocking: it is a registered H1 variable that cannot be backfilled |
| `no tasks available today` | Kalshi has nothing resolving before the freeze — tell me |

Send me any error and I'll fix it. Don't work around it — a workaround now
becomes a hole in the panel later.

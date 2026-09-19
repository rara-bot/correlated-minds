# AI use in this project — the record the ISEF rules ask for

Society for Science's guidance *Use of generative AI to support a research project*
(October 2025, published with the Regeneron ISEF rules) says, among other things:

- AI may write **initial code** only **with explicit citation stating which portions
  were AI-generated and a log of the prompts**.
- AI may help **identify statistical tests or software tools**, with a log of the
  prompts; **interpretation of the data must be done by the student**.
- AI may **never** initially write the **research plan, abstract, paper or poster**,
  produce **conclusions**, or supply **citations** or a starter bibliography.
- Affiliated fairs (for this project, NCSEF Region 6) may adopt stricter rules.

**For 2026-27 this is in the International Rules themselves**, not only in the
guidance (All Projects, Eligibility/Limitations #8, in Society for Science's list of
rule changes for 2026-27): AI may be used as a resource if it is cited and
acknowledged; everything you present must be in your own words; and generative AI
may not write the research plan, abstract or poster, or create citations. The same
year adds **Form 2A, the Student Support Disclosure Form, required for every
project** (it may be completed before or after experimentation), and requires the
Research Plan to have seven parts: rationale; research question or hypotheses and
expected outcomes; list of materials; procedures; risk and safety; data analysis;
bibliography.

This file is the factual half of that record. It was generated on 2026-09-13 from
this repository's git history by Claude (Anthropic's Claude Code), the assistant
used throughout the project. It is **not** a disclosure statement written for you:
read it, correct anything you know to be wrong, and write your own disclosure in
your own words.

---

## What the assistant was used for

| Area | What happened | What the rules require |
|---|---|---|
| Code: `neff/`, `scripts/`, `tests/`, `.github/workflows/` | Written by Claude Code at the student's direction; most commits carry a `Co-Authored-By: Claude` trailer | Allowed **with citation of which code is AI-generated, and the prompt log** |
| Statistical methods: N_eff, block and cluster bootstrap, Benjamini-Hochberg, cluster-robust regression | Proposed, simulated and implemented by the assistant | Allowed **with the prompt log**; **the interpretation must be yours** |
| Planning documents: PREREGISTRATION.md, VALIDITY.md, OSF text, AUDIT.md, README.md and the rest | Drafted largely by the assistant | These are **not** your ISEF Research Plan, abstract, paper or poster. **Those must be written by you, from scratch** |
| Literature: PRIOR-ART.md | Search results gathered by the assistant. Five arXiv papers the plan relies on were re-checked on arXiv on 2026-09-13 (PRIOR-ART.md §E) | **You must read every source you cite and check each citation yourself** |

---

## Evidence in the repository

Up to the daily data commit of 2026-09-13 (`21ceb22`) the repository has 62
commits. 40 carry `Co-Authored-By: Claude`, 14 are the automated daily data
commits (`neff-collector`), and 8 carry no AI trailer. A missing trailer does not
prove a commit had no AI assistance. The counts below are for those 62.

Commits touching each file, and how many of those carry the Claude trailer
(automated data commits excluded):

| File or folder | Commits | Claude co-authored |
|---|---|---|
| `PREREGISTRATION.md` | 20 | 17 |
| `README.md` | 20 | 18 |
| `neff/collect.py` | 12 | 9 |
| `neff/config.py` | 11 | 9 |
| `neff/providers.py` | 10 | 8 |
| `AUDIT.md` | 9 | 7 |
| `neff/panel.py` | 8 | 6 |
| `OSF.md` | 7 | 6 |
| `VALIDITY.md` | 6 | 5 |
| `.github/workflows/daily.yml` | 5 | 4 |
| `GO-LIVE.md`, `SETUP.md` | 5 each | 5 and 4 |
| `neff/analysis.py`, `neff/sources/kalshi.py`, `neff/stats.py`, `neff/store.py`, `neff/verify.py`, `neff/tasks.py` | 4 each | 4, 3, 2, 3, 3, 1 |
| `scripts/check_days.py`, `scripts/freeze_prereg.py` | 4 each | 4 and 3 |
| Every file under `tests/` | 1-4 each | nearly all |

Everything added on 2026-09-13 -- `neff/h1.py`, `neff/report.py`, `neff/surprise.py`,
`neff/prediction.py`, `scripts/analyze.py`, `scripts/release_surprise.py`,
`scripts/week5_prediction.py`, `scripts/snapshot_kalshi_ladders.py`, their tests,
§11 deviations 13-18, and this file -- was written by Claude Code in one session
and committed that evening as `eff412d`. A second session that evening added
`40270a5`, which holds the H3 variant arm to its registered start date. Both
carry the Claude trailer. A third session that night wrote §11 deviation 19:
`neff/logprobs.py`, `scripts/pin_spf_inputs.py`, the pinned inputs in `data/spf/`,
their tests, and changes to `neff/sources/spf.py` and `neff/sources/fred.py`. It
carries the trailer too. A fourth session, on 2026-09-14, wrote §11 deviation 20:
`neff/h2.py` to `neff/h6.py`, `scripts/category_base_rates.py` and the base rates it
pinned in `data/category_base_rates.jsonl`, the logprob re-estimate in
`neff/report.py` and `neff/logprobs.py`, a workflow step, and their tests.

A fifth session, on 2026-09-16 UTC, merged deviation 20 to `main` after re-running the
suite on CI's Python in a fresh clone, and added operational scaffolding only:
`.github/workflows/tests.yml` (the suite now runs on every push, not just inside
the daily job, so a regression cannot cost a collection day), `scripts/milestones.py`
and `tests/test_milestones.py` (a reminder for the two dated commitments a person
has to keep -- the Week-5 prediction and the freeze), and a step in `daily.yml` that
surfaces them. **No deviation number was taken.** Nothing there reaches a model,
enters the stored record, or moves a registered quantity; it is the same class of
change as the stress-day notice and the durable alarm, neither of which is in §11.

That session then ran the analysis **unblinded** on the real data to check the
December final look works -- outside the two looks the plan allows, by faking the
clock to get past the date gate. It is logged as §11 deviation 21 and summarised
in the addendum. Nobody asked for it; the assistant did it on its own initiative,
and the disclosure is the assistant's too. It displayed no number, the file it
wrote was deleted unopened, and every analysis choice was already fixed and public
before it ran. The remedy, `tests/test_unblinded_path.py`, checks the December path
against outcomes made up inside the test, so the real record is never opened early
again. **If a judge asks whether anyone looked at the results before December, the
honest answer is this deviation, and it is in the public log.**

A sixth session, on 2026-09-19, wrote §11 deviation 22. `scripts/week5_prediction.py`
now refuses to publish the 2 October prediction from a copy of the record that is
not current -- behind GitHub, missing that day's questions, or missing a settlement
Kalshi has already published -- and has a read-only `--check` that says READY or
what to wait for. `neff/sources/kalshi.py` and `scripts/release_surprise.py` now
expose the settlement rules they already applied, so the check uses the same ones.
`tests/test_week5_publish.py` runs the registered 2 October look end to end,
unblinded, on a record fabricated inside the test, and fails if anything opens the
real one. The same session changed the collection job's environment **without a
deviation number**, because nothing there reaches a model, enters the record or
moves a registered quantity: `requirements.txt` caps every dependency below its
next major version (httpx 1.0, then in pre-release, removes every function the
study uses to call a model or a data source); both workflows run on a named Ubuntu
24.04 image and on action versions that run on Node 24 (GitHub removes Node 20 on
2026-09-23, and moves `ubuntu-latest` to Ubuntu 26.04 from 2026-10-19); the daily
job's commit step now fails, and its alarm now fires, when a day's data cannot be
pushed, where before a failed push finished green; and `scripts/milestones.py` lists
`git pull` and `--check` before `--publish`. `tests/test_requirements_bounded.py`
and `tests/test_workflow_commit.py` pin those.

The same session wrote §11 deviation 23. Checking every vendor's retirement
schedule, it found that OpenAI shuts down `gpt-4.1-nano-2025-04-14` (`gpt_small`)
on 2026-10-23, an announcement from April that nobody had checked. **You chose**
between keeping the model through Azure and letting it drop out, and chose Azure.
The code (`neff/config.py` `SERVING_ROUTES`, `neff/providers.py`
`OpenRouterAzureProvider`) moves the model to OpenRouter's Azure host on that day,
asks every question on that route beforehand as well (the "bridge", stored at
prompt variant 98 and read only by `panel.bridge_report`), alarms if the route
fails, and adds a sensitivity without the post-switch answers
(`report.without_route`). `tests/test_serving_route.py` pins it. The route was
probed live with a synthetic question, outside the study record.

The 8 commits without a trailer, for you to check against your own memory:

| Commit | Date | Message |
|---|---|---|
| `6c20c93` | 2026-08-20 | Verify the full roster against live APIs; fix five pre-collection defects |
| `997829d` | 2026-08-18 | Record the OSF-vs-Zenodo decision and add the December Zenodo step |
| `c09460b` | 2026-08-17 | Record findings 9 and 10 in the audit |
| `0597b03` | 2026-08-17 | Correct the primary outcome metric before freezing |
| `63fb92a` | 2026-08-17 | Add document-grounded filing tasks for ecological validity |
| `3787e32` | 2026-08-17 | Add SETUP.md and pre-registration freeze tool |
| `620a996` | 2026-08-17 | Add pre-flight verification (neff.verify) |
| `ba5d205` | 2026-08-17 | Week 0: measurement instrument |

---

## The prompt log

Claude Code keeps a transcript of every session. On this Mac there are 29 of them
in `~/.claude/projects/-Users-rajankhiani-r1/`, from 19 Aug to 19 Sep 2026. **They
are not in this repository.** Copy that folder somewhere safe now, and again after
each working session, and keep it with your research notebook: it is the prompt
log the rules require. Sessions before 19 Aug, if any, are not on this machine.

---

## What only you can do

1. Write the ISEF Research Plan, abstract, paper, poster, quad chart and
   conclusions yourself, in your own words. You may ask an AI to fix grammar in
   something you wrote; you may not ask it to add, change or write content.
2. Read every paper you cite, and check every citation yourself.
3. Interpret the results yourself, and be ready to explain every method and every
   deviation in a judging interview.
4. **Keep the fair's answer on AI use in writing.** On 2026-09-13 you told Claude
   that you had already asked the fair about this use of AI and that they said it
   is fine. If the answer came by email, save it with your research notebook. If
   it was given in person or on a call, email them to confirm it, describing the
   use plainly: AI-written code and analysis, an AI-drafted pre-registration, and
   AI models as the object of study. Keep their reply.
5. **Fill in Form 2A**, the Student Support Disclosure Form, new for 2026-27 and
   required for every project. It is where the help you had is declared; name the
   AI assistant there, in your own words, and keep this file as the evidence.

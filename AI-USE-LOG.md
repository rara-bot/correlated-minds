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

Up to 2026-09-13 the repository has 62 commits. 40 carry `Co-Authored-By: Claude`,
14 are the automated daily data commits (`neff-collector`), and 8 carry no AI
trailer. A missing trailer does not prove a commit had no AI assistance.

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
§11 deviations 13-18, and this file -- was written by Claude Code in one session.

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

Claude Code keeps a transcript of every session. On this Mac there are 22 of them
in `~/.claude/projects/-Users-rajankhiani-r1/`, from 19 Aug to 13 Sep 2026. **They
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
4. **Before you register, ask the Region 6 fair's Scientific Review Committee in
   writing** whether this use of AI is acceptable under their rules, describing
   it plainly: AI-written code and analysis, an AI-drafted pre-registration, and
   AI models as the object of study. Keep their answer.

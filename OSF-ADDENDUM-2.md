# OSF addendum 2 — draft, not yet posted

**Same three steps as Addendum 1, about 15 minutes.** Post it before the data freeze
(11 Dec); sooner is better, since its value is being public while the outcomes it
could affect are unknown. Fold in any later deviation first.

| Step | Where | What |
|---|---|---|
| 1 | **Zenodo** — open DOI `10.5281/zenodo.22220263` → **New version** | Upload `PREREGISTRATION.md` (the current one, with §11) and `OSF-ADDENDUM-2.md` (this file). Set version to `1.3-addendum-2`. Publish |
| 2 | **Your OSF project** (osf.io/965dz — the project, *not* the frozen registration) | Upload the same two files (replace `PREREGISTRATION.md`). Then **Wiki** → new page titled `Addendum 2 — <the day you post>` → paste the wiki entry at the end of this file |
| 3 | **osf.io/x6kqg** (the registration) | Skip, as for Addendum 1. **Do not withdraw or edit the registration.** |

| | |
|---|---|
| Registration | osf.io/x6kqg, registered 2026-08-29 14:44 UTC |
| Registered SHA-256 | `90a7e7de5980a80bef786e87b938495d7a08e10234032a11c5d67e8ce1c70009` |
| Addendum 1 | posted 2026-10-03 (Zenodo 10.5281/zenodo.23113579), deviations 1-24 |
| Recorded at | PREREGISTRATION.md §11, deviations 25-25 |

---

## Step 2 — paste this as the OSF project wiki entry

```
ADDENDUM 2

One new dated deviation, logged in PREREGISTRATION.md section 11 before the
registered final look (after 11 Dec), and one note on deviation 24. No
hypothesis, falsification clause, temperature, task mix, primary outcome or
multiple-testing correction has changed.

DEVIATION 25 (11 Oct): gemini-3.5-flash is retired from 10 Oct
- Google deprecated gemini-3.5-flash on 8 Oct and now answers every request for
  it with gemini-3.6-flash. On 10 Oct all 27 calls returned the served id
  gemini-3.6-flash; every earlier call returned gemini-3.5-flash. The served-id
  check registered in section 10 found it on 11 Oct.
- The model was pinned to the same generation as its pair partner
  (gemini-3.5-flash-lite) so the pair varies tier with generation held fixed;
  the newer model would confound the two. No other host serves it with thinking
  off, as registered.
- It is not asked from 11 Oct. The 27 answers of 10 Oct stay in the append-only
  record and enter no estimate. Section 5.6 applies unchanged; deviation 24's
  sensitivity (primary estimate, H3 and H6 on the questions asked before the
  retirement, all nine models) is also reported for this retirement.
- Chosen by the student from vendor documentation alone; no outcome was read.

A NOTE ON DEVIATION 24
- After deviation 24 was written, Microsoft's schedule moved Azure's retirement of
  gpt-4.1-nano back to 2027-04-14 (seen 9 Oct). Deviation 24 is kept as written:
  gpt-4.1-nano is asked through OpenAI, as registered, to 22 Oct, and not at all
  from 23 Oct, when OpenAI shuts it down; no model changes host.

VERIFICATION
  Repository:  https://github.com/rara-bot/correlated-minds
  Zenodo:      10.5281/zenodo.22220263 (latest version)
  ./.venv/bin/python scripts/freeze_prereg.py --check  ->  "intact outside section 11"
```

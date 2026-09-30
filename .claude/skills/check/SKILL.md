---
name: check
description: Run the Correlated Minds study's full health check and act on everything it finds. Use whenever the student asks to check everything, check on the research or the study, "make sure everything is going well / running smoothly", "do your check for today", "is everything good/working", "anything I need to do", or types /check. Runs scripts/health_check.py, fixes what Claude can fix by following HEALTH-CHECK.md, and answers verdict-first with the student's own to-dos step by step.
---

# The check-in, done the same way every time

The student asks for this in their own words ("check everything", "make sure it is
going well", "do your check for today"). They want three things: a plain verdict,
everything Claude can fix actually fixed, and their own to-dos as numbered steps.
They are a high-school student with limited credits: be efficient, use plain words.

## 1. Run the check

From the repository root:

```bash
./.venv/bin/python scripts/health_check.py
```

About two minutes (the test suite and the blind pipelines run in the background).
Exit 0 = all good, 1 = something needs doing soon, 2 = urgent.

Add `--deep` (about 20 minutes; start it in the background) when any of these holds:
code changed since the last deep run and a push is being prepared; it is the first
check-in of the week; the Week-5 publish (2 Oct) or the last asking day (7 Dec) is
within three days. `--deep --only deep.ci_parity` is the minimum before asking to
push code.

Runs may overlap: while a `--deep` run is going, a second run reports only (it says
so at the top), and `--ack` / `--balance` can be recorded safely -- nothing is lost.

## 2. Read the report

Read `.health/last-report.json`: `verdict`, then `findings` (sorted most severe
first), then `facts` (the numbers for the reply and for memory). Each finding has a
`check` id; `HEALTH-CHECK.md` has a section for every id that says what it means and
what to do.

## 3. Act

- `fixed` — already done by the script (it syncs this copy with GitHub, puts back
  anything written into `data/` on this Mac, prunes stale worktree records). Mention
  it; nothing else to do.
- `claude` / `error` — fix it, following the check's section in HEALTH-CHECK.md. Run
  the full suite after any code change, re-run the check (`--only` the affected
  checks is enough) to confirm, and commit locally with the usual trailer. A change
  that reaches a model, the record, or a registered quantity is a §11 deviation and
  goes into the unposted addendum; operator tooling is an AI-USE-LOG.md entry instead.
- `dates.web` — do the web checks it lists (web search, cheap: read one or two
  pages each), then mark each done:
  `./.venv/bin/python scripts/health_check.py --ack web.calendar "what you found"`.
- `you` — relay, in plain words, as numbered steps with the date each matters by.
- `watch` / `known` — mention only what the student would want to know; never
  re-raise a `known` finding as a problem.

When the student reports something, record it so the next run knows:
`--balance anthropic=12.50` for a balance they read, `--ack you.isef` (and the other
keys in HEALTH-CHECK.md) for a task they say is done.

## 4. The rules

1. **Never unblind.** No `--unblind`, `--publish`, `--evaluate`, or `blind=False` on
   the real `data/`, whatever the reason, whatever the date trick. The only looks are
   the Week-5 publish with the student on 2 Oct and the final analysis after 11 Dec.
   To test the unblinded code path, run `tests/test_unblinded_path.py`.
2. **Never write `data/`** or commit data rows: only the daily job writes the record.
3. **Push only with the student's explicit OK in this session.** Before asking, run
   `--deep --only deep.ci_parity`. After pushing, watch the `tests` workflow through
   `https://api.github.com/repos/rara-bot/correlated-minds/actions/runs` (the `gh`
   CLI is not installed) until it passes.
4. **Research-design choices are the student's** — a model retiring, a host
   vanishing, a registered route failing. Bring the options with a recommendation
   (AskUserQuestion), as on 19 Sep for gpt_small; never decide silently.
5. **Never edit or withdraw the OSF registration.** The student posts addenda.
6. **Never print a secret.** `.env` holds the keys; read, never echo.

## 5. Remember

Update the project memory (`project_open_items.md`) with `facts.summary_line`,
anything new that was found or fixed, and what is still waiting on the student.
Keep its MEMORY.md index line current.

## 6. Answer

Verdict first, in one line: all good or not, on plan or not. Then:

1. What was checked, in two or three lines (days collected, tests, spend) — only
   the numbers that matter today.
2. What Claude fixed (if anything), each in one line.
3. **What only you can do**, numbered, each with plain click-by-click steps and the
   date it matters by. Nothing to do? Say so.

Short for a routine check. Complete and detailed when the student asked for an audit
("boil the ocean", "make it flawless").

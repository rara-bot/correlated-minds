# Health check — the playbook

One command runs every check the check-ins of September ran by hand, fixes what
is safe to fix, and says exactly what is left and who does it:

```bash
./.venv/bin/python scripts/health_check.py
```

About two minutes. `scripts/health_check.py` is the check; this file is what each
finding means and what to do about it. In Claude Code, just say "check
everything" (or type `/check`): the project skill in `.claude/skills/check/` runs
the script, fixes what Claude can fix, and answers in the usual form — verdict
first, then your to-dos, step by step.

| Command | What it does | Time |
|---|---|---|
| `scripts/health_check.py` | The daily check: this copy, GitHub Actions, the record, coverage, settlements, the plan and its public copies, tests, the blind pipelines, money, vendors, dates, your to-dos | ~2 min |
| `--deep` | Also: the suite on CI's Python 3.11 with the pinned packages in a fresh copy; the suite at every date that matters from here to 2027; actionlint; the pinned set against GitHub's Linux | ~20 min |
| `--no-fix` | Report only. Changes nothing (it still fetches from GitHub) | |
| `--offline` | Skip everything that needs the network | |
| `--quick` | Skip the test suite and the blind pipeline runs | ~30 s |
| `--only record,ci.runs` | Only these checks (ids or whole groups) | |
| `--list` | Every check, and the check-in or incident it came from | |
| `-v` | Print every check, not only what needs doing | |
| `--ack KEY "note"` | Record that a person-only item is done (keys below) | |
| `--balance anthropic=17.37 openai=8.83` | Record balances you read in your accounts (`--as-of` for when) | |

Exit status: **0** all good, **1** something needs doing soon, **2** something is
urgent. The full report is in `.health/last-report.md` (and `.json`); a run with
`--only` writes `.health/last-partial.*` instead, so the last full report stays; a
one-line history of every run is in `.health/history.jsonl`. Everything in `.health/`
stays on this Mac: the folder ignores itself, so no `git add` can publish it.

---

## Reading a report

Each check produces findings. A finding has a **status**:

| Status | Meaning |
|---|---|
| `ok` | Checked, fine |
| `info` | Worth knowing, nothing to do |
| `known` | Looks wrong, is not — explained, and never raised again |
| `fixed` | The check fixed it by itself this run (always reversible; it says how) |
| `watch` | Fine now, heading somewhere worth watching |
| `claude` | Claude should change something — this file says what |
| `you` | Only the student can do it: accounts, posting, forms, approvals |
| `error` | The check itself could not run (network down, a script crashed) |
| `skip` | Not run this time (`--offline`, `--quick`, not `--deep`) |

and a **severity**: `low`, `medium`, `high`, `critical`. The verdict is
**URGENT** if anything is critical, **NEEDS ATTENTION** if Claude has something
of medium severity or more, or you have something high, and **ALL GOOD**
otherwise — even if small to-dos remain for you.

---

## The rules nothing here overrides

1. **Never unblind.** No `--unblind`, no `--publish`, no `--evaluate`, no
   `blind=False` on the real `data/` — not "just to check", not with a faked
   clock. The plan allows two looks: the Week-5 fit on 2 Oct (run with the
   student, on the day) and the final analysis after 11 Dec. Deviation 21 is what
   breaking this once cost. To check that December's path works, run
   `tests/test_unblinded_path.py`, which uses outcomes made up inside the test.
   The health check itself cannot unblind: its runner refuses those arguments,
   and everything it computes about the panel reads only which cells are filled.
2. **Only the daily job writes `data/`.** A row written on this Mac is not
   evidence of anything. The check puts such changes back (and keeps a patch).
3. **Push only with the student's OK**, given in that session. Code changes are
   tested on CI's Python 3.11 (`--deep --only deep.ci_parity`) before asking.
4. **Never edit or withdraw the OSF registration** (osf.io/x6kqg). The student
   posts addenda; Claude drafts them.
5. **What needs a §11 deviation and what does not.** Anything that reaches a
   model, enters the record, or moves a registered quantity is a numbered, dated
   row in PREREGISTRATION.md §11, and goes into the next addendum. Operator
   tooling — monitoring, alarms, reminders, the workflow's environment, this
   check — takes no number; it is recorded in AI-USE-LOG.md instead (precedent:
   the 16, 19 and 24 Sep sessions).
6. **Research-design choices belong to the student.** When a finding forces one
   (a model retiring, a host vanishing), bring the options with a recommendation,
   as on 19 Sep for gpt_small. Do not decide it silently.
7. **Never print a secret.** Keys live in `.env` and in GitHub's secrets.
8. **Do not re-raise what is known.** The `known` findings and the list at the
   end of this file were looked into and are not defects.

---

## What Claude does after a run

1. Read `.health/last-report.json` (the terminal output is a summary).
2. For every `fixed` finding: note it; nothing else to do.
3. For every `claude` or `error` finding: follow its section below. Fix, run the
   tests, re-run the check to confirm, commit locally. Deviation or AI-USE-LOG
   entry as rule 5 says.
4. For every `you` finding: pass it on in plain words, step by step, with the
   date it matters by.
5. Update the project memory with `facts.summary_line` and anything new.
6. Answer verdict first: all good or not, on plan or not. Then what was fixed,
   then the student's to-dos, numbered. Short for a routine check; complete when
   the student asked for an audit.

---

## Every check

### Your copy of the repository

#### `repo.git`
Is this the study's repository, on `main`? Everything the daily job runs is on
`main`. On another branch: finish or set that work aside, then `git switch main`.

#### `repo.fetch`
Fetches GitHub's latest. If GitHub cannot be reached, everything that compares
with GitHub uses the last fetch and says so. Retry when online.

#### `repo.worktree`
Anything uncommitted. **Fixes itself:** files under `data/` changed on this Mac
are put back to the committed record (the removed part is saved in
`.health/backups/`), and untracked files in `data/` move to
`.health/quarantine/`. The exception is receipts a live `neff.verify` run
appended to `data/ledger.jsonl` or `data/verification.jsonl`: they record real
spend, so Claude commits them with a message naming the run (precedent
`e433cea`) or discards them deliberately. Uncommitted code: finish it, run the
suite, commit — the Week-5 publisher refuses to run while code is uncommitted,
and GitHub never runs it.

#### `repo.sync`
This copy against GitHub. **Fixes itself:** behind → fast-forward. Diverged
(commits made here that are not on GitHub, plus the daily job's data commits on
GitHub) → the local commits are replayed on top of GitHub's (`git rebase`), but
only if they do not touch `data/` and nothing is uncommitted. A conflict is
undone automatically and reported. The replay changes the local commits' ids and
nothing else; the report gives the undo command. **You:** local commits that
are not on GitHub take effect only when pushed — reply "push". Claude pushes and
watches the `tests` workflow pass before the next collection.

Why it matters: on 2 Oct the Week-5 publisher refuses a copy that is behind
GitHub, and `git pull --ff-only` cannot fix a diverged copy.

#### `repo.branches`
**Fixes itself:** prunes git's records of worktrees whose folders are gone.
Leftover merged branches and worktrees are listed with the commands to remove
them; branches with work that is not on `main` are listed for a decision.
Branches on GitHub are deleted only with the student's OK.

#### `repo.secrets`
No key-shaped string in any committed file, and every `.env*` file ignored.
A hit is critical: remove it, commit, and the student revokes and replaces the
key — a key that was ever public is compromised whatever is committed later.

#### `repo.gitignore`
The keys, mock output and scratch files are all ignored. Add what is missing.

### GitHub Actions

#### `ci.runs`
Every daily run of the last week passed, and the latest `tests` run passed. A
failed daily run with a later success the same day is medium; without one it is
high. Find the failing step (`ci.steps`) and its message (`ci.annotations`); the
logs themselves need a login. **You**, if nothing succeeded for 30 hours: look
for a banner on the Actions page saying scheduled workflows are disabled (GitHub
disables them after 60 days without activity in the repository) and enable them;
then run the workflow by hand.

#### `ci.schedule`
Whether the daily job got its chances to run each day. GitHub delays scheduled
runs by hours and sometimes drops them, and a run that starts after midnight UTC
collects the *next* day. On 28 Sep the 13:10 run never started on its day and the
20:00 run alone collected it. A `watch` here means a day ended up with one run or
none. What to do: add a third daily slot between the two, at a minute off the top
of the hour (when GitHub's scheduler is busiest). A rerun is free — the collector
skips everything already asked — so a slot adds a chance, not a cost. Workflow
changes: a test in `tests/test_workflow_commit.py`, an AI-USE-LOG entry, and push
with the student's OK.

#### `ci.steps`
A step marked `continue-on-error` can fail every day inside a green run. Any
step that did not succeed in the last four daily runs is listed; find out why.

#### `ci.annotations`
Warnings GitHub attached to the latest runs — deprecations arrive here first
(Node 20, on 19 Sep). Act before the date the warning gives.

#### `ci.pins`
Runners on a named image (`ubuntu-24.04`, not `ubuntu-latest`, which moves to
26.04 mid-study), actions on a Node runtime GitHub still has, and Python 3.11
available for the image. Fix in both workflows together.

### The daily record

#### `record.parse`
Every file in `data/` parses line by line. An unreadable line: find the commit
that wrote it (`git log -p`), never edit the record by hand, and treat it as a
§11 matter.

#### `record.continuity`
`scripts/check_days.py`: every day since 1 Sep collected, every model above the
80% floor over the last 7 days, the bridge answering. **Today late** (past
13:10 UTC plus 10 hours with nothing collected) is critical and yours: GitHub →
Actions → daily-collection → Run workflow, then tell Claude. **A past day
missing** can never be recovered — Claude finds out why and records it as lost
in §11 and the next addendum; never back-fill. A model below the floor and still
failing: read `record.errors`. From 8 Dec no questions are asked (none could
resolve by the freeze); that is not a gap.

#### `record.day_shape`
Each day has the whole registered design: 25 questions × every model, 2
replicates per model, the H3 arm (gpt_mid, variants 1-4) from 14 Sep, the bridge
(gpt_small on its next route) from 20 Sep to 22 Oct. A missing answer means the
collector never asked — usually a run cut off by its 45-minute limit. Check that
day's run. Known: 3 Sep has 30 questions (deviation 2).

#### `record.errors`
What the week's failed answers say, sorted by who can act:

| Category | Means | Who, and what |
|---|---|---|
| quota | the account is out of credit | **You**, now: top up (the finding gives the steps). Every failed day is lost |
| auth | the key was refused | **You**: new key; update the GitHub secret and `.env` |
| retired | the host says the model does not exist | **Claude**, critical: see `vendors.retirements` |
| rate limit | the host throttled us | Waited out for up to 15 min a run (deviation 11). `known` once the model is back to 100%; watch if it persists |
| server | timeouts, 5xx | Transient; watch if it persists |
| parse | an answer without the JSON asked for | Over 2% of a model's answers: look at the raw responses (deviation 1 raised the token budget) |

#### `record.integrity`
No duplicate ids, no answer to an unknown question, every forecast in [0, 1], no
mock answers (a mock run writes only to the ignored `data/mock/`). Known: 36
question rows without an arm label are the pre-registration pilot.

#### `record.append_only`
Since collection began, every commit to the four record files only added lines,
and came from the daily job (`neff-collector`). Known: `e433cea` (verification
receipts, before the first collection). A deletion is critical: the record's
whole claim is that it only grows.

#### `record.hosts`
OpenRouter names the host that answered each question. A host on the routing's
ignore list answering (Novita, deviation 4), or anything but Azure answering on
the Azure-only route (deviation 23), means the routing guard broke. New hosts
are reported once; they are allowed (routing is deliberately free).

#### `record.served_ids`
Every answer came from the exact version pinned in `neff/config.py` (or its
registered route). A different id is a silent model swap: critical. Find which
host served it, and treat it like a retirement.

#### `record.logprobs`
Logprobs for the models the §5.4(a) re-estimate uses: the OpenAI models near
100%; llama lower because some hosts send none; deepseek mostly none (known,
deviations 12 and 19). A drop in a clean model: check whether a host changed.

#### `record.state`
Every question carries the market state H1 needs, stamped when it was asked. It
cannot be added afterwards; if it is missing, fix the collector before the next
run.

#### `record.prices`
Kalshi's price is recorded on the market questions (deviation 15). If it drops,
Kalshi probably renamed a field again (13 Sep).

#### `record.market`
The VIX and whether today is a stress day. A new high or VIX ≥ 25 is worth more
to H1 than any ordinary day: confirm it collected in full (the check does), and
re-run the workflow at once if not. A new low is `known`: the terciles are formed
in-sample, and §10 limitation 5 registers that a flat stress leg is reported as
untested while the ambiguity leg carries H1.

#### `record.ask_times`
When each day's questions were asked. Not a fault either way (each question
carries the market state published when it was asked, VALIDITY.md 7); it shows
how often the day depended on the backup run.

### Coverage and the panel

#### `panel.coverage`
The registered 80% floor (§5.6) on the panel that will be estimated: settled
questions, after the registered row exclusions. Close to or under the floor, it
projects where the model will stand at the next moment the rule is applied (the
Week-5 fit, then the freeze), counting only which already-asked questions have
an answer. Outcome-blind throughout. Nothing can be recovered — a lost answer
cannot be asked again — so this is for knowing, and for saying it first:
VALIDITY.md 8 and deviation 17 already register what happens if a model drops.

#### `panel.health`
What the daily job's "Panel health" step prints. Rows out of time order would
mean the loader broke.

#### `panel.bridge`
gpt_small answering the same questions on its current and its next route
(deviation 23): share identical and reliability, beside its own replicates.
Forecasts only.

### Settlements

#### `resolve.integrity`
Every settlement is 0 or 1, recorded once, for a real question. Known: four
pilot-era rows carry a `kalshi:edgar:` source.

#### `resolve.pending`
No contract is past its close without a settlement recorded. It asks Kalshi about
each one: settled there but not here after 30 hours means the daily resolver is
stuck (it looked that way on 16 Sep) — read `neff/collect.py resolve_outcomes`
and the run's steps.

#### `resolve.upcoming`
What settles in the next two weeks. The September payrolls (2 Oct) are the
fourth release the Week-5 fit needs.

#### `resolve.eligibility`
Every market question resolves by 11 Dec (§5.4(b)). Known: filing questions
carry no date; late ones are excluded on read (deviation 17 (8)).

#### `resolve.surprise`
Every settled listed release has its market surprise recorded (deviation 18).
The step that records it may fail quietly; the Week-5 fit needs it.

### The registered plan and its public copies

#### `plan.freeze`
`scripts/freeze_prereg.py`: the plan is unchanged outside §11. A change outside
§11 is critical: find it with `git log -p -- PREREGISTRATION.md` and undo it. New
deviations since the last run are listed.

#### `plan.registration`
osf.io/x6kqg is public and not withdrawn. If either fails: **you**, at once —
never confirm a withdrawal; contact OSF support.

#### `plan.zenodo`, `plan.osf_project`
What is public on Zenodo and on the OSF project — the way `you.addendum` knows
whether the addendum is posted.

#### `plan.addendum_scope`
The unposted addendum covers every deviation logged. Before posting: fold new
deviations into OSF-ADDENDUM-1.md. After posting: new deviations go into an
OSF-ADDENDUM-2.md in the same form.

#### `plan.docs`
README.md's deviation range and test count still match.

### Code and tests

#### `code.week5_check`
`scripts/week5_prediction.py --check` (read-only). Before 2 Oct it is NOT READY
for two expected reasons — 2 Oct's collection and the payrolls settlement — and
those are `known`. Anything else (behind GitHub, uncommitted code, data differing
from GitHub) must be fixed before 2 Oct. When it says READY and the window is
open: **you**, now — publish with Claude, and post the SHA-256 the same day.

#### `code.milestones`
`scripts/milestones.py`: the dated one-shot commitments. Due soon → put it in
the calendar; due → do it today.

#### `code.preflight`
`scripts/preflight.py`. "Not pushed" is the same thing `repo.sync` reports.

#### `code.tests`
The full suite. A failure here is critical: the daily job runs this suite before
it collects, and a failure there loses the day. This Mac runs Python 3.9 and
GitHub 3.11 — confirm with `--deep --only deep.ci_parity`.

#### `code.blind_analysis`
`scripts/analyze.py` end to end on permuted outcomes (the registered way to
exercise it). Nothing it computes is shown. It must work: the Week-5 fit and the
December look use this code.

#### `code.rehearsal`
The Week-5 pipeline on permuted outcomes. Must work before 2 Oct.

### Budget and API balances

#### `money.budget`
Spend against the $200 cap and the $110 arm cap, and the projection to the last
question. Above 60% it warns; above 85% the daily job's budget guard fails every
run, so act well before.

#### `money.openrouter`
OpenRouter's balance, read live with the key in `.env` (never printed).

#### `money.balances`
Each account's estimated balance against what is left to spend there. Balances
you read out are recorded once (`--balance`); the check subtracts the study's
spend since then. The estimate cannot see other use of the same account. Short:
**you**, top up (steps in the finding; keep auto-reload off). From 23 Oct
gpt_small's spend moves from OpenAI to OpenRouter; the projection follows the
route.

### Models and hosts

#### `vendors.retirements`
Reads Anthropic's, OpenAI's, Google's and Azure's retirement pages and finds the
rows about the panel's models — the rows themselves, not mentions of a model as
someone else's replacement. A shutdown before 11 Dec that is not already handled
is critical: read the page yourself, then bring the student the choice with a
recommendation (19 Sep: gpt_small). A row that **changed** since the last run is
high: read it. Anthropic gives 60 days' notice; while a notice could still land
a retirement inside the window, claude-haiku-4-5 is on `watch` — tell Claude if
an Anthropic deprecation e-mail arrives.

#### `vendors.hosts`
Every model served through OpenRouter has at least one working host that is not
ignored, and Azure still serves the gpt_small route. No host is critical.

### Dates

#### `dates.calendar`
The dates ahead: the Week-5 window, the route switch, the last asking day, the
freeze, the fair.

#### `dates.route_switch`
From 23 Oct, gpt_small's answers come from its registered route. Before then it
only counts down.

#### `dates.after_freeze`
After 11 Dec the registered final look is allowed — with the student.

#### `dates.web`
Checks that need judgement, done by Claude with a web search on a cadence, then
marked with `--ack`:

| Key | Every | What |
|---|---|---|
| `web.calendar` | 7 days | US government funding and the BLS release calendar for the next three weeks |
| `web.fair` | 14 days | NCSEF Region 6: registration deadline and rules; update SUBMISSION-TARGETS.md |
| `web.github` | 14 days | GitHub Actions changes that land before the freeze |

### Only you can do these

#### `you.addendum`
Addendum 1 on Zenodo (new version `1.1-addendum-1`) and on the OSF project
(files and a wiki page titled with the UTC date of posting). The finding lists
only the parts still missing. Best before 2 Oct 20:00 UTC, so it is public
before the first registered look.

#### `you.issues`
Old "collection at risk" alarms whose day is fine now can be closed; so can
anything not from the study's jobs (never install what it suggests). The
"needs a person" issue stays open until its dated step is done. A recent alarm
is Claude's to read first.

#### `you.isef`
Forms 1, 1A, 1B and 2A, your own Research Plan, and the fair's answer on AI use
kept in writing. The check cannot see these; mark them done with
`--ack you.isef` and `--ack you.fair_ai_answer`.

#### `you.prompt_log`
The Claude Code transcripts are the prompt log the ISEF rules require. The check
counts secret-shaped strings in them (never showing one). If it finds a token or
key, revoke it and make a new one, then `--ack you.github_token`. Never share the
transcripts as they are — ask Claude for a redacted copy. Back them up weekly
(`--ack you.prompt_log_backup`).

### This Mac

#### `local.python`
The venv imports the study's packages. This Mac runs 3.9; GitHub runs 3.11.

#### `local.leftovers`
**Fixes itself:** removes links in `~/.local/bin` that point into deleted Claude
scratch folders (left by `uv python install` on 19 Sep).

#### `local.disk`
Free space for the deep checks.

### Deep checks (`--deep`)

#### `deep.ci_parity`
The suite on Python 3.11 with exactly the pinned packages, in a fresh copy with
this copy's uncommitted changes applied — what CI will see. Required before
asking to push code.

#### `deep.time_travel`
The suite with the clock set to every instant that matters: the Week-5 window's
edges, the route switch, month ends, the last asking days, the freeze, 2027.
It verifies each clock really moved. No test can unblind the real record at any
date.

#### `deep.actionlint`
Both workflows pass actionlint.

#### `deep.linux_install`
The pinned set still resolves for GitHub's Linux and Python 3.11, exactly as
pinned.

#### `checker-errors`
A check that crashes reports `error` with the last lines of its traceback. Fix the
check (and add a test for the case), never the finding.

---

## Recording what a person reports

```bash
./.venv/bin/python scripts/health_check.py --ack you.isef "forms signed 30 Sep"
./.venv/bin/python scripts/health_check.py --ack web.calendar "funded through 11 Dec"
./.venv/bin/python scripts/health_check.py --balance anthropic=17.37 openai=8.83 google=8.98
./.venv/bin/python scripts/health_check.py --unack you.isef
```

| Key | Lasts | Means |
|---|---|---|
| `you.isef` | until cleared | Forms 1, 1A, 1B, 2A and the Research Plan are done |
| `you.fair_ai_answer` | until cleared | The fair's answer on AI use is saved in writing |
| `you.github_token` | until cleared | The token found in the prompt log was revoked |
| `you.prompt_log_backup` | 7 days | The prompt log was copied somewhere safe |
| `you.addendum` | until cleared | Addendum 1 is posted (only if the automatic check misses it) |
| `web.calendar`, `web.fair`, `web.github` | 7 / 14 / 14 days | The web check was done |

---

## Known, not problems

Each of these was looked into, and each is here so no check-in raises it again.

- **qwen rate limits.** DeepInfra is qwen's only usable host since Novita was
  ignored (deviation 4); it throttles now and then. Waits of up to 15 minutes a
  run recover most of it (deviation 11). A day with some qwen rows lost and full
  recovery the next day is designed behaviour.
- **Novita listed as a qwen host.** It is on the routing's ignore list; it
  cannot answer.
- **A new VIX low.** Terciles are in-sample; §10 limitation 5.
- **deepseek logprobs.** Mostly absent and partly broken (deviations 12, 19);
  the re-estimate runs without deepseek.
- **gpt_frontier outside the primary panel.** Registered as a secondary panel.
- **JPM and XOM filing questions.** Excluded on read (deviations 3 and 16).
- **Chevron's Q2 2026 revenue of $70.06B.** Real; SEC's data confirms it.
- **Four `kalshi:edgar:` settlement sources.** August pilot rows.
- **36 question rows without an arm label.** The pre-registration pilot.
- **30 questions on 3 Sep.** Deviation 2.
- **No questions from 8 Dec.** None could resolve by the freeze.
- **Late filing questions without a resolution date.** Deviation 17 (8).
- **`e433cea` touching the ledger.** Verification receipts before collection.
- **Days asked only by the evening run, or just after midnight.** GitHub's
  queue; each question carries the market state of the moment it was asked.
- **The Week-5 check NOT READY before 2 Oct.** Waiting for 2 Oct's collection
  and the payrolls settlement, by design.

---

## Where each check came from

| Date | Check-in | What it found, and the check it became |
|---|---|---|
| 3 Sep | "Did we run the data collection today?" | `scripts/check_days.py`, the evening backup run, the alarm → `record.continuity` |
| 4 Sep | The backup run re-selected a day; mock runs could write the record | deviation 2, `data/mock/` → `record.day_shape`, `record.integrity` |
| 9 Sep | "Is everything good?" | a routing fault that cost qwen two days (deviation 4), a stale filing series (deviation 3) → `record.hosts`, `record.errors` |
| 13 Sep | "Is everything working?" and the full audit | qwen 429s (deviation 11), logprobs missing (deviation 12), H1 unbuilt, Kalshi prices unread (deviation 15), the draft on OSF (deviation 13) → `record.logprobs`, `record.prices`, `plan.*` |
| 16 Sep | "Make sure all systems are working" | tests ran nowhere but the daily job, nothing tracked the one-shot dates, an unregistered unblinded run (deviation 21) → `code.tests`, `code.milestones`, rule 1 |
| 19 Sep | "Check everything and fully fix it" | gpt_small retiring (deviation 23), Node 20 and Ubuntu 26.04, httpx 1.0, a failed push that finished green, a stale copy able to publish (deviation 22) → `vendors.retirements`, `ci.pins`, `ci.annotations`, `code.week5_check` |
| 22 Sep | "Check everything, then my tasks" | balances against spend, the fair's date → `money.balances`, `dates.web` |
| 23 Sep | "Check everything else" | a second qwen host, a new VIX low → `vendors.hosts`, `record.market` |
| 24 Sep | "Make sure everything runs smoothly" | a reporting step could discard a day, December false alarms, package drift → `ci.steps`, `deep.*` |
| 29 Sep | This file | a diverged copy `git pull` could not fix, the 28 Sep dropped run, and Azure moving gpt-4.1-nano's retirement to 14 Oct → `repo.sync`, `ci.schedule`, `vendors.retirements` |

---

## Adding a check

1. Write it in `scripts/health_check.py` with `@check("group.name", "title",
   origin="the check-in or incident it comes from")`. Return `Finding`s.
2. Give it a section here — `tests/test_health_check.py` fails if any check has
   none.
3. Test it in `tests/test_health_check.py`, including the case where it speaks up.
4. If it computes anything about the panel, it reads which cells are filled,
   never an outcome.

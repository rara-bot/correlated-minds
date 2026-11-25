# OSF addendum 2 — ready to post

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
| Recorded at | PREREGISTRATION.md §11, deviations 25-29 |

---

## Step 2 — paste this as the OSF project wiki entry

```
ADDENDUM 2

Five new dated deviations, logged in PREREGISTRATION.md section 11 before the
registered final look (after 11 Dec), notes on deviations 24 and 19, and a
note naming the release that decides the Week-5 prediction. No
hypothesis, falsification clause, temperature, task mix, primary outcome or
multiple-testing correction has changed. Deviation 27 changes which task-days H3
and H6 are judged on, and is set out in full below. Deviations 28 and 29
change only how a request that failed is retried.

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
- We chose this from vendor documentation alone, without reading any outcome.

DEVIATION 26 (24 Oct): the questions of 21 Oct carry no market state
- On 21 Oct the St. Louis Fed's FRED website showed a maintenance page instead
  of data when the day's 25 questions were asked (18:00 UTC); it was back for
  the next day's questions. The questions were asked and answered as usual,
  but carry no VIX, no realised volatility and no interest rates.
- Nothing is filled in. Section 4 records the market state at ask time because
  it cannot be reconstructed afterwards. The 25 task-days are left out of H1's
  state regressions and its VIX tercile leg; they stay in the ambiguity leg and
  in every other analysis. They are 25 of the 1,330 primary task-days
  collected to 23 Oct.
- FRED's archive of past vintages (ALFRED) was checked as a repair and
  rejected: tested on every other day of the study, it reproduced the market
  state actually recorded on only 33 of 53 checks, missing by up to 3.5 VIX
  points, so it cannot say what FRED would have shown on 21 Oct.
- We chose this without reading any outcome.

DEVIATION 27 (31 Oct): H3 and H6 are judged on the questions asked before 10 Oct
- Deviations 24 and 25 each considered one retirement. Together they leave
  gemini-3.5-flash and gpt-4.1-nano under the 80% floor of section 5.6, so the
  primary panel ends at seven models with one within-family pair (Anthropic's).
- A run on permuted outcomes, printing only which tests could run, shows the
  effect. H3's cross-family arm is empty, so H3 reads untested. H6's exact
  permutation has 21 labelings, so its p cannot go below 1/21 = 0.048. Section
  3.1 widened the panel to nine to avoid exactly this.
- The verdicts of H3 and H6 are now read from the sub-panel deviation 25 already
  reports: the questions asked before 10 Oct, with all nine models and all three
  pairs (1260 labelings). On 31 Oct it holds 436 settled task-days (277 for H3),
  and up to 959 (650) once everything asked in it has settled. Estimators,
  intervals, thresholds and falsification clauses are unchanged.
- The primary estimate, H1, H2, H4 and H5 run on the primary panel as registered.
  H3 and H6 on the primary panel are still reported, labelled as not deciding.
- H4 matches the surviving panel size, so the human benchmark moves to seven. It
  is fixed now, from the pinned data. SPF RECESS at M = 7, headroom [interval]:
  h=1 0.1698 [0.060, 0.400], h=2 0.1168 [0.034, 0.298], h=3 0.1075 [0.027, 0.348],
  h=4 0.1181 [0.021, 0.376], h=5 0.1307 [0.023, 0.423].
- The Week-5 prediction is read on the primary panel as published. A smaller panel
  cannot hand it a hit: at every size up to nine, rho_bar above 0.147575 already
  puts headroom below 3.536360, so the rho_bar condition decides it.
- The cost: H3 and H6 rest on fewer and earlier task-days than the rest of the
  study. We chose this from which answers exist and from permuted runs, without
  reading any outcome, estimate or verdict of the real record.

DEVIATION 28 (14 Nov): a second host is ignored, and an empty reply is retried
- Between 3 and 13 Nov deepseek lost 23 of its 297 answers, 10 of them on 9 Nov,
  to two faults in how its answers are fetched, not in the model.
- 13 were lost when its usual host (DigitalOcean) was busy and OpenRouter passed
  the request to a second host, AtlasCloud, which rejects it (HTTP 400). Test
  requests on 14 Nov, outside the record, showed that AtlasCloud refuses the
  logprobs the study asks for and that no third host accepts the request. The
  registered wait for a busy host (deviation 11) never started, because the
  error that came back was AtlasCloud's.
- 10 arrived as HTTP 200 with no answer inside: no text, no tokens billed, no
  host named. OpenRouter documents this for a host that accepts a request and
  then fails. The collector read only the status and recorded "unparseable
  response" without retrying. 9 qwen answers have the same shape.
- The change: AtlasCloud joins Novita on the ignore list (deviation 4), so a
  busy host is waited out as deviation 11 intends; and a reply with an error
  and no answer, or with no text and no tokens billed, is retried like any
  other failed call (twice, 2 s and 4 s apart). A reply in which the model
  wrote something that is not the JSON asked for is recorded as before and
  never retried. Both apply from the collection of 16 Nov.
- The question, the models, temperature, token limit and the logprobs request
  are unchanged. The 32 rows already lost stay in the record as failures.
- 9 Nov is one of the four days so far asked with the VIX at or above 25
  (7 to 10 Nov), which H1's stress leg depends on. deepseek's place in the
  panel was not at risk (99.8% of 951 settled task-days). We chose this from
  the failed rows' error text and the test requests, without reading any
  forecast, outcome, estimate or verdict.

DEVIATION 29 (25 Nov): a call no host will take with logprobs is asked without them
- On 24 and 25 Nov deepseek lost all 54 of its answers. Every call came back
  from OpenRouter as HTTP 404, "No endpoints found that can handle the
  requested parameters". Every other model answered every question.
- DigitalOcean, deepseek's only host from 16 Nov and the last one that accepted
  its request with logprobs, no longer serves the model. The three hosts left
  (SiliconFlow, DeepInfra, Baidu) do not accept logprobs, and the study requires
  every host to serve the request as sent (deviation 4). A test request on
  25 Nov, outside the record, was answered by DeepInfra once logprobs were left
  out.
- Deviation 10 promised that asking for logprobs could never cost an answer: a
  host that rejects them is asked again without them. That reissue looked for an
  error naming logprobs, and this one does not name them.
- The change: that one OpenRouter reply now counts as a refusal of logprobs, so
  the call is reissued once without them and nothing else. Temperature 0 and the
  token limit are still required of the host. Every run asks with logprobs
  first, so if a host that accepts them comes back, they return by themselves.
- What it costs: nothing the logprob sensitivity uses. DigitalOcean's logprobs
  were already judged unusable under deviation 19. deepseek is now served by
  other hosts, and the host of every answer is recorded.
- 24 Nov carries the highest VIX of the study (35.89) and 25 Nov 26.62. The 54
  rows stay in the record as failures. deepseek stands at 99.4% of the 1,071
  settled task-days and would end near 89% at the freeze even with no further
  answer, so its place in the panel was not at risk. We chose this from the
  failed rows' error text, OpenRouter's public host list and two test requests,
  without reading any forecast, outcome, estimate or verdict.

A NOTE ON DEVIATION 24
- After deviation 24 was written, Microsoft's schedule moved Azure's retirement of
  gpt-4.1-nano back to 2027-04-14 (seen 9 Oct). Deviation 24 is kept as written:
  gpt-4.1-nano is asked through OpenAI, as registered, to 22 Oct, and not at all
  from 23 Oct, when OpenAI shuts it down; no model changes host.

A NOTE ON DEVIATION 19
- Deviation 19 judges logprobs per source: a model and the host that served
  it. On 13 Sep no deepseek source passed, so it wrote that the section 5.4(a)
  logprob leg rests on gpt_mid, gpt_small and llama. Two hosts that began
  serving deepseek later (Mara from 29 Sep, SambaNova from 3 Oct) have returned
  consistent logprobs on every row, so by the same rule their rows count, and
  the leg now includes deepseek on the few task-days those hosts answered
  (4 of 312 settled task-days on 24 Oct). The rule is applied as written;
  nothing was changed.

A NOTE ON THE WEEK-5 PREDICTION
- The first holdout release at or above the registered surprise threshold
  has closed: the October jobs report, 6 Nov 13:29 UTC. The surprise is computed
  from market prices only and is public in data/release_surprise.jsonl:
  KXPAYROLLS-26OCT 0.2468 and KXU3-26OCT 0.2612, both above 0.2425625.
- The two markets closed at the same minute, which deviation 18 (7)'s "first
  eligible release" does not order. It does not need to: no question on
  KXU3-26OCT was asked from 3 Oct, so it has no holdout task-days and is not
  eligible. KXPAYROLLS-26OCT (32 questions asked from 3 Oct) is the only
  release that can decide it now. If its panel turns out not estimable, the
  next qualifying release decides, as registered.
- We state this from the question list and the public surprises alone. No
  forecast, outcome, estimate or verdict was read; the verdict is computed only
  after the freeze, as deviation 17 (9) sets out.

VERIFICATION
  Repository:  https://github.com/rara-bot/correlated-minds
  Zenodo:      10.5281/zenodo.22220263 (latest version)
  ./.venv/bin/python scripts/freeze_prereg.py --check  ->  "intact outside section 11"
```

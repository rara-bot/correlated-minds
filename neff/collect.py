"""The daily collection runner -- the spine of the study.

Runs once per day, unattended, for 15 weeks. Everything here is written for that
setting: it must be safe to re-run, safe to interrupt, and it must never spend
more than it is allowed.

Guarantees:

  IDEMPOTENT   Observation ids are content-addressed from
               (task_id, model_key, prompt_variant). A day that is re-run skips
               work already done and cannot double-bill or double-count.

  RESUMABLE    Every observation is fsynced as it completes, so a cancelled job
               loses at most the call in flight.

  BOUNDED      The ledger refuses any call that would breach the cap, and the
               runner stops that arm cleanly rather than thrashing.

  HONEST       Failures are recorded as observations carrying an error, never
               dropped. Silent omission would bias the panel toward calm days,
               because rate limits cluster when markets are busy -- precisely
               the observations H1 depends on.
"""

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import fields
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from .config import (
    ARM_CAPS_USD,
    BUDGET_USD,
    LEDGER_PATH,
    ROOT,
    OBS_PATH,
    RESOLUTIONS_PATH,
    TASKS_PATH,
    RunConfig,
    REPLICATE_VARIANT,
    mock_sandbox,
)
from .ledger import Ledger
from .providers import ask
from .store import JsonlStore, Observation, Resolution, Task, observation_id
from .tasks import build_daily_tasks, summarize


def _log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def run_day(
    config: Optional[RunConfig] = None,
    as_of: Optional[date] = None,
    use_mock: bool = False,
) -> Dict[str, object]:
    """Collect one day of the panel."""
    config = config or RunConfig()
    today = as_of or datetime.now(timezone.utc).date()

    # A MOCK RUN DOES NOT WRITE TO THE STUDY'S FILES.
    #
    # Its forecasts are fabricated, and the record they were landing in is the
    # one whose contents are the evidence -- see `mock_sandbox` in config.py for
    # why downstream filtering was not enough. Resolved here rather than at the
    # CLI because this is where a writer is opened, and a rule enforced anywhere
    # else is one a programmatic caller walks straight past.
    #
    # The ledger goes with them, which means a mock run reports $0.00 spent of
    # its own empty sandbox rather than inheriting real spend. That is the
    # intended reading: one rule, no exceptions, and a budget line that cannot be
    # mistaken for the real one. `--dry-run` remains the way to price a day
    # against the real ledger.
    paths = (mock_sandbox if use_mock else (lambda p: p))
    ledger_path, tasks_path, obs_path = (
        paths(LEDGER_PATH), paths(TASKS_PATH), paths(OBS_PATH)
    )

    ledger = Ledger(ledger_path, cap_usd=BUDGET_USD, arm_caps=dict(ARM_CAPS_USD))
    task_store = JsonlStore(tasks_path)
    obs_store = JsonlStore(obs_path)

    models = config.models()
    _log(f"collection for {today} | {len(models)} models | arm={config.arm}")
    if use_mock:
        _log(f"MOCK -- writing to {obs_store.path.parent}, not the study record")
    _log(f"budget: ${ledger.spent:.2f} spent of ${ledger.cap_usd:.2f}")

    # 1. Today's questions.
    #
    # A SECOND RUN ON THE SAME DAY MUST NOT RE-SELECT THEM.
    #
    # `build_daily_tasks` picks from live sources, so it is not stable within a
    # day: called at 17:04 and again at 22:24 it can return questions that did
    # not exist at the first call. On 3 Sep 2026 that is exactly what happened --
    # the 20:00 UTC backup run added 5 Kalshi housing-start rungs on top of the
    # morning's 25, and the day closed with 30 tasks carrying a market-state
    # snapshot five hours removed from the rest of it.
    #
    # The backup exists to finish an interrupted day, never to extend a finished
    # one. So if this day already has registered tasks, those tasks ARE the day,
    # and this run's only job is to fill in observations still missing against
    # them. Only a day with nothing registered at all gets a fresh selection.
    _TASK_FIELDS = {f.name for f in fields(Task)}
    already_registered = [
        row for row in task_store.read_all()
        if str(row.get("asked_at", ""))[:10] == today.isoformat()
        and row.get("arm") == config.arm
    ]
    if already_registered:
        tasks = [
            Task(**{k: v for k, v in row.items() if k in _TASK_FIELDS})
            for row in already_registered
        ]
        _log(
            f"reusing the {len(tasks)} task(s) already registered for {today} "
            f"-- a rerun finishes the day, it does not extend it"
        )
    else:
        tasks = build_daily_tasks(as_of=today, max_tasks=config.tasks_per_day)
    if not tasks:
        _log("no tasks available today -- nothing to collect")
        return {"date": today.isoformat(), "tasks": 0, "observations": 0}

    stats = summarize(tasks)
    _log(
        f"built {stats['n_tasks']} tasks | horizon "
        f"{stats['min_days_out']}-{stats['max_days_out']}d "
        f"(median {stats['median_days_out']}d)"
    )

    # Register tasks before any model is asked. Ordering matters: the task file
    # is the record that the question existed before the answers did.
    #
    # A DRY RUN MUST NOT WRITE HERE. `--dry-run` is documented as "prices the day,
    # asks nothing" and the OSF gate lets it through on the grounds that it
    # "touches nothing real" -- but it used to append to the append-only task
    # registry all the same. Those rows can never acquire observations, so they
    # are permanent orphans in the public record; and SETUP.md tells the operator
    # to smoke-test the workflow with `dry_run` ticked, which would have committed
    # a batch of them to the public repository dated BEFORE the pre-registration.
    known_tasks = task_store.existing_ids("task_id")
    new_tasks = [t for t in tasks if t.task_id not in known_tasks]
    for task in new_tasks:
        task.arm = config.arm
    if config.dry_run:
        _log(f"would register {len(new_tasks)} new tasks -- dry run, nothing written")
    else:
        if new_tasks:
            task_store.append_many(new_tasks)
        _log(f"registered {len(new_tasks)} new tasks ({len(tasks) - len(new_tasks)} already known)")

    # 2. Work out what still needs asking.
    done = obs_store.existing_ids("obs_id")
    pending = []
    for task in tasks:
        for variant in range(max(1, config.prompt_variants)):
            for spec in models:
                obs_id = observation_id(task.task_id, spec.key, variant)
                if obs_id not in done:
                    pending.append((task, spec, variant))

    # 2b. TEST-RETEST REPLICATES.
    #
    # `TEMPERATURE = 0.0` is registered in §9 so that cross-model differences
    # reflect the models rather than our sampling. Measured on 22 Aug 2026,
    # 3 prompts x 4 repetitions, that holds for only half the panel:
    #
    #   deterministic  claude_haiku, gpt_mid, qwen, deepseek, gpt_frontier
    #   varies         claude_sonnet .033, gpt_small .033, gemini_flash_pro .033,
    #                  llama .040, gemini_flash .093   (mean spread in probability)
    #
    # Which models vary shifts between runs, so it is infrastructure -- batched
    # inference and, on OpenRouter, backend routing -- not a model property, and
    # no setting removes it.
    #
    # This matters because the noise is IDIOSYNCRATIC: uncorrelated across
    # models, it inflates apparent independence, pushing rho_bar down and N_eff
    # up. That is the conservative direction -- it biases AGAINST the study's own
    # hypothesis -- but its SIZE was unknown, and "unknown but probably small" is
    # not something to hand a reviewer.
    #
    # So a few questions each day are asked to every model TWICE, identically.
    # The spread between the two answers estimates each model's noise floor,
    # which turns an unquantified threat into a measured reliability coefficient
    # and lets §5.4(d) report rho_bar both raw and disattenuated.
    #
    # Stored at a reserved prompt_variant so they cannot leak into anything else:
    # `panel.load_panel` filters to variant 0, and H3's variants are 0..4.
    if config.replicates_per_day > 0 and not config.dry_run:
        rng = random.Random(f"{config.seed}|replicate|{today.isoformat()}")
        pool = sorted(tasks, key=lambda t: t.task_id)
        chosen = rng.sample(pool, min(config.replicates_per_day, len(pool)))
        for task in chosen:
            for spec in models:
                obs_id = observation_id(task.task_id, spec.key, REPLICATE_VARIANT)
                if obs_id not in done:
                    pending.append((task, spec, REPLICATE_VARIANT))
        _log(f"test-retest: {len(chosen)} task(s) re-asked to all {len(models)} models")

    if not pending:
        _log("every observation for today already collected -- nothing to do")
        return {"date": today.isoformat(), "tasks": len(tasks), "observations": 0}

    _log(f"{len(pending)} observations to collect")

    if config.dry_run:
        estimated = sum(
            spec.price.estimate(len(task.prompt) // 4 + 200, 300)
            for task, spec, _ in pending
        )
        _log(f"DRY RUN -- would spend about ${estimated:.4f}")
        return {
            "date": today.isoformat(),
            "tasks": len(tasks),
            "observations": 0,
            "estimated_usd": round(estimated, 4),
            "dry_run": True,
        }

    # 3. Ask, concurrently but politely.
    collected: List[Observation] = []
    failures = 0

    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        futures = {
            pool.submit(
                ask,
                spec=spec,
                task_id=task.task_id,
                prompt=task.prompt,
                ledger=ledger,
                arm=config.arm,
                prompt_variant=variant,
                use_mock=use_mock,
            ): (task, spec, variant)
            for task, spec, variant in pending
        }

        for future in as_completed(futures):
            task, spec, variant = futures[future]
            try:
                obs = future.result()
            except Exception as exc:                        # noqa: BLE001
                obs = Observation(
                    obs_id=observation_id(task.task_id, spec.key, variant),
                    task_id=task.task_id,
                    model_key=spec.key,
                    model_id_returned="",
                    provider=spec.provider,
                    prompt_variant=variant,
                    forecast=None,
                    direction=None,
                    confidence=None,
                    error=f"runner exception: {type(exc).__name__}: {exc}",
                    arm=config.arm,
                )

            obs_store.append(obs)          # fsynced immediately
            collected.append(obs)
            if obs.error:
                failures += 1

    usable = [o for o in collected if o.forecast is not None]
    _log(
        f"collected {len(collected)} observations "
        f"({len(usable)} usable, {failures} with errors)"
    )
    _log(f"spend today: ${sum(o.usd for o in collected):.4f} | total ${ledger.spent:.2f}")

    # Model-drift check: a provider silently serving a different model is the
    # highest-impact silent failure in a longitudinal panel.
    drift = sorted(
        {
            f"{o.model_key} -> {o.model_id_returned}"
            for o in collected
            if o.model_id_returned and not o.model_id_returned.startswith(
                next((m.model_id for m in models if m.key == o.model_key), "")
            )
        }
    )
    if drift:
        _log(f"!! MODEL ID DRIFT: {drift}")

    return {
        "date": today.isoformat(),
        "tasks": len(tasks),
        "observations": len(collected),
        "usable": len(usable),
        "failures": failures,
        "spend_today_usd": round(sum(o.usd for o in collected), 4),
        "ledger": ledger.summary(),
        "drift": drift,
    }


def resolve_outcomes(use_mock: bool = False) -> Dict[str, object]:
    """Score any task whose event has now settled.

    Runs alongside collection each day. Resolutions are append-only and written
    only once per task -- a task that is already resolved is never revisited, so
    a later data revision cannot silently rewrite history.

    `use_mock` carries the same containment as `run_day`: it resolves the mock
    run's own tasks into the mock run's own file. Settlements themselves are read
    from the live sources either way -- an outcome is not something there is a
    fake version of -- but a mock run must not append to the real resolution
    record, which is the file that closes the loop on "the question predates the
    answer".
    """
    from .sources import edgar, kalshi

    paths = (mock_sandbox if use_mock else (lambda p: p))
    task_store = JsonlStore(paths(TASKS_PATH))
    resolution_store = JsonlStore(paths(RESOLUTIONS_PATH))

    resolved = resolution_store.existing_ids("task_id")
    tasks = task_store.read_all()

    # One settlement lookup per external contract, not per task-day.
    by_ref: Dict[str, List[Dict]] = {}
    for task in tasks:
        if task.get("task_id") in resolved:
            continue
        ref = task.get("source_ref")
        if ref:
            by_ref.setdefault(str(ref), []).append(task)

    if not by_ref:
        _log("nothing new to resolve")
        return {"checked": 0, "resolved": 0}

    _log(f"checking settlement for {len(by_ref)} contracts")
    new: List[Resolution] = []

    for ref, group in by_ref.items():
        if ref.startswith("edgar:"):
            # edgar:<cik>:<last_reported_period_end>
            try:
                _, cik_s, last_end = ref.split(":", 2)
                threshold = next(
                    (
                        float(t["state"]["threshold"])
                        for t in group
                        if isinstance(t.get("state"), dict)
                        and t["state"].get("threshold") is not None
                    ),
                    None,
                )
            except (ValueError, TypeError):
                continue
            if threshold is None:
                continue
            outcome = edgar.resolve_filing_task(int(cik_s), last_end, threshold)
        else:
            outcome = kalshi.fetch_settlement(ref)

        if outcome is None:
            continue
        for task in group:
            new.append(
                Resolution(
                    task_id=str(task["task_id"]),
                    outcome=float(outcome),
                    source=f"kalshi:{ref}",
                    note="settled",
                )
            )

    if new:
        resolution_store.append_many(new)
    _log(f"resolved {len(new)} task-days across {len(by_ref)} contracts")
    return {"checked": len(by_ref), "resolved": len(new)}


# Arms that may legitimately run before the OSF registration is public. The pilot
# is a separately registered arm, excluded from the primary analysis, and exists
# precisely so the instrument can be exercised before the plan is locked.
PRE_REGISTRATION_ARMS = {"pilot"}

OSF_URL_PATH = ROOT / ".osf_url"

# CI reads the registration URL from the repository, not from the laptop that
# created it. `.osf_url` must therefore be COMMITTED, not merely written -- an
# uncommitted file blocks every scheduled run with a message about a missing
# registration that is, locally, plainly present. `OSF_URL` is accepted as an
# environment override so the study can still run from a checkout where the file
# has not landed yet.
OSF_URL_ENV = "OSF_URL"


def _looks_like_a_registration_url(value: str) -> bool:
    """A placeholder must not satisfy the gate.

    The original check was "non-empty", which `echo pending > .osf_url` passes.
    The point of this gate is to make premature collection impossible, and a
    gate that a typo opens is not a gate.
    """
    return value.startswith(("http://", "https://")) and len(value) > len("https://") + 3


def registered_osf_url() -> str:
    """The recorded registration URL, from the environment or the repo file."""
    from os import environ

    for value in (environ.get(OSF_URL_ENV, ""), _read_osf_file()):
        value = value.strip()
        if _looks_like_a_registration_url(value):
            return value
    return ""


def _read_osf_file() -> str:
    try:
        return OSF_URL_PATH.read_text()
    except OSError:
        return ""


def osf_is_registered() -> bool:
    """True only once the operator has recorded a public OSF registration URL."""
    return bool(registered_osf_url())


def require_osf_before_real_collection(arm: str, dry_run: bool, use_mock: bool) -> None:
    """Refuse to collect primary study data before the registration is public.

    The study's entire claim is "this was registered before the outcome existed".
    Data collected before the OSF registration goes public cannot support that
    claim -- it has to be discarded or reported separately, and either way the
    strongest evidence in the project is weakened for no gain.

    This is enforced here, in code, for the same reason the budget cap is: the
    failure is silent. Nothing about a pre-registration run looks wrong at the
    time. It only becomes a problem months later, in front of a judge asking how
    they know the plan came first.

    Mock and dry-run touch nothing real. The pilot arm is explicitly permitted.
    """
    if use_mock or dry_run or arm in PRE_REGISTRATION_ARMS:
        return
    if osf_is_registered():
        return
    raise SystemExit(
        "\n".join([
            "=" * 68,
            "  REFUSING TO COLLECT -- OSF registration not confirmed.",
            "=" * 68,
            f"  arm={arm!r} writes primary study data, but {OSF_URL_PATH.name} is",
            "  missing or empty, so the pre-registration is not yet public.",
            "",
            "  Collecting now would produce data you cannot defend as",
            "  'registered in advance'. That is the study's core evidence.",
            "",
            "  When -- and only when -- your OSF registration is live:",
            "      echo 'https://osf.io/XXXXX' > .osf_url",
            "      git add .osf_url && git commit -m 'Record OSF registration' && git push",
            "",
            "  The COMMIT is not optional. The scheduled job runs from a fresh",
            "  checkout, so a file that exists only on your laptop leaves every",
            "  automated collection day failing on this same message.",
            "  (CI alternative: set an OSF_URL repository variable.)",
            "",
            "  To work in the meantime, any of these still run:",
            "      --mock              offline, zero spend",
            "      --dry-run           prices the day, asks nothing",
            "      --arm pilot         real calls, separately registered arm",
            "=" * 68,
        ])
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="neff daily collection")
    parser.add_argument("--dry-run", action="store_true", help="price the day, ask nothing")
    parser.add_argument("--mock", action="store_true", help="offline mock provider, zero spend")
    parser.add_argument("--arm", default="ws1_prospective")
    parser.add_argument("--tasks", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--variants", type=int, default=1)
    parser.add_argument("--models", default=None, help="comma-separated model keys")
    parser.add_argument("--no-resolve", action="store_true")
    args = parser.parse_args(argv)

    config = RunConfig(
        arm=args.arm,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
        prompt_variants=args.variants,
        model_keys=args.models.split(",") if args.models else None,
    )
    if args.tasks is not None:
        config.tasks_per_day = args.tasks

    require_osf_before_real_collection(
        arm=args.arm, dry_run=args.dry_run, use_mock=args.mock
    )

    if args.mock:
        # A mock run reports observation counts and a dollar figure exactly like
        # a real one. On 17 Aug 2026 that was mistaken for a completed setup, and
        # 140 fabricated forecasts sat in the study log for a day. Be loud.
        print("=" * 64)
        print("  MOCK MODE -- NO API CALLS. Every forecast below is FABRICATED.")
        print(f"  Rows go to {mock_sandbox(OBS_PATH).parent}/ -- never to the study")
        print("  record, and never to git. This is NOT a real pilot.")
        print("=" * 64)

    summary = run_day(config=config, use_mock=args.mock)

    if args.mock:
        print("=" * 64)
        print("  MOCK RUN COMPLETE -- nothing above was real.")
        print("  For a real pilot, set your API keys in .env and drop --mock.")
        print("=" * 64)
    if not args.no_resolve and not args.dry_run:
        summary["resolution"] = resolve_outcomes(use_mock=args.mock)

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

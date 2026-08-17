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
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from .config import (
    ARM_CAPS_USD,
    BUDGET_USD,
    LEDGER_PATH,
    OBS_PATH,
    RESOLUTIONS_PATH,
    TASKS_PATH,
    RunConfig,
)
from .ledger import Ledger
from .providers import ask
from .store import JsonlStore, Observation, Resolution, observation_id
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

    ledger = Ledger(LEDGER_PATH, cap_usd=BUDGET_USD, arm_caps=dict(ARM_CAPS_USD))
    task_store = JsonlStore(TASKS_PATH)
    obs_store = JsonlStore(OBS_PATH)

    models = config.models()
    _log(f"collection for {today} | {len(models)} models | arm={config.arm}")
    _log(f"budget: ${ledger.spent:.2f} spent of ${ledger.cap_usd:.2f}")

    # 1. Build today's questions.
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
    known_tasks = task_store.existing_ids("task_id")
    new_tasks = [t for t in tasks if t.task_id not in known_tasks]
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


def resolve_outcomes() -> Dict[str, object]:
    """Score any task whose event has now settled.

    Runs alongside collection each day. Resolutions are append-only and written
    only once per task -- a task that is already resolved is never revisited, so
    a later data revision cannot silently rewrite history.
    """
    from .sources import edgar, kalshi

    task_store = JsonlStore(TASKS_PATH)
    resolution_store = JsonlStore(RESOLUTIONS_PATH)

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

    summary = run_day(config=config, use_mock=args.mock)
    if not args.no_resolve and not args.dry_run:
        summary["resolution"] = resolve_outcomes()

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

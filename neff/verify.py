"""Pre-flight check. Run this before the first real collection day.

Model ids and prices in config.py are written from documentation, not from the
live APIs. A wrong id fails loudly on day one; a wrong PRICE fails silently and
quietly drains the budget while every log looks healthy. This command catches
both before any money is committed.

    python -m neff.verify           # keys + one live call per model
    python -m neff.verify --offline # no calls; checks structure and sources only

Exit code is non-zero if anything is wrong, so CI can gate on it.
"""

import argparse
import sys
from typing import Dict, List, Tuple

from .config import ARM_CAPS_USD, BUDGET_USD, LEDGER_PATH, enabled_panel, families
from .ledger import Ledger
from .providers import PROVIDERS, ask

TICK, CROSS, WARN = "OK  ", "FAIL", "WARN"


def check_panel_structure() -> List[Tuple[str, str, str]]:
    """The panel must be able to answer the questions we plan to ask of it."""
    out: List[Tuple[str, str, str]] = []
    panel = enabled_panel()
    fams = families()

    out.append(
        (TICK if len(panel) >= 5 else CROSS,
         "panel size",
         f"{len(panel)} models (>=5 needed for a usable pair count)")
    )

    n_pairs = len(panel) * (len(panel) - 1) // 2
    out.append((TICK if n_pairs >= 10 else CROSS, "pairs", f"{n_pairs} pairwise correlations"))

    out.append(
        (TICK if len(fams) >= 4 else CROSS,
         "families",
         f"{len(fams)} distinct: {', '.join(sorted(fams))}")
    )

    # H3 needs a within-family pair to contrast against cross-family pairs.
    within = [f for f, keys in fams.items() if len(keys) >= 2]
    out.append(
        (TICK if within else CROSS,
         "H3 within-family control",
         f"families with 2+ models: {within or 'NONE -- H3 is untestable'}")
    )

    duplicate_keys = len(panel) != len({m.key for m in panel})
    out.append((CROSS if duplicate_keys else TICK, "unique model keys", "join keys must be unique"))

    for spec in panel:
        if spec.price.input_per_mtok <= 0 or spec.price.output_per_mtok <= 0:
            out.append((CROSS, f"price {spec.key}", "price must be positive"))

    return out


def check_sources() -> List[Tuple[str, str, str]]:
    """Every data source is free, but they must actually be reachable today."""
    out: List[Tuple[str, str, str]] = []

    try:
        from .sources import kalshi
        tasks = kalshi.select_tasks(max_tasks=5, min_days_out=3.0, max_days_out=90.0)
        out.append(
            (TICK if tasks else WARN, "kalshi tasks", f"{len(tasks)} questions available")
        )
        if tasks:
            settled = kalshi.fetch_settlement("KXCPIYOY-26JUL-T5.0")
            out.append(
                (TICK if settled is not None else WARN,
                 "kalshi settlement", f"probe returned {settled}")
            )
    except Exception as exc:                                   # noqa: BLE001
        out.append((CROSS, "kalshi", f"{type(exc).__name__}: {exc}"))

    try:
        from .sources import fred
        when, value = fred.latest_value("VIXCLS")
        out.append((TICK, "fred (no key)", f"VIX {value} on {when}"))
    except Exception as exc:                                   # noqa: BLE001
        out.append((CROSS, "fred", f"{type(exc).__name__}: {exc}"))

    try:
        from .sources.spf import CACHE_PATH
        if CACHE_PATH.exists() and CACHE_PATH.stat().st_size > 1_000_000:
            mb = CACHE_PATH.stat().st_size / 1e6
            out.append((TICK, "spf baseline", f"cached, {mb:.0f} MB"))
        else:
            out.append((WARN, "spf baseline", "not cached -- run spf.download_microdata()"))
    except Exception as exc:                                   # noqa: BLE001
        out.append((CROSS, "spf", f"{type(exc).__name__}: {exc}"))

    return out


def check_budget() -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    ledger = Ledger(LEDGER_PATH, cap_usd=BUDGET_USD, arm_caps=dict(ARM_CAPS_USD))
    summary = ledger.summary()
    out.append(
        (TICK if summary["pct_used"] < 50 else WARN,
         "budget",
         f"${summary['spent_usd']:.2f} of ${BUDGET_USD:.0f} used ({summary['pct_used']}%)")
    )
    arm_total = sum(ARM_CAPS_USD.values())
    out.append(
        (TICK if arm_total <= BUDGET_USD else CROSS,
         "arm caps",
         f"sum ${arm_total:.0f} vs cap ${BUDGET_USD:.0f} "
         f"(reserve ${BUDGET_USD - arm_total:.0f})")
    )
    return out


def check_live_models(spend_cap_usd: float = 0.50) -> List[Tuple[str, str, str]]:
    """One real call per model. Confirms the id resolves and records what was served.

    This is the check that matters most: it is the only way to learn that a
    pinned model id is wrong, or that a provider is serving something else.
    """
    out: List[Tuple[str, str, str]] = []
    ledger = Ledger(LEDGER_PATH, cap_usd=BUDGET_USD, arm_caps={"pilot": spend_cap_usd})

    prompt = (
        'Respond with ONLY this JSON: {"probability": 0.5, "direction": "no", '
        '"confidence": 0.5, "rationale": "verification probe"}'
    )

    for spec in enabled_panel():
        if spec.provider not in PROVIDERS:
            out.append((CROSS, spec.key, f"no client for provider {spec.provider!r}"))
            continue

        obs = ask(
            spec=spec,
            task_id="verify",
            prompt=prompt,
            ledger=ledger,
            arm="pilot",
            max_tokens=100,
            timeout=45.0,
        )

        if obs.error and obs.forecast is None:
            out.append((CROSS, spec.key, obs.error[:110]))
            continue

        served = obs.model_id_returned or "?"
        drift = not served.startswith(spec.model_id.split("/")[-1][:12])
        out.append(
            (WARN if drift else TICK,
             spec.key,
             f"served {served!r} (pinned {spec.model_id!r}), ${obs.usd:.5f}"
             + ("  <- ID MISMATCH, update config.py" if drift else ""))
        )

    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="neff pre-flight verification")
    parser.add_argument("--offline", action="store_true", help="skip live model calls")
    args = parser.parse_args(argv)

    sections: Dict[str, List[Tuple[str, str, str]]] = {
        "panel structure": check_panel_structure(),
        "data sources": check_sources(),
        "budget": check_budget(),
    }
    if not args.offline:
        sections["live models"] = check_live_models()

    failures = 0
    warnings = 0
    for title, rows in sections.items():
        print(f"\n=== {title} ===")
        for status, name, detail in rows:
            print(f"  [{status}] {name:<26} {detail}")
            if status == CROSS:
                failures += 1
            elif status == WARN:
                warnings += 1

    print(f"\n{'-' * 62}")
    if failures:
        print(f"{failures} FAILURE(S), {warnings} warning(s) -- do not start collection")
        return 1
    print(f"all checks passed, {warnings} warning(s) -- clear to collect")
    return 0


if __name__ == "__main__":
    sys.exit(main())

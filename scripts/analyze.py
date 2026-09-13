#!/usr/bin/env python
"""Run every registered analysis that exists in code. Blind unless the freeze has passed.

    ./.venv/bin/python scripts/analyze.py                 # blind: outcomes permuted
    ./.venv/bin/python scripts/analyze.py --out run.json  # and write the result
    ./.venv/bin/python scripts/analyze.py --unblind       # refuses before 2026-12-12

A blind run is safe on any day and is how the pipeline is exercised: every shape
that can break it is real, and the forecast-to-outcome link is not. The only
registered unblinded looks are the Week-5 fit (`scripts/week5_prediction.py
--publish`) and this script after the 11 Dec freeze (PREREGISTRATION.md 11,
deviation 17).

What it runs: the primary estimate with both registered intervals
(`analysis.run`), every quantity the plan reports always (`report`), and H1
(`h1`). What it does not yet run is listed in its output, so nobody mistakes a
missing analysis for a null one.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from neff import analysis, h1, report  # noqa: E402
from neff.config import DATA_FREEZE  # noqa: E402
from neff.panel import load_panel, reliability_report  # noqa: E402

NOT_YET_IMPLEMENTED = [
    "H2 base-rate convergence (confirmatory)",
    "H3 intra-model vs within- vs cross-family N_eff, with permutation inference",
    "H4 human comparison at matched accuracy against SPF RECESS",
    "H5 interval on the Type A minus Type B difference",
    "H6 exact permutation over family labels with capability terms",
]


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--unblind", action="store_true")
    parser.add_argument("--n-boot", type=int, default=analysis.N_BOOT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    today = datetime.now(timezone.utc).date().isoformat()
    if args.unblind and today <= DATA_FREEZE:
        raise SystemExit(f"REFUSING to unblind on {today}: the registered final look is after "
                         f"the {DATA_FREEZE} freeze. The Week-5 fit has its own script.")
    blind = not args.unblind

    primary = analysis.run(blind=blind, seed=args.seed, n_boot=args.n_boot)
    panel, _ = analysis.apply_registered_exclusions(load_panel())
    if blind and panel.n_tasks:
        panel = analysis._permute_outcomes(panel, args.seed)
    result = {
        "blind": blind,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary": primary,
        "report": report.registered_report(panel, n_boot=args.n_boot,
                                           reliabilities=reliability_report()),
        "h1": h1.run(blind=blind, seed=args.seed, n_boot=args.n_boot),
        "not_yet_implemented": NOT_YET_IMPLEMENTED,
    }
    result = _clean(result)
    print(("BLIND -- outcomes permuted; every number below is meaningless by design"
           if blind else "UNBLINDED"))
    print(f"task-days {primary.get('n_tasks')}  models {primary.get('n_models')}  "
          f"excluded {primary.get('models_excluded')}")
    for warning in primary.get("warnings", []):
        print(f"  ! {warning}")
    print("not yet implemented:", "; ".join(NOT_YET_IMPLEMENTED))
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(f"written {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Cost accounting with a hard, code-enforced spending cap.

The budget is $200 and there is no more where that came from, so the cap is an
invariant in code rather than a number in a spreadsheet. Every call is priced
BEFORE it is made; if it would breach the cap the ledger raises and the call
never happens.

This exists because the realistic way to lose the budget is not a wrong price
estimate -- it is a retry loop, or a script accidentally launched twice, quietly
draining the account overnight while nobody is watching.
"""

import json
import os
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


class BudgetExceeded(RuntimeError):
    """Raised when a call would push cumulative spend past the cap."""


@dataclass(frozen=True)
class Price:
    """USD per million tokens, plus cache-read and batch multipliers.

    cached_input_mult: cache reads typically bill at ~0.1x the input rate.
    batch_mult:        batch APIs typically bill at 0.5x.
    """

    input_per_mtok: float
    output_per_mtok: float
    cached_input_mult: float = 0.10
    batch_mult: float = 0.50

    def estimate(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        batch: bool = False,
    ) -> float:
        """Cost in USD for one call."""
        if cached_input_tokens > input_tokens:
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        fresh = input_tokens - cached_input_tokens
        cost = (
            fresh / 1e6 * self.input_per_mtok
            + cached_input_tokens / 1e6 * self.input_per_mtok * self.cached_input_mult
            + output_tokens / 1e6 * self.output_per_mtok
        )
        if batch:
            cost *= self.batch_mult
        return cost


@dataclass
class Entry:
    ts: str
    model: str
    arm: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    batch: bool
    usd: float


class Ledger:
    """Append-only spend ledger with a global cap and per-arm sub-caps.

    Thread-safe: the collector runs calls concurrently, so reserve/commit must be
    atomic or two calls can each pass the check and jointly breach the cap.
    """

    def __init__(
        self,
        path: Path,
        cap_usd: float = 200.0,
        arm_caps: Optional[Dict[str, float]] = None,
    ) -> None:
        self.path = Path(path)
        self.cap_usd = float(cap_usd)
        self.arm_caps = dict(arm_caps or {})
        self._lock = threading.Lock()
        self._spent = 0.0
        self._arm_spent: Dict[str, float] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._replay()

    def _replay(self) -> None:
        """Rebuild running totals from the log so restarts cannot double-spend."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    # A torn final line from an interrupted write. Skip it; the
                    # lost cent is preferable to refusing to start.
                    continue
                usd = float(rec.get("usd", 0.0))
                arm = rec.get("arm", "unknown")
                self._spent += usd
                self._arm_spent[arm] = self._arm_spent.get(arm, 0.0) + usd

    @property
    def spent(self) -> float:
        with self._lock:
            return self._spent

    @property
    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self.cap_usd - self._spent)

    def arm_spent(self, arm: str) -> float:
        with self._lock:
            return self._arm_spent.get(arm, 0.0)

    def check(self, usd: float, arm: str = "unknown") -> None:
        """Raise BudgetExceeded if this spend would breach a cap. Does not record."""
        with self._lock:
            self._check_locked(usd, arm)

    def _check_locked(self, usd: float, arm: str) -> None:
        if self._spent + usd > self.cap_usd:
            raise BudgetExceeded(
                f"call would cost ${usd:.4f}; spent ${self._spent:.2f} of "
                f"${self.cap_usd:.2f} cap (${self.cap_usd - self._spent:.2f} left)"
            )
        cap = self.arm_caps.get(arm)
        if cap is not None:
            arm_total = self._arm_spent.get(arm, 0.0)
            if arm_total + usd > cap:
                raise BudgetExceeded(
                    f"call would cost ${usd:.4f}; arm {arm!r} has spent "
                    f"${arm_total:.2f} of its ${cap:.2f} cap"
                )

    def record(
        self,
        model: str,
        arm: str,
        input_tokens: int,
        output_tokens: int,
        usd: float,
        cached_input_tokens: int = 0,
        batch: bool = False,
    ) -> Entry:
        """Atomically check, append to the log, and update totals."""
        entry = Entry(
            ts=datetime.now(timezone.utc).isoformat(),
            model=model,
            arm=arm,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cached_input_tokens=int(cached_input_tokens),
            batch=bool(batch),
            usd=float(usd),
        )
        with self._lock:
            self._check_locked(usd, arm)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry)) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._spent += usd
            self._arm_spent[arm] = self._arm_spent.get(arm, 0.0) + usd
        return entry

    def summary(self) -> Dict[str, object]:
        with self._lock:
            return {
                "cap_usd": self.cap_usd,
                "spent_usd": round(self._spent, 4),
                "remaining_usd": round(max(0.0, self.cap_usd - self._spent), 4),
                "pct_used": round(100 * self._spent / self.cap_usd, 2) if self.cap_usd else 0.0,
                "by_arm": {k: round(v, 4) for k, v in sorted(self._arm_spent.items())},
            }

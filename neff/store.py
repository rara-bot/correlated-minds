"""Append-only JSONL storage for tasks, observations, and resolutions.

Design constraints, in priority order:

1. APPEND-ONLY. Records are never edited or deleted. A forecast, once written,
   is immutable. This is what makes the "we registered this before the event
   resolved" claim checkable rather than asserted -- combined with git commits,
   the file history is the evidence.

2. CRASH-SAFE. Each write is flushed and fsynced. A laptop that sleeps or a
   GitHub Action that is cancelled must not corrupt the record.

3. TOLERANT ON READ. A torn final line (interrupted write) is skipped with a
   warning rather than aborting the load. Losing one observation is acceptable;
   being unable to read 15 weeks of data is not.

4. CONTENT-ADDRESSED. Every observation carries a deterministic id derived from
   (task_id, model_key, prompt_variant, schema_version). Re-running a day is
   therefore idempotent and cannot double-bill or double-count.
"""

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

SCHEMA_VERSION = "v1"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def observation_id(
    task_id: str, model_key: str, prompt_variant: int = 0, schema: str = SCHEMA_VERSION
) -> str:
    """Deterministic id, so a repeated run overwrites nothing and adds nothing."""
    raw = f"{schema}|{task_id}|{model_key}|{prompt_variant}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass
class Task:
    """A single forecasting question, registered BEFORE its outcome is known."""

    task_id: str
    kind: str                      # macro | event | earnings | filing
    prompt: str
    asked_at: str = field(default_factory=_utcnow)
    resolves_after: Optional[str] = None
    source: str = ""
    source_ref: str = ""
    outcome_kind: str = "binary"   # binary | continuous
    market_implied: Optional[float] = None   # benchmark, when the source is a market
    state: Dict[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA_VERSION


@dataclass
class Observation:
    """One model's answer to one task."""

    obs_id: str
    task_id: str
    model_key: str
    model_id_returned: str          # what the API actually served -- drift detector
    provider: str
    prompt_variant: int
    forecast: Optional[float]       # probability in [0,1], or a continuous estimate
    direction: Optional[str]
    confidence: Optional[float]
    rationale: str = ""
    logprobs: Optional[Dict[str, float]] = None
    raw_response: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    latency_ms: int = 0
    error: Optional[str] = None
    created_at: str = field(default_factory=_utcnow)
    schema: str = SCHEMA_VERSION


@dataclass
class Resolution:
    """The realised outcome of a task, written only after it is knowable."""

    task_id: str
    outcome: float
    resolved_at: str = field(default_factory=_utcnow)
    source: str = ""
    note: str = ""
    schema: str = SCHEMA_VERSION


class JsonlStore:
    """Thread-safe append-only JSONL file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, record: Any) -> None:
        payload = asdict(record) if hasattr(record, "__dataclass_fields__") else dict(record)
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    def append_many(self, records: List[Any]) -> int:
        n = 0
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                for record in records:
                    payload = (
                        asdict(record)
                        if hasattr(record, "__dataclass_fields__")
                        else dict(record)
                    )
                    fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    n += 1
                fh.flush()
                os.fsync(fh.fileno())
        return n

    def read(self, strict: bool = False) -> Iterator[Dict[str, Any]]:
        """Yield records. Skips malformed lines unless strict=True."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    if strict:
                        raise ValueError(f"{self.path}:{lineno} malformed: {exc}") from exc
                    continue

    def read_all(self, strict: bool = False) -> List[Dict[str, Any]]:
        return list(self.read(strict=strict))

    def count(self) -> int:
        return sum(1 for _ in self.read())

    def existing_ids(self, key: str) -> Set[str]:
        """Set of values for `key` already present -- used for idempotent reruns."""
        out: Set[str] = set()
        for rec in self.read():
            value = rec.get(key)
            if value is not None:
                out.add(str(value))
        return out

    def integrity_report(self) -> Dict[str, Any]:
        """Check the file is readable and internally consistent."""
        total = 0
        malformed = 0
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    total += 1
                    try:
                        json.loads(line)
                    except json.JSONDecodeError:
                        malformed += 1
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "records": total,
            "malformed": malformed,
            "bytes": self.path.stat().st_size if self.path.exists() else 0,
        }

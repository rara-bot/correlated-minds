#!/usr/bin/env python
"""Check everything a check-in checks, fix what is safe to fix, and say who does the rest.

    ./.venv/bin/python scripts/health_check.py            # the daily check, about two minutes
    ./.venv/bin/python scripts/health_check.py --deep     # + CI's Python, future dates, lint (~20 min)
    ./.venv/bin/python scripts/health_check.py --no-fix   # report only; change nothing at all
    ./.venv/bin/python scripts/health_check.py --list     # every check, and why it exists

WHY THIS EXISTS

From 3 to 24 September the same request came again and again: "check everything,
make sure it is going well, and if anything is wrong, fix it." Every one of those
check-ins was done by hand, and nearly every one found something. A backup run
re-selected a day's questions (3 Sep). A mock run could write fabricated forecasts
into the public record (4 Sep). qwen lost whole days to one host (9 and 13 Sep).
The resolver looked stalled (16 Sep). A model was due to retire mid-study, GitHub
was removing the Node runtime and moving the Ubuntu image under the job, and the
next major version of one library would have broken every call (19 Sep). A
reporting step could discard a collected day, and packages drifted under CI
(24 Sep). On 28 Sep the 13:10 UTC run never started and the evening backup saved
the day.

This file is those check-ins written down once, so they are done the same way
every time: the commands they ran, the thresholds they applied, the findings they
learned are NOT defects, and what to do when a finding is real. HEALTH-CHECK.md is
the playbook it points into; `.claude/skills/check/SKILL.md` tells Claude how to
run it and act on what it says.

WHAT IT FIXES BY ITSELF -- only things with one right answer, all reversible:
  - brings this copy up to date with GitHub: a fast-forward, or, when commits made
    here are not on GitHub yet, replays them on top of GitHub's data commits;
  - puts back any file under data/ changed on this Mac (only the daily job writes
    the record), keeping a patch of what it removed;
  - moves stray untracked files out of data/ into .health/quarantine/;
  - prunes git's records of worktrees whose folders are gone, and removes a
    leftover ~/.local/bin link into a deleted Claude scratchpad.

WHAT IT NEVER DOES:
  - look at outcomes in any way the plan forbids. Nothing here passes --unblind,
    --publish or --evaluate, and every number it computes about the panel reads
    only which cells are filled, never an outcome (tests/test_health_check.py);
  - write to data/, push, open or close issues, touch OSF or Zenodo, or spend;
  - print a secret, or send the owner's e-mail address anywhere.

Exit status: 0 all good, 1 something needs doing soon, 2 something is urgent.
The full report is written to .health/last-report.md and .health/last-report.json.
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

try:
    import fcntl
except ImportError:                     # Windows only; this Mac and the runner have it
    fcntl = None

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neff import config  # noqa: E402

# --- where things live --------------------------------------------------------------

REPO = "rara-bot/correlated-minds"
GITHUB_API = f"https://api.github.com/repos/{REPO}"
GITHUB_WEB = f"https://github.com/{REPO}"
ZENODO_RECORD = "22220263"
ZENODO_VERSIONS = (f"https://zenodo.org/api/records/{ZENODO_RECORD}/versions"
                   "?allversions=true&size=25")   # Zenodo refuses more than 25 a page
OSF_API = "https://api.osf.io/v2"
OSF_REGISTRATION = "x6kqg"          # the registration: never edited, never withdrawn
OSF_PROJECT = "965dz"               # the project the registration was made from
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
OPENROUTER_API = "https://openrouter.ai/api/v1"
PYTHON_VERSIONS_MANIFEST = ("https://raw.githubusercontent.com/actions/python-versions/"
                            "main/versions-manifest.json")
RETIREMENT_PAGES = {
    "anthropic": "https://platform.claude.com/docs/en/about-claude/model-deprecations",
    "openai": "https://developers.openai.com/api/docs/deprecations",
    "google": "https://ai.google.dev/gemini-api/docs/deprecations",
    "azure": ("https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/"
              "model-retirement-schedule"),
}
# Deliberately NOT config.USER_AGENT: that one carries the owner's e-mail for SEC,
# which requires it. Nothing this file calls needs it, so nothing gets it.
AGENT = "correlated-minds-health-check/1 (+https://github.com/rara-bot/correlated-minds)"
BROWSER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                 "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")

CORE_RECORD = ("observations", "tasks", "resolutions", "ledger")
DAILY_WORKFLOW = "daily-collection"
TESTS_WORKFLOW = "tests"
COLLECTOR = "neff-collector"        # the author of every daily data commit
CODE_PATHS = ("neff/", "scripts/", "tests/", ".github/", "requirements.txt", "constraints.txt")

# Arguments that would make a script look at outcomes. The runner refuses them.
FORBIDDEN_ARGS = ("--unblind", "--publish", "--evaluate")

# Known, explained exceptions -- found once, looked into, and NOT defects. Each is
# here so no check-in raises it again. HEALTH-CHECK.md "Known, not problems".
KNOWN_RECORD_COMMITS = {
    "e433cea": ("verification receipts (ledger rows on the pilot arm) committed with the "
                "OSF promotion on 2026-09-01, before the first collection"),
}
KNOWN_TASK_DAY_COUNTS = {
    "2026-09-03": "30 questions, not 25: the backup run re-selected that day (deviation 2)",
}
KNOWN_LOW_LOGPROBS = {
    "deepseek": "most of its hosts send no logprobs, and the two that do send broken ones "
                "(deviations 12 and 19); the logprob check runs without it",
}
# Models whose logprobs depend on which host OpenRouter picks: some hosts send none
# (Cloudflare for llama, deviation 12), so a share in this band is routing, not a fault.
PARTIAL_LOGPROBS_FLOOR = {"llama": 0.60}
PILOT_TASKS_WITHOUT_ARM = 36        # pre-registration pilot rows, from before the arm label

# Anthropic: "at least 60 days' notice before model retirement for publicly released
# models" (model-deprecations page, read 2026-09-29).
ANTHROPIC_NOTICE_DAYS = 60

# Region 6 (ncsef.org/fairs, read 2026-09-22). Seniors compete on the first date.
FAIR_DATES = {"NCSEF Region 6 fair (grades 9-12, virtual)": "2027-01-28"}

# Checks that need judgement and a web search, done by Claude on a cadence, and
# marked done with `--ack KEY`. Their cadence is in days.
WEB_CHECKS = {
    "web.calendar": (
        7, "US government funding and the release calendar the questions depend on",
        "Search for news of a federal shutdown or a lapse in appropriations, and read "
        "bls.gov/schedule for the next three weeks. A shutdown delays payrolls, CPI "
        "and JOLTS, and the Week-5 calibration waits on the 2 Oct payrolls release."),
    "web.fair": (
        14, "NCSEF Region 6: registration deadline and rules",
        "Read ncsef.org/fairs and the UNC Charlotte Region 6 page. If a registration "
        "deadline or a paperwork rule has appeared, update SUBMISSION-TARGETS.md and "
        "tell the student."),
    "web.github": (
        14, "GitHub Actions changes that land before the freeze",
        "Skim github.blog/changelog for runner images (ubuntu-24.04), Node versions, "
        "and scheduled-workflow behaviour, for anything dated before 2026-12-11."),
}

# Acknowledgements a person gives, and how long each lasts (None: until revoked).
ACK_KEYS = {
    "you.isef": (None, "ISEF Forms 1, 1A, 1B, 2A and your own Research Plan are done"),
    "you.fair_ai_answer": (None, "the fair's answer on AI use is saved in writing"),
    "you.github_token": (None, "the token or key found in the prompt log was revoked and replaced"),
    "you.prompt_log_backup": (7, "the prompt log was copied somewhere safe"),
    "you.addendum": (None, "Addendum 1 is posted (use only if the automatic check misses it)"),
}
ACK_KEYS.update({k: (v[0], v[1]) for k, v in WEB_CHECKS.items()})

VENDOR_OF_PROVIDER = {"anthropic": "anthropic", "openai": "openai", "google": "google",
                      "openrouter": "openrouter", "openrouter_azure": "openrouter"}
VENDOR_NAMES = {"anthropic": "Anthropic (Claude Console)", "openai": "OpenAI",
                "google": "Google AI Studio", "openrouter": "OpenRouter"}
VENDOR_TOPUP = {
    "anthropic": ["Open platform.claude.com -- the Claude Console, not claude.ai.",
                  "Billing -> Buy credits. Keep auto-reload off."],
    "openai": ["Open platform.openai.com -> the gear icon (Settings) -> Billing.",
               "Add to credit balance. Keep auto-recharge off."],
    "google": ["Open aistudio.google.com -> Billing (left menu).",
               "The 'Available credits' card is the balance; add credits there (minimum $5)."],
    "openrouter": ["Open openrouter.ai -> Credits -> Add credits. Keep auto top-up off."],
}
VENDOR_SECRET = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
                 "google": "GOOGLE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}

KEY_PATTERNS = [
    ("Anthropic key", r"sk-ant-[A-Za-z0-9_\-]{40,}"),
    ("OpenAI key", r"sk-proj-[A-Za-z0-9_\-]{40,}"),
    ("OpenRouter key", r"sk-or-v1-[A-Za-z0-9_\-]{40,}"),
    ("Google key", r"AQ\.[A-Za-z0-9_\-]{30,}"),
    ("Google key (legacy)", r"AIza[A-Za-z0-9_\-]{30,}"),
    ("GitHub token", r"ghp_[A-Za-z0-9]{30,}"),
    ("GitHub fine-grained token", r"github_pat_[A-Za-z0-9_]{50,}"),
]
_KEY_RE = re.compile("|".join(f"(?P<k{i}>{p})" for i, (_, p) in enumerate(KEY_PATTERNS)))
# A transcript also holds base64 -- the signature of every thinking block, screenshots,
# pasted images -- thousands of characters at a time, where four of them spell "AIza"
# now and then (30 Sep: one thinking signature did). A key someone pasted or a tool
# printed never starts in the middle of such a run, so the prompt log is read with a
# boundary in front. Committed files keep the broad patterns, exactly as
# tests/test_no_secrets_committed.py has them.
_LOG_KEY_RE = re.compile(r"(?<![A-Za-z0-9+/])(?:" + _KEY_RE.pattern + ")")


def _key_kind(match: "re.Match") -> str:
    return KEY_PATTERNS[int(match.lastgroup[1:])][0]


# --- what a finding is ----------------------------------------------------------------
#
#   ok      checked, fine                    fixed   this run fixed it by itself
#   info    worth knowing, nothing to do     watch   fine now, heading somewhere
#   known   looks wrong, is not (explained)  claude  Claude should change something
#   you     only the student can do it       error   the check itself could not run
#   skip    not run this time (--offline, --quick, not --deep)

OK, INFO, KNOWN, FIXED, WATCH, CLAUDE, YOU, ERROR, SKIP = (
    "ok", "info", "known", "fixed", "watch", "claude", "you", "error", "skip")
SEVERITIES = ("low", "medium", "high", "critical")
_RANK = {s: i for i, s in enumerate(SEVERITIES)}
ACTIONABLE = (CLAUDE, YOU, ERROR)


@dataclass
class Finding:
    status: str
    summary: str
    severity: str = "low"
    detail: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    due: Optional[str] = None
    playbook: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    check: str = ""
    group: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Check:
    id: str
    group: str
    title: str
    fn: Callable[["Ctx"], Any]
    network: bool = False
    deep: bool = False
    origin: str = ""


CHECKS: List[Check] = []

GROUPS = [
    ("repo", "Your copy of the repository"),
    ("ci", "GitHub Actions"),
    ("record", "The daily record"),
    ("panel", "Coverage and the panel"),
    ("resolve", "Settlements"),
    ("plan", "The registered plan and its public copies"),
    ("code", "Code and tests"),
    ("money", "Budget and API balances"),
    ("vendors", "Models and hosts"),
    ("dates", "Dates"),
    ("you", "Only you can do these"),
    ("local", "This Mac"),
    ("deep", "Deep checks (--deep)"),
]
GROUP_TITLES = dict(GROUPS)


def check(id: str, title: str, *, network: bool = False, deep: bool = False, origin: str = ""):
    group = id.split(".", 1)[0]
    if group not in GROUP_TITLES:
        raise ValueError(f"unknown group for {id}")

    def register(fn):
        CHECKS.append(Check(id, group, title, fn, network, deep, origin))
        return fn
    return register


# --- small helpers --------------------------------------------------------------------

@dataclass
class Proc:
    rc: int
    out: str = ""
    err: str = ""
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.rc == 0


def _decode(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _run(argv: Sequence[str], cwd: Path, timeout: float = 120, env: Optional[dict] = None) -> Proc:
    start = time.time()
    try:
        p = subprocess.run([str(a) for a in argv], cwd=str(cwd), capture_output=True,
                           timeout=timeout, env=env)
        return Proc(p.returncode, _decode(p.stdout), _decode(p.stderr), time.time() - start)
    except subprocess.TimeoutExpired as exc:
        return Proc(124, _decode(exc.stdout), f"timed out after {timeout:.0f}s", time.time() - start)
    except OSError as exc:
        return Proc(127, "", str(exc), time.time() - start)


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _tail(text: str, n: int = 12) -> List[str]:
    lines = [ln.rstrip() for ln in _strip_ansi(text).splitlines() if ln.strip()]
    return lines[-n:]


def _quiet_env(**extra: str) -> dict:
    env = dict(os.environ)
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env.setdefault(var, "2")
    env["NO_COLOR"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def _ts(value: Any) -> Optional[datetime]:
    """Parse the ISO-8601 variants this project meets. Naive means UTC."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip().replace("‑", "-").replace("‐", "-")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = re.match(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)(\.\d+)?(.*)$", s)
    if m:
        frac = (m.group(2) or "")
        if frac:
            frac = (frac + "000000")[:7]
        s = m.group(1) + frac + m.group(3)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        try:
            d = datetime.fromisoformat(s[:10])
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _day(value: Any) -> Optional[date]:
    t = _ts(value)
    return t.date() if t else None


def _et(when: datetime) -> str:
    """The same instant on the clock in Charlotte."""
    try:
        from zoneinfo import ZoneInfo
        local = when.astimezone(ZoneInfo("America/New_York"))
    except Exception:                                              # noqa: BLE001
        local = when.astimezone(timezone(timedelta(hours=-4)))
    return local.strftime("%-I:%M %p ET")


def _when(when: datetime) -> str:
    return f"{when:%a %-d %b}, {when:%H:%M} UTC ({_et(when)})"


def _plural(n: int, word: str, plural: Optional[str] = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _shown(ctx: "Ctx", path: Path) -> str:
    try:
        return str(Path(path).relative_to(ctx.root))
    except ValueError:
        return str(path)


def _venv_python(root: Path) -> str:
    for candidate in (root / ".venv" / "bin" / "python", root / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


class Git:
    def __init__(self, root: Path):
        self.root = Path(root)

    def __call__(self, *args: str, timeout: float = 60) -> Proc:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_EDITOR="true", GIT_PAGER="cat",
                   GIT_OPTIONAL_LOCKS="0")
        return _run(["git", *args], self.root, timeout=timeout, env=env)

    def out(self, *args: str, timeout: float = 60) -> str:
        p = self(*args, timeout=timeout)
        return p.out.strip() if p.ok else ""


@dataclass
class Resp:
    status: int
    text: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        return json.loads(self.text)


class Http:
    """GET, with a timeout, never raising. Replaced by a fake in the tests."""

    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout

    def get(self, url: str, headers: Optional[dict] = None, timeout: Optional[float] = None) -> Resp:
        hdrs = {"User-Agent": AGENT}
        hdrs.update(headers or {})
        try:
            import httpx
        except ImportError:                                            # pragma: no cover
            return self._urllib(url, hdrs, timeout)
        try:
            r = httpx.get(url, headers=hdrs, timeout=timeout or self.timeout, follow_redirects=True)
            return Resp(r.status_code, r.text, {k.lower(): v for k, v in r.headers.items()})
        except Exception as exc:                                       # noqa: BLE001
            return Resp(0, "", {}, f"{type(exc).__name__}: {exc}"[:300])

    def _urllib(self, url, hdrs, timeout):                             # pragma: no cover
        import urllib.error
        import urllib.request
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                return Resp(r.status, r.read().decode("utf-8", "replace"),
                            {k.lower(): v for k, v in r.headers.items()})
        except urllib.error.HTTPError as exc:
            return Resp(exc.code, exc.read().decode("utf-8", "replace"), {})
        except Exception as exc:                                       # noqa: BLE001
            return Resp(0, "", {}, f"{type(exc).__name__}: {exc}"[:300])


class Background:
    """Slow subprocesses started early and collected by the checks that need them."""

    def __init__(self):
        self._jobs: Dict[str, Any] = {}

    def start(self, name: str, argv: Sequence[str], cwd: Path, env: Optional[dict] = None,
              timeout: float = 900) -> None:
        out, err = tempfile.TemporaryFile(), tempfile.TemporaryFile()
        try:
            p = subprocess.Popen([str(a) for a in argv], cwd=str(cwd), stdout=out, stderr=err, env=env)
        except OSError as exc:
            self._jobs[name] = Proc(127, "", str(exc))
            return
        self._jobs[name] = (p, out, err, time.time(), timeout)

    def started(self, name: str) -> bool:
        return name in self._jobs

    def wait(self, name: str) -> Optional[Proc]:
        job = self._jobs.get(name)
        if job is None or isinstance(job, Proc):
            return job
        p, out, err, t0, timeout = job
        try:
            rc = p.wait(timeout=max(1.0, timeout - (time.time() - t0)))
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            rc = 124
        out.seek(0)
        err.seek(0)
        result = Proc(rc, _decode(out.read()), _decode(err.read()), time.time() - t0)
        out.close()
        err.close()
        self._jobs[name] = result
        return result

    def stop_all(self) -> None:
        for job in self._jobs.values():
            if isinstance(job, tuple) and job[0].poll() is None:
                job[0].kill()


# --- the context every check gets -----------------------------------------------------

class Ctx:
    def __init__(self, root: Path = ROOT, *, fix: bool = True, offline: bool = False,
                 deep: bool = False, quick: bool = False, now: Optional[datetime] = None,
                 http: Optional[Http] = None, python: Optional[str] = None,
                 home: Optional[Path] = None, state_dir: Optional[Path] = None):
        self.root = Path(root)
        self.fix = fix
        self.offline = offline
        self.deep = deep
        self.quick = quick
        self.now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.today = self.now.date()
        self.http = http or Http()
        self.python = python or _venv_python(self.root)
        self.home = Path(home) if home else Path.home()
        self.git = Git(self.root)
        self.state_dir = Path(state_dir) if state_dir else self.root / ".health"
        self.state = _load_state(self.state_dir)
        self._state_base = _plain(self.state)      # what was on disk; a save writes only the difference
        self.results: Dict[str, List[Finding]] = {}
        self.flags: Dict[str, Any] = {}
        self.facts: Dict[str, Any] = {}
        self.bg = Background()
        self._data: Dict[str, Tuple[List[dict], List[int]]] = {}
        self._memo: Dict[str, Any] = {}
        self._tmp: Optional[Path] = None

    # scratch space for this run, deleted at the end
    @property
    def tmp(self) -> Path:
        if self._tmp is None:
            self._tmp = Path(tempfile.mkdtemp(prefix="health-"))
        return self._tmp

    def cleanup(self) -> None:
        self.bg.stop_all()
        if self._tmp is not None:
            shutil.rmtree(self._tmp, ignore_errors=True)

    def stamp(self) -> str:
        return self.now.strftime("%Y%m%dT%H%M%SZ")

    # the record
    def path(self, name: str) -> Path:
        return self.root / "data" / f"{name}.jsonl"

    def _load(self, name: str) -> Tuple[List[dict], List[int]]:
        if name not in self._data:
            rows, bad = [], []
            p = self.path(name)
            if p.exists():
                with p.open(encoding="utf-8") as fh:
                    for n, line in enumerate(fh, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            bad.append(n)
            self._data[name] = (rows, bad)
        return self._data[name]

    def rows(self, name: str) -> List[dict]:
        return self._load(name)[0]

    def bad_lines(self, name: str) -> List[int]:
        return self._load(name)[1]

    def invalidate(self) -> None:
        self._data.clear()
        self._memo.clear()

    def memo(self, key: str, make: Callable[[], Any]) -> Any:
        if key not in self._memo:
            self._memo[key] = make()
        return self._memo[key]

    def task_index(self) -> Dict[str, dict]:
        return self.memo("task_index", lambda: {str(t.get("task_id")): t for t in self.rows("tasks")})

    @staticmethod
    def task_day(task: dict) -> str:
        return str(task.get("asked_at") or (task.get("state") or {}).get("asked_on") or "")[:10]

    def primary_tasks(self) -> List[dict]:
        return self.memo("primary_tasks", lambda: [
            t for t in self.rows("tasks") if t.get("arm") == config.PRIMARY_ARM])

    def primary_obs(self) -> List[dict]:
        """Answers to primary-arm questions, labelled by the day their question was asked."""
        def make():
            index = self.task_index()
            out = []
            for o in self.rows("observations"):
                t = index.get(str(o.get("task_id")))
                if t is None or t.get("arm") != config.PRIMARY_ARM:
                    continue
                out.append(dict(o, _day=self.task_day(t) or str(o.get("created_at", ""))[:10]))
            return out
        return self.memo("primary_obs", make)

    def days_collected(self) -> List[str]:
        return self.memo("days", lambda: sorted({o["_day"] for o in self.primary_obs() if o["_day"]}))

    def resolved_ids(self) -> set:
        return self.memo("resolved", lambda: {str(r.get("task_id")) for r in self.rows("resolutions")})

    def ack(self, key: str) -> Optional[dict]:
        a = (self.state.get("acks") or {}).get(key)
        if not a:
            return None
        days = ACK_KEYS.get(key, (None, ""))[0]
        at = _ts(a.get("at"))
        if days is not None and (at is None or self.now - at > timedelta(days=days)):
            return None
        return a


# --- state that lives between runs (.health/, never committed) --------------------------

def _ensure_state_dir(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    guard = state_dir / ".gitignore"
    if not guard.exists():
        # Everything in here is private to this Mac -- balances, a quarantine, patches
        # of what was restored. A directory that ignores itself cannot be committed by
        # a `git add -A`, whatever the root .gitignore says.
        guard.write_text("# written by scripts/health_check.py; nothing here is committed\n*\n",
                         encoding="utf-8")


def _read_state(state_dir: Path) -> Optional[dict]:
    """The state on disk: {} when there is none yet, None when it cannot be read."""
    path = state_dir / "state.json"
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return state if isinstance(state, dict) else None


def _load_state(state_dir: Path) -> dict:
    return _read_state(state_dir) or {}


def _plain(value: Any) -> Any:
    """`value` as it reads back from state.json."""
    return json.loads(json.dumps(value, default=str))


_GONE = object()


def _changes(base: Any, ours: Any, path: Tuple[str, ...] = ()) -> Iterator[Tuple[Tuple[str, ...], Any]]:
    """Each leaf this run set, changed or removed, relative to what it loaded."""
    if isinstance(ours, dict):
        was = base if isinstance(base, dict) else {}
        for key, value in ours.items():
            yield from _changes(was.get(key, _GONE), value, path + (key,))
        for key in was.keys() - ours.keys():
            yield path + (key,), _GONE
    elif base != ours:
        yield path, ours


def _apply_changes(state: dict, changes: Iterable[Tuple[Tuple[str, ...], Any]]) -> dict:
    for path, value in changes:
        node = state
        for key in path[:-1]:
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        if value is _GONE:
            node.pop(path[-1], None)
        else:
            node[path[-1]] = value
    return state


@contextmanager
def _flock(path: Path, wait: bool = True) -> Iterator[bool]:
    """An exclusive lock between processes; yields False when `wait` is off and another holds it."""
    _ensure_state_dir(path.parent)
    with path.open("a", encoding="utf-8") as fh:
        got = True
        if fcntl is not None:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            except OSError:
                got = False
        yield got                        # closing the file releases the lock


def _save_state(ctx: Ctx) -> None:
    """Write what this run changed -- and only that -- onto the state as it is on disk now.

    A --deep run takes twenty minutes, and the procedure has acknowledgements and
    balances recorded while it runs. Writing back the whole state the run loaded would
    silently undo them, so its own changes, leaf by leaf, are replayed onto a fresh read
    under a lock, and everything another run wrote meanwhile is kept.
    """
    ours = _plain(ctx.state)
    with _flock(ctx.state_dir / "state.lock"):
        on_disk = _read_state(ctx.state_dir)
        merged = _apply_changes(on_disk if on_disk is not None else _plain(ctx._state_base),
                                _changes(ctx._state_base, ours))
        tmp = ctx.state_dir / f"state.json.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(ctx.state_dir / "state.json")
    ctx.state, ctx._state_base = merged, _plain(merged)


def _seen(ctx: Ctx) -> dict:
    return ctx.state.setdefault("seen", {})


# --- running a script, never one that unblinds ---------------------------------------------

def _script(ctx: Ctx, name: str, *args: str, cwd: Optional[Path] = None, timeout: float = 300,
            background: Optional[str] = None) -> Optional[Proc]:
    bad = [a for a in args if a in FORBIDDEN_ARGS]
    if bad:
        raise RuntimeError(f"refusing to run {name} {' '.join(bad)}: this check never unblinds "
                           f"and never publishes (PREREGISTRATION.md 11, deviations 17 and 21)")
    argv = [ctx.python, str(ctx.root / "scripts" / name), *args]
    if background:
        ctx.bg.start(background, argv, cwd or ctx.root, env=_quiet_env(), timeout=timeout)
        return None
    return _run(argv, cwd or ctx.root, timeout=timeout, env=_quiet_env())


def _pytest_summary(text: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    lines = [ln for ln in _strip_ansi(text).splitlines() if re.search(r"\b(passed|failed|error)", ln)]
    last = lines[-1] if lines else ""
    for n, what in re.findall(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)", last):
        counts["error" if what.startswith("error") else what] = int(n)
    return counts


def _failing_tests(text: str) -> List[str]:
    return [ln.split(" - ")[0].strip() for ln in _strip_ansi(text).splitlines()
            if ln.startswith(("FAILED ", "ERROR "))]


# ======================================================================================
# repo -- your copy of the repository
# ======================================================================================

@check("repo.git", "This folder is the study's git repository, on main",
       origin="every check-in started from `git status` and `git log`")
def _repo_git(ctx: Ctx):
    top = ctx.git.out("rev-parse", "--show-toplevel")
    if not top:
        ctx.flags["no_git"] = True
        return Finding(ERROR, "this folder is not a git repository, so nothing about GitHub can "
                       "be checked", severity="high", playbook="repo.git")
    branch = ctx.git.out("rev-parse", "--abbrev-ref", "HEAD")
    remote = ctx.git.out("remote", "get-url", "origin")
    ctx.facts["branch"] = branch
    out = []
    if REPO not in remote:
        out.append(Finding(WATCH, f"'origin' is {remote or 'not set'}, not github.com/{REPO}",
                           severity="medium", playbook="repo.git"))
    if branch != "main":
        out.append(Finding(CLAUDE, f"this copy is on '{branch}', not main -- everything the "
                           f"daily job runs is on main", severity="medium", playbook="repo.git",
                           steps=["Finish or set aside the work on that branch, then: git switch main"]))
    return out or Finding(OK, "on main, tracking GitHub")


@check("repo.fetch", "GitHub can be reached, and this copy knows GitHub's latest", network=True,
       origin="09-19, 09-22, 09-23: the daily job commits on GitHub, so a local copy falls behind")
def _repo_fetch(ctx: Ctx):
    if ctx.flags.get("no_git"):
        return None
    p = ctx.git("fetch", "--quiet", "origin", timeout=120)
    if p.ok:
        return Finding(OK, "fetched GitHub's latest")
    ctx.flags["fetch_failed"] = True
    head = ctx.root / ".git" / "FETCH_HEAD"
    age = ""
    if head.exists():
        age = f", last fetched {datetime.fromtimestamp(head.stat().st_mtime, timezone.utc):%d %b %H:%M} UTC"
    why = (_tail(p.err, 1) or ["no reason given"])[0]
    return Finding(WATCH, f"could not reach GitHub ({why}); working from this copy's last "
                   f"fetch{age}", severity="medium", playbook="repo.fetch")


def _only_verification_receipts(ctx: Ctx, path: str) -> bool:
    """Is the local change to `path` appended receipts of a live verify run, and nothing else?"""
    if path not in ("data/ledger.jsonl", "data/verification.jsonl"):
        return False
    committed = ctx.git("show", f"HEAD:{path}")
    try:
        local = (ctx.root / path).read_text(encoding="utf-8")
    except OSError:
        return False
    if not committed.ok or not local.startswith(committed.out):
        return False
    added = [ln for ln in local[len(committed.out):].splitlines() if ln.strip()]
    if not added:
        return False
    for line in added:
        try:
            row = json.loads(line)
        except ValueError:
            return False
        if path.endswith("ledger.jsonl") and row.get("arm") == config.PRIMARY_ARM:
            return False
    return True


def _porcelain(ctx: Ctx) -> List[Tuple[str, str]]:
    p = ctx.git("status", "--porcelain=v1", "--untracked-files=all")
    entries = []
    for line in p.out.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path.startswith(".health/"):
            continue
        entries.append((code, path))
    return entries


@check("repo.worktree", "No uncommitted work -- and nothing written into data/ on this Mac",
       origin="09-16: a local run of a daily step appended rows; only the daily job may write "
              "the record, so they were reverted")
def _repo_worktree(ctx: Ctx):
    if ctx.flags.get("no_git"):
        return None
    entries = _porcelain(ctx)
    data_changed = [p for c, p in entries if p.startswith("data/") and c != "??"]
    data_untracked = [p for c, p in entries if p.startswith("data/") and c == "??"]
    code = [p for c, p in entries if not p.startswith("data/") and p.startswith(CODE_PATHS)]
    other = [p for c, p in entries if not p.startswith("data/") and not p.startswith(CODE_PATHS)]
    out: List[Finding] = []

    receipts = [p for p in data_changed if _only_verification_receipts(ctx, p)]
    restore = [p for p in data_changed if p not in receipts]
    if receipts:
        out.append(Finding(
            CLAUDE, "a live model check on this Mac added receipts to " + ", ".join(receipts),
            severity="medium", playbook="repo.worktree",
            detail=["They record real spend on the pilot arm, so they are not thrown away."],
            steps=["Commit them with a message saying which verify run made them (precedent: "
                   "e433cea), or discard them if that run should not count."]))
    if restore:
        if ctx.fix:
            _ensure_state_dir(ctx.state_dir)
            backup = ctx.state_dir / "backups" / f"{ctx.stamp()}-data.patch"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(ctx.git("diff", "HEAD", "--binary", "--", *restore).out, encoding="utf-8")
            p = ctx.git("restore", "--source=HEAD", "--staged", "--worktree", "--", *restore)
            if not p.ok:
                p = ctx.git("checkout", "HEAD", "--", *restore)
            left = [q for c, q in _porcelain(ctx) if q in restore]
            if p.ok and not left:
                ctx.invalidate()
                out.append(Finding(
                    FIXED, f"put back {_plural(len(restore), 'file')} in data/ that had been changed "
                    f"on this Mac: {', '.join(restore)}", playbook="repo.worktree",
                    detail=["Only the daily job writes the record; a row written here is not "
                            "evidence of anything.",
                            f"What was removed is saved in {_shown(ctx, backup)}."]))
            else:
                out.append(Finding(CLAUDE, "could not put back " + ", ".join(restore),
                                   severity="high", playbook="repo.worktree",
                                   detail=_tail(p.err, 4)))
        else:
            out.append(Finding(CLAUDE, "data/ was changed on this Mac: " + ", ".join(restore),
                               severity="high", playbook="repo.worktree",
                               steps=["Run the check without --no-fix to put them back, or: "
                                      "git restore --source=HEAD --staged --worktree -- data/"]))
    if data_untracked:
        if ctx.fix:
            _ensure_state_dir(ctx.state_dir)
            dest_root = ctx.state_dir / "quarantine" / ctx.stamp()
            moved = []
            for rel in data_untracked:
                dest = dest_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(ctx.root / rel), str(dest))
                moved.append(rel)
            ctx.invalidate()
            out.append(Finding(FIXED, f"moved {_plural(len(moved), 'stray file')} out of data/: "
                               + ", ".join(moved), playbook="repo.worktree",
                               detail=[f"They are in {_shown(ctx, dest_root)}. Files in data/ that GitHub "
                                       "does not have make the Week-5 publisher refuse to run."]))
        else:
            out.append(Finding(CLAUDE, "files in data/ that are not part of GitHub's record: "
                               + ", ".join(data_untracked), severity="medium", playbook="repo.worktree"))
    if code:
        out.append(Finding(
            CLAUDE, f"uncommitted code changes: {', '.join(code[:8])}"
            + (f" and {len(code) - 8} more" if len(code) > 8 else ""),
            severity="medium", playbook="repo.worktree",
            detail=["GitHub never runs code that is not committed and pushed, and the Week-5 "
                    "publisher refuses to run while code is uncommitted."],
            steps=["Finish, test (full suite) and commit them -- or discard them."]))
    if other:
        out.append(Finding(INFO, "uncommitted changes outside the code: " + ", ".join(other[:8]),
                           playbook="repo.worktree"))
    return out or Finding(OK, "nothing uncommitted, and data/ matches the committed record")


@check("repo.sync", "This copy has everything GitHub has, and GitHub has everything this copy has",
       origin="09-19 to 09-24 pulled before reading data/; on 09-29 this copy had diverged "
              "(1 local commit, 7 data commits on GitHub), which `git pull --ff-only` cannot fix")
def _repo_sync(ctx: Ctx):
    if ctx.flags.get("no_git") or ctx.facts.get("branch") not in (None, "main"):
        return None
    if not ctx.git.out("rev-parse", "--verify", "--quiet", "origin/main"):
        return Finding(ERROR, "this copy has no origin/main to compare with", severity="medium",
                       playbook="repo.sync")

    def counts() -> Tuple[int, int]:
        parts = ctx.git.out("rev-list", "--left-right", "--count", "origin/main...HEAD").split()
        return (int(parts[0]), int(parts[1])) if len(parts) == 2 else (0, 0)

    behind, ahead = counts()
    stale = " (GitHub was unreachable, so this is as of the last fetch)" if ctx.flags.get("fetch_failed") else ""
    out: List[Finding] = []

    if behind and not ahead:
        if not ctx.fix:
            out.append(Finding(CLAUDE, f"this copy is {_plural(behind, 'commit')} behind GitHub{stale}; "
                               "everything below reads the old record", severity="medium",
                               playbook="repo.sync", steps=["git pull --ff-only"]))
        else:
            p = ctx.git("merge", "--ff-only", "--quiet", "origin/main", timeout=120)
            if p.ok:
                ctx.invalidate()
                out.append(Finding(FIXED, f"brought in {_plural(behind, 'new commit')} from GitHub{stale}",
                                   playbook="repo.sync",
                                   detail=["The daily job commits the record on GitHub; this copy "
                                           "reads it only after pulling."]))
            else:
                out.append(Finding(CLAUDE, "could not fast-forward to GitHub", severity="high",
                                   playbook="repo.sync", detail=_tail(p.err, 4)))

    elif behind and ahead:
        local = ctx.git.out("log", "--format=%h %s", "origin/main..HEAD").splitlines()
        touches_data = ctx.git.out("diff", "--name-only", "origin/main...HEAD", "--", "data/").split()
        dirty = [p for c, p in _porcelain(ctx) if c != "??"]
        if touches_data:
            out.append(Finding(CLAUDE, f"{_plural(ahead, 'local commit')} {'changes' if ahead == 1 else 'change'} "
                               f"data/ ({', '.join(touches_data)}) -- the record is written only by the "
                               "daily job, so they are not replayed", severity="high", playbook="repo.sync",
                               detail=local))
        elif dirty:
            out.append(Finding(CLAUDE, f"this copy and GitHub have both moved on ({ahead} here, {behind} on "
                               "GitHub), and uncommitted changes stop them being joined",
                               severity="medium", playbook="repo.sync", detail=dirty[:8]))
        elif not ctx.fix:
            out.append(Finding(CLAUDE, f"this copy and GitHub have both moved on: {ahead} commit(s) here, "
                               f"{behind} on GitHub{stale}", severity="medium", playbook="repo.sync",
                               steps=["git rebase origin/main   # replays the local commits on top"]))
        else:
            old = ctx.git.out("rev-parse", "--short", "HEAD")
            p = ctx.git("rebase", "origin/main", timeout=180)
            if p.ok:
                new = ctx.git.out("rev-parse", "--short", "HEAD")
                ctx.invalidate()
                ctx.facts["rebased"] = {"from": old, "to": new}
                out.append(Finding(
                    FIXED, f"joined this copy to GitHub: took GitHub's {_plural(behind, 'new commit')} and "
                    f"replayed {_plural(ahead, 'local commit')} on top{stale}", playbook="repo.sync",
                    detail=[f"was {old}, now {new}: the local commits keep their messages and changes, "
                            f"only their ids change. Undo with: git reset --hard {old}"],
                    data={"from": old, "to": new}))
            else:
                ctx.git("rebase", "--abort")
                out.append(Finding(CLAUDE, f"{_plural(ahead, 'local commit')} could not be replayed on top "
                                   "of GitHub's without a conflict", severity="high", playbook="repo.sync",
                                   detail=_tail(p.out + p.err, 6),
                                   steps=["Nothing was changed (the attempt was undone). By hand: "
                                          "git rebase origin/main, resolve, git rebase --continue."]))
        behind, ahead = counts()

    ctx.facts["unpushed_commits"] = ahead
    ctx.facts["behind_github"] = behind
    if ahead and not behind:
        local = ctx.git.out("log", "--format=%h %s", "origin/main..HEAD").splitlines()
        code = sorted(set(ctx.git.out("diff", "--name-only", "origin/main...HEAD", "--", *CODE_PATHS).split()))
        out.append(Finding(
            YOU, f"{_plural(len(local), 'commit')} made on this Mac {'is' if len(local) == 1 else 'are'} not on "
            "GitHub yet", severity="high" if code else "medium", playbook="repo.sync", detail=local,
            steps=["Reply \"push\" to Claude. It pushes, then watches GitHub re-run the whole test suite on "
                   "the new code (the 'tests' workflow) before the next collection.",
                   ("Until then the daily job keeps running the old version of: " + ", ".join(code[:6])
                    + (" and more" if len(code) > 6 else "")) if code else
                   "Until then GitHub does not have these commits."],
            data={"commits": local, "code_files": code}))
    if not out:
        out.append(Finding(OK, f"identical to GitHub at {ctx.git.out('rev-parse', '--short', 'HEAD')}"))
    return out


@check("repo.branches", "No stale worktrees or forgotten branches",
       origin="09-13 and 09-19 found a leftover worktree and three merged branches")
def _repo_branches(ctx: Ctx):
    if ctx.flags.get("no_git"):
        return None
    out: List[Finding] = []
    listing = ctx.git.out("worktree", "list", "--porcelain")
    blocks = [b for b in listing.split("\n\n") if b.strip()]
    prunable, extra = [], []
    for i, block in enumerate(blocks):
        path = next((ln[9:] for ln in block.splitlines() if ln.startswith("worktree ")), "")
        if i == 0:
            continue
        if any(ln.startswith("prunable") for ln in block.splitlines()):
            prunable.append(path)
        else:
            extra.append(path)
    if prunable:
        if ctx.fix:
            ctx.git("worktree", "prune")
            out.append(Finding(FIXED, f"pruned git's record of {_plural(len(prunable), 'worktree')} whose "
                               "folder no longer exists", detail=prunable, playbook="repo.branches"))
        else:
            out.append(Finding(INFO, "git still lists worktrees whose folders are gone: "
                               + ", ".join(prunable), steps=["git worktree prune"], playbook="repo.branches"))
    merged, unmerged = [], []
    for b in ctx.git.out("for-each-ref", "--format=%(refname:short)", "refs/heads").split():
        if b == "main":
            continue
        if ctx.git("merge-base", "--is-ancestor", b, "main").ok:
            merged.append(b)
        else:
            n = ctx.git.out("rev-list", "--count", f"main..{b}")
            unmerged.append(f"{b} ({n} commit(s) not on main)")
    tidy = []
    if extra:
        tidy += [f"git worktree remove {p}" for p in extra]
    if merged:
        tidy.append("git branch -d " + " ".join(merged))
    if tidy:
        out.append(Finding(INFO, "tidy-up available: " + ", ".join(
            ([_plural(len(extra), "leftover worktree")] if extra else [])
            + ([_plural(len(merged), "merged branch", "merged branches")] if merged else [])),
            steps=tidy, playbook="repo.branches",
            detail=["Nothing is lost by removing them: everything in them is already on main."]))
    if unmerged:
        out.append(Finding(WATCH, "branches with work that is not on main: " + "; ".join(unmerged),
                           severity="low", playbook="repo.branches",
                           steps=["Decide for each: merge it, or delete it with git branch -D."]))
    remote = [r for r in ctx.git.out("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin").split()
              if r not in ("origin/main", "origin/HEAD", "origin")]
    if remote:
        out.append(Finding(INFO, "leftover branches on GitHub: " + ", ".join(remote),
                           playbook="repo.branches",
                           steps=[f"If they are merged, delete them on GitHub (Branches page) or ask Claude "
                                  f"to run: git push origin --delete {' '.join(r.split('/', 1)[1] for r in remote)}"]))
    return out or Finding(OK, "no leftover worktrees or branches")


@check("repo.secrets", "No key or token in any committed file, and every .env file is ignored",
       origin="08-22: a .env backup holding all four keys sat unignored in the path of `git add -A`")
def _repo_secrets(ctx: Ctx):
    if ctx.flags.get("no_git"):
        return None
    out: List[Finding] = []
    tracked = [p for p in ctx.git.out("ls-files", "-z").split("\0") if p]
    hits: List[Tuple[str, int, str]] = []
    for rel in tracked:
        p = ctx.root / rel
        try:
            if p.stat().st_size > 60_000_000 or p.suffix in (".xlsx", ".png", ".pdf", ".zip"):
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _KEY_RE.finditer(text):
            hits.append((rel, text.count("\n", 0, m.start()) + 1, _key_kind(m)))
    if hits:
        out.append(Finding(
            CLAUDE, f"{_plural(len(hits), 'key-shaped string')} in committed files (values not shown)",
            severity="critical", playbook="repo.secrets",
            detail=[f"{rel}:{line} -- {kind}" for rel, line, kind in hits[:12]],
            steps=["Remove them from the files and commit.",
                   "The student must also revoke and replace every key found: a key that was ever "
                   "public is compromised, whatever is committed afterwards."]))
    for env_file in sorted(ctx.root.glob(".env*")):
        if env_file.name == ".env.example" or not env_file.is_file():
            continue
        rel = env_file.name
        if rel in tracked:
            out.append(Finding(CLAUDE, f"{rel} is committed to the public repository", severity="critical",
                               playbook="repo.secrets",
                               steps=[f"git rm --cached {rel}, commit, and have every key in it replaced."]))
        elif not ctx.git("check-ignore", "-q", rel).ok:
            out.append(Finding(CLAUDE, f"{rel} is not ignored by git -- the next `git add -A` would "
                               "publish every key in it", severity="critical", playbook="repo.secrets",
                               steps=["Add a pattern covering it to .gitignore and commit."]))
    return out or Finding(OK, f"no key-shaped string in {len(tracked)} committed files; .env files ignored")


@check("repo.gitignore", "Private and scratch files cannot be committed by accident",
       origin="09-04: mock output belongs in the ignored data/mock/; 09-16 and 09-03: scratch JSON")
def _repo_gitignore(ctx: Ctx):
    if ctx.flags.get("no_git"):
        return None
    probes = {
        ".env": "the API keys",
        ".env.backup-20260101-000000": "backups of the API keys",
        "data/mock/observations.jsonl": "fabricated forecasts from mock runs",
        "continuity.json": "check_days.py scratch output",
        "milestones.json": "milestones.py scratch output",
        "run-summary.json": "the daily job's run summary",
        ".health/state.json": "this checker's private state",
    }
    missing = [f"{p} ({why})" for p, why in probes.items() if not ctx.git("check-ignore", "-q", p).ok]
    if missing:
        return Finding(CLAUDE, "not ignored by git: " + "; ".join(missing), severity="medium",
                       playbook="repo.gitignore", steps=["Add the missing patterns to .gitignore and commit."])
    return Finding(OK, "keys, mock output and scratch files are all ignored")


# ======================================================================================
# record -- the daily record in data/
# ======================================================================================

@check("record.parse", "Every record file reads cleanly, line by line",
       origin="09-19 integrity audit: every data file parsed and counted")
def _record_parse(ctx: Ctx):
    counts, bad = {}, {}
    for p in sorted((ctx.root / "data").glob("*.jsonl")):
        name = p.stem
        counts[name] = len(ctx.rows(name))
        if ctx.bad_lines(name):
            bad[name] = ctx.bad_lines(name)
    ctx.facts["record_lines"] = counts
    if not counts:
        return Finding(ERROR, "no data/*.jsonl files found", severity="high", playbook="record.parse")
    if bad:
        return Finding(CLAUDE, "unreadable lines in " + ", ".join(
            f"data/{k}.jsonl (line {', '.join(map(str, v[:5]))})" for k, v in bad.items()),
            severity="high", playbook="record.parse",
            detail=["Every reader skips or trips on them; find which commit wrote them (git log -p)."])
    return Finding(OK, "all record files parse: " + ", ".join(f"{k} {v:,}" for k, v in counts.items()
                                                                 if k in CORE_RECORD))


DELAY_NOTE = "10 hours after 13:10 UTC, as check_days.py says"


@check("record.continuity", "Every day since 1 Sep collected, and every model above the 80% floor",
       origin="09-03: scripts/check_days.py was written because a silently missed day can never "
              "be filled; every check-in since ran it")
def _record_continuity(ctx: Ctx):
    work = ctx.tmp / "continuity"
    work.mkdir(parents=True, exist_ok=True)
    p = _script(ctx, "check_days.py", "--json", cwd=work, timeout=240)
    try:
        c = json.loads((work / "continuity.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Finding(ERROR, "scripts/check_days.py did not produce its report", severity="high",
                       playbook="record.continuity", detail=_tail(p.out + p.err, 8))
    ctx.flags["continuity"] = c
    days = ctx.days_collected()
    ctx.facts.update({"days_collected": len(days), "first_day": days[0] if days else None,
                      "last_day": days[-1] if days else None, "today_state": c.get("today_state"),
                      "coverage_window": c.get("coverage_window")})
    out: List[Finding] = []
    today = c.get("today")
    for d in c.get("missing_days", []):
        if d == today and c.get("today_state") == "late":
            out.append(Finding(
                YOU, f"today ({d}) has not collected, and it is past the usual delay", severity="critical",
                playbook="record.continuity", due=f"{d}T23:59:59+00:00",
                steps=[f"Open {GITHUB_WEB}/actions/workflows/daily.yml",
                       "Click 'Run workflow' (top right), leave the inputs as they are, click the green "
                       "'Run workflow'.",
                       "Tell Claude; it will watch the run. A day not collected by 23:59 UTC is lost for good."]))
        else:
            out.append(Finding(
                CLAUDE, f"{d} has no observations -- a day that can never be recovered", severity="critical",
                playbook="record.continuity",
                steps=["Find out why (ci.runs; the run's steps and annotations).",
                       "Record it as lost in PREREGISTRATION.md section 11 and in the next addendum. "
                       "Never back-fill: a forecast stamped with a day the model never saw is fabricated."]))
    state = c.get("today_state")
    if state == "pending" and not c.get("today_collected"):
        out.append(Finding(INFO, f"today's run has not landed yet; it is due and still inside the usual "
                           f"delay (it becomes an alarm {DELAY_NOTE})", playbook="record.continuity"))
    elif state == "not_due" and not c.get("today_collected"):
        out.append(Finding(INFO, "today's run is not due until 13:10 UTC", playbook="record.continuity"))
    elif state == "closed":
        out.append(Finding(INFO, "no questions are asked from 8 December (none could resolve by the "
                           "freeze); the job still runs to record settlements", playbook="record.continuity"))
    for m in c.get("below_floor", []):
        cov = (c.get("coverage_window") or {}).get(m)
        out.append(Finding(CLAUDE, f"{m} is below the 80% floor over the last {c.get('window_days')} "
                           f"days ({_pct(cov) if cov is not None else '?'}) and still failing",
                           severity="high", playbook="record.continuity",
                           detail=["See record.errors for what its failures say."]))
    for m, b in (c.get("bridge_latest") or {}).items():
        if b.get("asked") and b.get("answered", 0) < 0.8 * b["asked"]:
            out.append(Finding(CLAUDE, f"the bridge that asks {m} through a second host answered only "
                               f"{b.get('answered')}/{b['asked']} on {c.get('bridge_day')} (deviations 23-24)",
                               severity="medium", playbook="record.continuity",
                               detail=["No day is at risk: since deviation 24 the bridge carries the model "
                                       "nowhere.",
                                       "If the host has retired the model early, record the bridge's early end "
                                       "in PREREGISTRATION.md 11 for the next addendum."]))
    watching = [m for m, v in (c.get("coverage_window") or {}).items()
                if v < 0.80 and m not in c.get("below_floor", [])]
    if watching:
        out.append(Finding(WATCH, "under the floor over the window but fine on the latest day: "
                           + ", ".join(watching), severity="low", playbook="record.continuity",
                           detail=["An old bad day is still inside the 7-day window; it clears as it ages out."]))
    lowest = min((c.get("coverage_window") or {}).items(), key=lambda kv: kv[1], default=None)
    if not [f for f in out if f.status in (CLAUDE, YOU)]:
        span = f"{days[0]} to {days[-1]}" if days else "none"
        note = f"; lowest over the last 7 days: {lowest[0]} {_pct(lowest[1])}" if lowest else ""
        out.insert(0, Finding(OK, f"unbroken: {len(days)} days collected ({span}), no gaps{note}"))
    return out


def expected_rows(day: str, n_tasks: int) -> Dict[Tuple[str, int], int]:
    """How many answers each (model, prompt variant) owes on `day` -- the registered design."""
    want: Dict[Tuple[str, int], int] = {}
    if not n_tasks:
        return want
    for spec in config.enabled_panel():
        if config.retired(spec, day):
            continue                    # no host serves it (deviation 24)
        want[(spec.key, 0)] = n_tasks
        if config.REPLICATES_PER_DAY:
            want[(spec.key, config.REPLICATE_VARIANT)] = min(config.REPLICATES_PER_DAY, n_tasks)
        if spec.key == config.H3_VARIANT_MODEL and day >= config.H3_VARIANT_START:
            for v in range(1, config.H3_VARIANTS):
                want[(spec.key, v)] = n_tasks
        if config.bridge_spec(spec, day) is not None:
            want[(spec.key, config.BRIDGE_VARIANT)] = n_tasks
    return want


@check("record.day_shape", "Each day has the full design: every question put to every model, "
       "plus replicates, the H3 arm and the bridge",
       origin="09-03: the backup run re-selected questions (30 not 25); 09-16 and 09-20 confirmed "
              "the H3 arm and the bridge started on their registered days")
def _record_day_shape(ctx: Ctx):
    tasks_by_day: Dict[str, int] = Counter(ctx.task_day(t) for t in ctx.primary_tasks())
    have: Dict[Tuple[str, str, int], int] = Counter(
        (o["_day"], o.get("model_key"), int(o.get("prompt_variant", 0) or 0)) for o in ctx.primary_obs())
    days = ctx.days_collected()[-14:]
    problems, known = [], []
    for day in days:
        n = tasks_by_day.get(day, 0)
        if n != config.TASKS_PER_DAY:
            (known if day in KNOWN_TASK_DAY_COUNTS else problems).append(
                f"{day}: {n} questions, not {config.TASKS_PER_DAY}"
                + (f" -- {KNOWN_TASK_DAY_COUNTS[day]}" if day in KNOWN_TASK_DAY_COUNTS else ""))
        for (model, variant), want in expected_rows(day, n).items():
            got = have.get((day, model, variant), 0)
            if got != want:
                if day == ctx.today.isoformat() and got < want:
                    continue                    # still collecting, or the backup run will finish it
                problems.append(f"{day}: {model} variant {variant} has {got} of {want} answers")
        extra = sorted({(m, v) for (d, m, v) in have if d == day} - set(expected_rows(day, n)))
        for m, v in extra:
            problems.append(f"{day}: unexpected rows for {m} variant {v} ({have[(day, m, v)]})")
    if days:
        latest = days[-1]
        ctx.facts["rows_per_day_latest"] = sum(v for (d, _, _), v in have.items() if d == latest)
    if problems:
        return Finding(WATCH, f"{_plural(len(problems), 'gap')} in the design over the last "
                       f"{len(days)} days", severity="medium", playbook="record.day_shape",
                       detail=problems[:15],
                       steps=["A missing row means the collector never asked -- usually a run cut off "
                              "by its 45-minute limit. Check that day's run (ci.runs)."])
    n = expected_rows(days[-1], config.TASKS_PER_DAY) if days else {}
    return Finding(OK, f"the last {len(days)} days each have the full design "
                   f"({sum(n.values())} answers a day now)", detail=known)


def classify_error(message: str) -> str:
    """What a failed answer's error says, in the categories that decide who acts."""
    m = str(message or "").lower()
    code_m = re.search(r"http (\d{3})", m)
    code = int(code_m.group(1)) if code_m else None
    if (code == 402 or "insufficient_quota" in m or "daily quota" in m or "billing" in m
            or "credit balance" in m or "insufficient credit" in m or "out of credit" in m
            or "exceeded your current quota" in m):
        return "quota"
    if (code == 401 or "invalid api key" in m or "invalid x-api-key" in m or "api key not valid" in m
            or "incorrect api key" in m or (re.search(r"api[_ ]key", m) and "not set" in m)
            or (code == 403 and ("key" in m or "permission" in m or "forbidden" in m))):
        return "auth"
    if (code == 404 or "model_not_found" in m or "model not found" in m or "does not exist" in m
            or "no longer available" in m or "decommissioned" in m or "has been deprecated" in m
            or "was retired" in m):
        return "retired"
    if code == 429 or "rate limit" in m or "rate-limit" in m or "too many requests" in m:
        return "rate_limit"
    if (code is not None and code >= 500) or "timeout" in m or "timed out" in m \
            or "connecterror" in m or "connection" in m or "overloaded" in m:
        return "server"
    if "unparseable" in m or "truncated" in m:
        return "parse"
    return "other"


@check("record.errors", "What the failed answers of the last week say",
       origin="09-13 qwen 429s; 09-03 truncation; 09-22 qwen 21/27; an out-of-credit or retired "
              "model would show up here first")
def _record_errors(ctx: Ctx):
    days = ctx.days_collected()[-7:]
    if not days:
        return None
    recent = [o for o in ctx.primary_obs() if o["_day"] in days]
    failed = [o for o in recent if o.get("error") or o.get("forecast") is None]
    by_model_day: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for o in failed:
        by_model_day[(o.get("model_key"), o["_day"])].append(o)
    total_by_model = Counter(o.get("model_key") for o in recent)
    ctx.facts["failed_answers_7d"] = {m: sum(len(v) for (k, _), v in by_model_day.items() if k == m)
                                      for m in total_by_model}
    if not failed:
        return Finding(OK, f"no failed answers in the last {len(days)} days ({len(recent):,} asked)")
    latest = days[-1]
    out: List[Finding] = []
    per_cat: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for o in failed:
        per_cat[classify_error(o.get("error") or "no forecast in the reply")][o.get("model_key")].append(o)
    spec_of = config.panel_by_key()
    recent_days = set(days[-2:])
    for cat, models in per_cat.items():
        for model, rows in models.items():
            n, total = len(rows), total_by_model[model]
            when = sorted({r["_day"] for r in rows})
            live = bool(recent_days & set(when))
            spec = spec_of.get(model)
            vendor = VENDOR_OF_PROVIDER.get(rows[-1].get("provider") or (spec.provider if spec else ""), "")
            sample = str(rows[-1].get("error") or "")[:220]
            head = f"{model}: {n} of {total} answers failed ({cat.replace('_', ' ')}) on {', '.join(when)}"
            latest_failed = len(by_model_day.get((model, latest), []))
            recovered = latest_failed == 0
            if cat == "quota" and live:
                out.append(Finding(YOU, f"{VENDOR_NAMES.get(vendor, vendor)} says the account is out of "
                                   f"credit or quota ({model})", severity="critical", playbook="record.errors",
                                   detail=[head, sample], steps=VENDOR_TOPUP.get(vendor, []) +
                                   ["Tell Claude once it is done; the next run asks again."]))
            elif cat == "auth" and live:
                out.append(Finding(YOU, f"{VENDOR_NAMES.get(vendor, vendor)} refused the API key ({model})",
                                   severity="critical", playbook="record.errors", detail=[head, sample],
                                   steps=[f"Make a new key in your {VENDOR_NAMES.get(vendor, vendor)} account.",
                                          f"GitHub -> the repository -> Settings -> Secrets and variables -> "
                                          f"Actions -> {VENDOR_SECRET.get(vendor, 'the key')} -> Update.",
                                          "Put the same key in .env on this Mac."]))
            elif cat == "retired" and live:
                out.append(Finding(CLAUDE, f"{model}'s host says the model does not exist -- it may have "
                                   "been retired", severity="critical", playbook="record.errors",
                                   detail=[head, sample]))
            elif cat == "rate_limit":
                out.append(Finding(KNOWN if recovered else WATCH,
                                   head + ("; every answer came back on the latest day" if recovered else ""),
                                   severity="low" if recovered else "medium", playbook="record.errors",
                                   detail=["Rate limits are waited out for up to 15 minutes a run "
                                           "(deviation 11); what is left over is lost for that day.", sample]))
            elif cat == "server":
                out.append(Finding(KNOWN if recovered else WATCH, head, severity="low",
                                   playbook="record.errors", detail=[sample]))
            elif cat == "parse":
                share = n / max(total, 1)
                out.append(Finding(CLAUDE if share > 0.02 else INFO, head, playbook="record.errors",
                                   severity="medium" if share > 0.02 else "low", detail=[sample]))
            else:
                out.append(Finding(CLAUDE if live else INFO, head, severity="low", playbook="record.errors",
                                   detail=[sample]))
    return out


@check("record.integrity", "No duplicate ids, orphan answers, impossible forecasts or mock rows",
       origin="09-04: a mock run could append fabricated forecasts; 09-19: full integrity audit")
def _record_integrity(ctx: Ctx):
    problems, known = [], []
    obs, tasks, res = ctx.rows("observations"), ctx.rows("tasks"), ctx.rows("resolutions")
    for name, rows, key in (("observations", obs, "obs_id"), ("tasks", tasks, "task_id"),
                            ("resolutions", res, "task_id")):
        dup = [k for k, v in Counter(str(r.get(key)) for r in rows).items() if v > 1]
        if dup:
            problems.append(f"{len(dup)} duplicate {key}(s) in {name}: {', '.join(dup[:3])}")
    ids = ctx.task_index()
    orphans = [o.get("obs_id") for o in obs if str(o.get("task_id")) not in ids]
    if orphans:
        problems.append(f"{len(orphans)} answer(s) to questions that are not in tasks.jsonl")
    bad_f = [o.get("obs_id") for o in obs if o.get("forecast") is not None
             and not (isinstance(o.get("forecast"), (int, float)) and 0.0 <= float(o["forecast"]) <= 1.0)]
    if bad_f:
        problems.append(f"{len(bad_f)} forecast(s) outside [0, 1]")
    mock = [o for o in obs if str(o.get("provider", "")).lower() == "mock"
            or str(o.get("model_id_returned", "")).endswith("-mock")]
    if mock:
        problems.append(f"{len(mock)} MOCK answer(s) in the real record -- fabricated forecasts")
    arms = Counter(t.get("arm") for t in tasks)
    unlabelled = arms.pop(None, 0)
    odd_arms = {a: n for a, n in arms.items() if a not in (config.PRIMARY_ARM, config.PRE_REGISTRATION_ARM)}
    if odd_arms:
        problems.append(f"questions on arms the study does not have: {odd_arms}")
    if unlabelled:
        early = all((ctx.task_day(t) or "9") < config.COLLECTION_START for t in tasks if t.get("arm") is None)
        (known if early and unlabelled <= PILOT_TASKS_WITHOUT_ARM else problems).append(
            f"{unlabelled} question rows carry no arm label"
            + (" -- pre-registration pilot rows from before the label existed; read as pilot" if early else ""))
    bad_usd = [r for r in ctx.rows("ledger") if not isinstance(r.get("usd"), (int, float)) or r.get("usd") < 0]
    if bad_usd:
        problems.append(f"{len(bad_usd)} ledger row(s) with a missing or negative cost")
    if problems:
        return Finding(CLAUDE, f"{_plural(len(problems), 'integrity problem')} in the record",
                       severity="high", playbook="record.integrity", detail=problems + known)
    out = [Finding(OK, f"{len(obs):,} answers, {len(tasks):,} questions, {len(res)} settlements: "
                   "no duplicates, no orphans, every forecast in [0, 1], no mock rows")]
    out += [Finding(KNOWN, k, playbook="record.integrity") for k in known]
    return out


@check("record.append_only", "The record only ever grew, and only the daily job wrote it",
       origin="09-19: every commit touching data/*.jsonl was checked for deletions")
def _record_append_only(ctx: Ctx):
    if ctx.flags.get("no_git"):
        return None
    if ctx.git.out("rev-parse", "--is-shallow-repository") == "true":
        return Finding(INFO, "this is a shallow copy, so the history cannot be checked here")
    since = (date.fromisoformat(config.COLLECTION_START) - timedelta(days=1)).isoformat()
    files = [f"data/{n}.jsonl" for n in CORE_RECORD]
    log = ctx.git.out("log", f"--since={since}", "--format=@@%h%x09%an%x09%aI%x09%s", "--numstat", "--", *files,
                      timeout=120)
    commits, deleted, strangers, known = 0, [], [], []
    current = None
    for line in log.splitlines():
        if line.startswith("@@"):
            sha, author, when, subject = (line[2:].split("\t") + ["", "", ""])[:4]
            current = (sha, author, when[:10], subject)
            commits += 1
            if author != COLLECTOR:
                (known if sha[:7] in KNOWN_RECORD_COMMITS else strangers).append(
                    f"{sha} {when[:10]} by {author}: {subject}"
                    + (f" -- {KNOWN_RECORD_COMMITS[sha[:7]]}" if sha[:7] in KNOWN_RECORD_COMMITS else ""))
            continue
        parts = line.split("\t")
        if len(parts) == 3 and current and parts[1].isdigit() and int(parts[1]) > 0:
            deleted.append(f"{current[0]} {current[2]}: {parts[1]} line(s) removed from {parts[2]}")
    ctx.facts["record_commits_since_start"] = commits
    out: List[Finding] = []
    if deleted:
        out.append(Finding(CLAUDE, "the record lost lines after collection began", severity="critical",
                           playbook="record.append_only", detail=deleted[:10]))
    if strangers:
        out.append(Finding(CLAUDE, "record files changed by someone other than the daily job",
                           severity="high", playbook="record.append_only", detail=strangers[:10]))
    out += [Finding(KNOWN, k, playbook="record.append_only") for k in known]
    if not deleted and not strangers:
        out.insert(0, Finding(OK, f"{commits} commits to the record since collection began: every one "
                              "only added lines, and every one but the known exception came from the daily job"
                              if known else f"{commits} commits to the record since collection began: all "
                              "append-only, all from the daily job"))
    return out


@check("record.hosts", "OpenRouter's hosts are recorded, and a known-bad host never answers",
       origin="09-09: Novita cost qwen two whole days (deviation 4); 09-23: Novita reappeared as a host")
def _record_hosts(ctx: Ctx):
    try:
        from neff.providers import OpenRouterProvider
        ignored = set(OpenRouterProvider.EXTRA_BODY["provider"].get("ignore", []))
    except Exception:                                                  # noqa: BLE001
        ignored = set()
    days = set(ctx.days_collected()[-7:])
    rows = [o for o in ctx.primary_obs() if o["_day"] in days and o.get("forecast") is not None
            and str(o.get("provider", "")).startswith("openrouter")]
    if not rows:
        return None
    hosts: Dict[str, Counter] = defaultdict(Counter)
    missing = 0
    for o in rows:
        h = o.get("upstream_provider")
        if not h:
            missing += 1
        hosts[f"{o.get('model_key')}{' (Azure route)' if o.get('provider') == 'openrouter_azure' else ''}"][h or "?"] += 1
    out: List[Finding] = []
    bad = sorted({h for c in hosts.values() for h in c if h in ignored})
    if bad:
        out.append(Finding(CLAUDE, f"answers came from a host the routing ignores: {', '.join(bad)}",
                           severity="high", playbook="record.hosts"))
    off_route = [o for o in rows if o.get("provider") == "openrouter_azure" and o.get("upstream_provider") != "Azure"]
    if off_route:
        out.append(Finding(CLAUDE, f"{len(off_route)} answers on the Azure-only route came from another "
                           "host (deviation 23 pins Azure)", severity="high", playbook="record.hosts"))
    if missing:
        out.append(Finding(WATCH, f"{missing} OpenRouter answers name no host", severity="low",
                           playbook="record.hosts"))
    seen = _seen(ctx).setdefault("hosts", {})
    new = []
    for model, c in hosts.items():
        before = set(seen.get(model, []))
        fresh = sorted(set(c) - before - {"?"})
        if before and fresh:
            new.append(f"{model}: {', '.join(fresh)}")
        seen[model] = sorted(before | set(c) - {"?"})
    if new:
        out.append(Finding(INFO, "first answers from new hosts: " + "; ".join(new), playbook="record.hosts"))
    ctx.facts["hosts_7d"] = {m: dict(c) for m, c in hosts.items()}
    out.insert(0, Finding(OK if not bad and not off_route else INFO, "hosts over the last week: " + "; ".join(
        f"{m} {', '.join(f'{h} {n}' for h, n in c.most_common())}" for m, c in sorted(hosts.items()))))
    return out


@check("record.served_ids", "Every model answered as the exact version pinned for it",
       origin="PREREGISTRATION.md 10 (limitation 4): 'we log the served id every call and report drift'")
def _record_served_ids(ctx: Ctx):
    from neff.verify import classify_served_id
    days = set(ctx.days_collected()[-3:])
    spec_of = config.panel_by_key()
    drift: Counter = Counter()
    notes: Counter = Counter()
    for o in ctx.primary_obs():
        if o["_day"] not in days or o.get("forecast") is None:
            continue
        spec = spec_of.get(o.get("model_key"))
        if spec is None:
            continue
        variant = int(o.get("prompt_variant", 0) or 0)
        target = config.bridge_spec(spec, o["_day"]) if variant == config.BRIDGE_VARIANT else None
        target = target or config.routed(spec, o["_day"])
        is_drift, note = classify_served_id(target.model_id, str(o.get("model_id_returned") or ""))
        if is_drift:
            drift[(spec.key, target.model_id, str(o.get("model_id_returned")))] += 1
        elif note:
            notes[(spec.key, note)] += 1
    if drift:
        return Finding(CLAUDE, "a model answered as a different version than the one pinned",
                       severity="critical", playbook="record.served_ids",
                       detail=[f"{k}: pinned {p}, served {s} ({n}x)" for (k, p, s), n in drift.most_common(10)])
    out = [Finding(OK, "every answer of the last 3 days came from the pinned version")]
    out += [Finding(INFO, f"{k}: {note} ({n}x)") for (k, note), n in notes.items()]
    return out


@check("record.logprobs", "Logprobs keep arriving for the models the 5.4(a) re-estimate uses",
       origin="09-13: deepseek's logprobs mostly never arrived and nothing said so (deviation 12)")
def _record_logprobs(ctx: Ctx):
    days = set(ctx.days_collected()[-7:])
    spec_of = config.panel_by_key()
    asked, carried = Counter(), Counter()
    for o in ctx.primary_obs():
        if o["_day"] not in days or o.get("forecast") is None or int(o.get("prompt_variant", 0) or 0) != 0:
            continue
        spec = spec_of.get(o.get("model_key"))
        if spec is None or not config.routed(spec, o["_day"]).supports_logprobs:
            continue
        asked[spec.key] += 1
        carried[spec.key] += bool(o.get("logprobs"))
    if not asked:
        return None
    share = {k: carried[k] / asked[k] for k in asked}
    ctx.facts["logprob_share_7d"] = {k: round(v, 3) for k, v in share.items()}
    low = {k: v for k, v in share.items()
           if v < PARTIAL_LOGPROBS_FLOOR.get(k, 0.95) and k not in KNOWN_LOW_LOGPROBS}
    out = [Finding(OK if not low else INFO, "logprobs arrived with: " + ", ".join(
        f"{k} {_pct(v)}" for k, v in sorted(share.items())))]
    for k, v in share.items():
        if k in KNOWN_LOW_LOGPROBS and v < 0.80:
            out.append(Finding(KNOWN, f"{k} {_pct(v)} -- {KNOWN_LOW_LOGPROBS[k]}", playbook="record.logprobs"))
    if low:
        out.append(Finding(WATCH, "fewer logprobs than before for " + ", ".join(
            f"{k} ({_pct(v)})" for k, v in low.items()), severity="medium", playbook="record.logprobs"))
    return out


@check("record.state", "Every question carries the market state the H1 legs need",
       origin="09-03 and 09-09: state is stamped at ask time and cannot be added afterwards")
def _record_state(ctx: Ctx):
    days = ctx.days_collected()[-7:]
    tasks = [t for t in ctx.primary_tasks() if ctx.task_day(t) in set(days)]
    if not tasks:
        return None
    need_all = ("vix_level", "realized_vol_20d", "asked_on")
    need_event = ("ladder_distance", "days_out")
    missing: Counter = Counter()
    for t in tasks:
        st = t.get("state") or {}
        for k in need_all + (need_event if t.get("kind") == "event" else ()):
            if st.get(k) is None:
                missing[k] += 1
    if missing:
        return Finding(CLAUDE, "questions without market state: " + ", ".join(
            f"{k} missing on {n}" for k, n in missing.items()), severity="medium", playbook="record.state",
            detail=["A state variable is registered to be read at ask time, so a gap cannot be repaired later."])
    return Finding(OK, f"all {len(tasks)} questions of the last {len(days)} days carry their market state")


@check("record.prices", "Kalshi prices are recorded on the market questions",
       origin="09-13: Kalshi renamed its price fields and every price came back empty (deviation 15)")
def _record_prices(ctx: Ctx):
    days = [d for d in ctx.days_collected()[-7:] if d > "2026-09-13"]
    events = [t for t in ctx.primary_tasks() if t.get("kind") == "event" and ctx.task_day(t) in set(days)]
    if not events:
        return None
    by_day: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    for t in events:
        d = by_day[ctx.task_day(t)]
        d[0] += 1
        d[1] += t.get("market_implied") is not None
    latest = max(by_day)
    n, priced = by_day[latest]
    share = priced / n if n else 1.0
    ctx.facts["priced_share_latest"] = round(share, 3)
    if share < 0.5:
        return Finding(WATCH, f"only {priced} of {n} market questions on {latest} carry a Kalshi price",
                       severity="medium", playbook="record.prices")
    total = sum(v[0] for v in by_day.values())
    got = sum(v[1] for v in by_day.values())
    return Finding(OK, f"{got} of {total} market questions of the last week carry a Kalshi price")


@check("record.market", "Market state: is today a stress day worth protecting?",
       origin="09-09: a stress day is worth far more to H1 than an ordinary one; 09-23: a new VIX low")
def _record_market(ctx: Ctx):
    c = ctx.flags.get("continuity") or {}
    vix = c.get("vix_latest")
    if not isinstance(vix, (int, float)):
        return None
    ctx.facts["vix"] = {"latest": vix, "day": c.get("vix_latest_day"), "min": c.get("vix_min"),
                        "max": c.get("vix_max"), "distinct": c.get("vix_distinct"), "band": c.get("vix_band")}
    line = (f"VIX {vix:.2f} on {c.get('vix_latest_day')} ({c.get('vix_band')}); range "
            f"{c.get('vix_min'):.2f}-{c.get('vix_max'):.2f} over the window, {c.get('vix_distinct')} distinct states")
    out = [Finding(INFO, line)]
    if c.get("vix_new_high") or vix >= 25.0:
        complete = not [f for f in ctx.results.get("record.day_shape", []) if f.status == WATCH]
        out.append(Finding(YOU if not complete else INFO,
                           "a possible stress day -- the kind the stress leg of H1 depends on",
                           severity="high" if not complete else "low", playbook="record.market",
                           detail=["It collected in full." if complete else
                                   "It did NOT collect in full; see record.day_shape."],
                           steps=[] if complete else [f"Run the workflow again now: {GITHUB_WEB}/actions/workflows/daily.yml"]))
    elif isinstance(c.get("vix_min"), (int, float)) and vix <= c["vix_min"] and c.get("vix_distinct", 0) > 2:
        out.append(Finding(KNOWN, "a new VIX low -- not a problem: terciles are formed in-sample, and "
                           "section 10 limitation 5 registers that a flat stress leg is reported as untested "
                           "while the ambiguity leg carries H1", playbook="record.market"))
    return out


@check("record.ask_times", "When each day's questions were actually asked",
       origin="09-29: 29 Sep was asked at 00:16 UTC by a run that started hours late")
def _record_ask_times(ctx: Ctx):
    first: Dict[str, datetime] = {}
    for t in ctx.primary_tasks():
        when = _ts(t.get("asked_at"))
        d = ctx.task_day(t)
        if when and d and (d not in first or when < first[d]):
            first[d] = when
    days = ctx.days_collected()[-14:]
    early = [f"{d} at {first[d]:%H:%M} UTC" for d in days if d in first and first[d].hour < 13]
    late = [f"{d} at {first[d]:%H:%M} UTC" for d in days if d in first and first[d].hour >= 20]
    ctx.facts["ask_times_14d"] = {d: f"{first[d]:%H:%M}" for d in days if d in first}
    detail = []
    if early:
        detail.append("before the 13:10 slot (a delayed run crossed midnight and collected the new "
                      "day): " + ", ".join(early))
    if late:
        detail.append("only from the evening backup: " + ", ".join(late))
    if detail:
        return Finding(INFO, "some days were asked outside the usual afternoon", detail=detail + [
            "Not a fault: each question carries the market state published when it was asked "
            "(VALIDITY.md 7). It shows how much the backup run matters (ci.schedule)."],
            playbook="record.ask_times")
    return Finding(OK, "every day of the last two weeks was asked in the afternoon run")


# ======================================================================================
# panel -- coverage on the panel as it will be estimated (outcome-blind)
# ======================================================================================

def _panel_paths(ctx: Ctx) -> dict:
    return {"obs_path": ctx.path("observations"), "resolutions_path": ctx.path("resolutions"),
            "tasks_path": ctx.path("tasks")}


# How close to the floor counts as close. Below it, section 5.6 removes the model.
COVERAGE_MARGIN = 0.03


@check("panel.coverage", "The registered 80% floor on the panel that will actually be estimated",
       origin="09-16 and 09-20: qwen was 97% on all days but under 80% on the settled questions, "
              "which is what section 5.6 judges; 09-29: qwen exactly on the floor three days before "
              "the Week-5 fit applies the rule")
def _panel_coverage(ctx: Ctx):
    # OUTCOME-BLIND. Everything here reads which forecast cells are filled and when a
    # question closes -- never an outcome, never an error. The three row rules decide on
    # forecasts and question metadata (see their docstrings in neff/panel.py).
    import warnings

    import numpy as np
    from neff import prediction
    from neff.analysis import COVERAGE_JUDGEMENT_MIN_TASKS
    from neff.panel import (COVERAGE_FLOOR, apply_filing_deadline_exclusion,
                            apply_settled_question_exclusion, apply_stale_source_exclusion,
                            load_panel, model_coverage)

    def rows_kept(require_resolved: bool):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            panel = load_panel(require_resolved=require_resolved, **_panel_paths(ctx))
        return apply_settled_question_exclusion(apply_filing_deadline_exclusion(apply_stale_source_exclusion(panel)))

    settled = rows_kept(True)
    cov = model_coverage(settled)
    n = settled.n_tasks
    ctx.facts["panel_resolved_task_days"] = n
    ctx.facts["panel_coverage"] = {k: round(v, 4) for k, v in cov.items()}
    if not n:
        return Finding(INFO, "no settled question yet, so the floor cannot be judged")
    lowest = min(cov, key=cov.get)
    head = f"{n} settled task-days in the primary panel; lowest coverage {lowest} {_pct(cov[lowest])}"
    close = {k: v for k, v in cov.items() if v < COVERAGE_FLOOR + COVERAGE_MARGIN}
    if not close:
        return Finding(OK, head + " -- every model clear of the 80% floor")

    # Where each such model will stand once what has already been asked settles. The
    # Week-5 fit applies 5.6 to whatever has settled when it is published, so the
    # horizon is that moment until it passes, then the freeze.
    publish = _ts(prediction.CALIBRATION_CLOSES_BY)
    horizon = publish if ctx.now < _ts(prediction.PUBLISH_NOT_BEFORE) else _ts(f"{config.DATA_FREEZE}T23:59:59+00:00")
    label = "at the Week-5 fit" if horizon == publish else "at the freeze"
    everything = rows_kept(False)
    resolved, index = ctx.resolved_ids(), ctx.task_index()
    pending = [i for i, tid in enumerate(everything.task_ids)
               if tid not in resolved and (_ts((index.get(tid) or {}).get("resolves_after")) or horizon) <= horizon
               and (index.get(tid) or {}).get("resolves_after")]
    out = [Finding(INFO, head)]
    for k, v in sorted(close.items(), key=lambda kv: kv[1]):
        col = everything.model_keys.index(k)
        answered_now = round(v * n)
        more_n = len(pending)
        more_a = int(sum(1 for i in pending if not np.isnan(everything.forecasts[i, col])))
        projected = (answered_now + more_a) / (n + more_n) if (n + more_n) else v
        ctx.facts.setdefault("coverage_projection", {})[k] = {"now": round(v, 4), label: round(projected, 4)}
        where = (f"{_pct(v)} on {n} settled task-days now; about {_pct(projected)} {label}, once the {more_n} "
                 f"already-asked questions closing by then settle ({more_n - more_a} of them without a {k} answer)")
        consequence = ("section 5.6 removes it from the primary panel and M becomes "
                       f"{len(cov) - 1} (VALIDITY.md 8; the M = 8 human benchmark is registered, deviation 17)")
        if v < COVERAGE_FLOOR and projected < COVERAGE_FLOOR:
            out.append(Finding(WATCH, f"{k} is under the 80% floor and is expected to stay under it {label}",
                               severity="medium", playbook="panel.coverage",
                               detail=[where, "If it is still under when the rule is applied, " + consequence + ".",
                                       "Nothing can be recovered: a lost answer cannot be asked again."]))
        elif v < COVERAGE_FLOOR:
            out.append(Finding(WATCH, f"{k} is under the 80% floor now, but should clear it {label}",
                               severity="low", playbook="panel.coverage", detail=[where]))
        elif projected < COVERAGE_FLOOR:
            out.append(Finding(WATCH, f"{k} is on the 80% floor and heading under it {label}", severity="medium",
                               playbook="panel.coverage", detail=[where, "If so, " + consequence + "."]))
        else:
            out.append(Finding(WATCH, f"{k} sits close to the 80% floor ({_pct(v)}), heading to about "
                               f"{_pct(projected)} {label}", severity="low", playbook="panel.coverage", detail=[where]))
        if n < COVERAGE_JUDGEMENT_MIN_TASKS:
            out[-1].detail.append("Provisional: fewer than 20 settled task-days.")
    return out


@check("panel.health", "The panel the daily job's 'Panel health' step prints",
       origin="the daily workflow prints this every run; 09-19 read it")
def _panel_health(ctx: Ctx):
    import warnings
    from neff.panel import describe, load_panel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = describe(load_panel(require_resolved=False, **_panel_paths(ctx)))
    ctx.facts["panel"] = {k: d[k] for k in ("n_tasks", "n_models", "coverage", "resolved", "distinct_days")}
    if not d.get("rows_time_ordered", True):
        return Finding(CLAUDE, "the panel's rows are out of time order", severity="medium", playbook="panel.health")
    return Finding(OK, f"{d['n_tasks']} task-days x {d['n_models']} models, {_pct(d['coverage'])} filled, "
                   f"{d['resolved']} settled, {d['distinct_days']} days")


@check("panel.bridge", "gpt_small answers the same through a second host (deviations 23-24)",
       origin="09-19: OpenAI retires gpt-4.1-nano on 23 Oct; Azure keeps it; both are asked until then")
def _panel_bridge(ctx: Ctx):
    from neff.panel import bridge_report
    report = bridge_report(obs_path=ctx.path("observations"))
    if not report:
        return None
    out = []
    for model, r in report.items():
        a, own = r["across_routes"], r.get("own_replicates") or {}
        rel = a.get("reliability")
        rel = None if rel is None or (isinstance(rel, float) and math.isnan(rel)) else float(rel)
        ctx.facts[f"bridge_{model}"] = {"n": a["n"], "identical": round(a["identical_share"], 3),
                                        "reliability": round(rel, 3) if rel is not None else None}
        line = (f"{model}: {a['n']} questions on both routes, {_pct(a['identical_share'])} identical, "
                f"reliability {a['reliability']:.3f}" + (
                    f" (its own replicates: {_pct(own['identical_share'])}, {own['reliability']:.3f})"
                    if own else ""))
        weak = a["n"] >= 30 and own and a["reliability"] < own["reliability"] - 0.15
        out.append(Finding(WATCH if weak else OK, line, severity="medium" if weak else "low",
                           playbook="panel.bridge"))
    return out


# ======================================================================================
# resolve -- settlements
# ======================================================================================

@check("resolve.integrity", "Every settlement is 0 or 1, recorded once, for a real question",
       origin="09-19: the resolutions audit")
def _resolve_integrity(ctx: Ctx):
    res, index = ctx.rows("resolutions"), ctx.task_index()
    bad = [r for r in res if r.get("outcome") not in (0, 1, 0.0, 1.0)]
    unknown = [r for r in res if str(r.get("task_id")) not in index]
    mismatch, known = [], 0
    for r in res:
        t = index.get(str(r.get("task_id")))
        src = str(r.get("source") or "")
        if t is None or not src.startswith("kalshi:"):
            continue
        if src[len("kalshi:"):] != str(t.get("source_ref")):
            if src.startswith("kalshi:edgar:") and t.get("arm") != config.PRIMARY_ARM:
                known += 1
            else:
                mismatch.append(f"{r.get('task_id')}: {src} vs {t.get('source_ref')}")
    problems = ([f"{len(bad)} settlement(s) that are not 0 or 1"] if bad else []) + \
               ([f"{len(unknown)} settlement(s) for questions not in tasks.jsonl"] if unknown else []) + mismatch[:5]
    if problems:
        return Finding(CLAUDE, "settlement problems", severity="high", playbook="resolve.integrity", detail=problems)
    out = [Finding(OK, f"{len(res)} settlements, each 0 or 1, one per question")]
    if known:
        out.append(Finding(KNOWN, f"{known} pilot-era settlements carry a 'kalshi:edgar:' source -- August "
                           "pilot rows, outside the study", playbook="resolve.integrity"))
    return out


@check("resolve.pending", "Every contract past its close has its settlement recorded",
       origin="09-16: resolutions.jsonl looked frozen for four days; 09-22: 'past-due unresolved: 0'")
def _resolve_pending(ctx: Ctx):
    resolved = ctx.resolved_ids()
    grace = ctx.now - timedelta(hours=6)
    due: Dict[str, datetime] = {}
    count: Counter = Counter()
    for t in ctx.primary_tasks():
        if t.get("kind") != "event" or str(t.get("task_id")) in resolved:
            continue
        close = _ts(t.get("resolves_after"))
        if close and close < grace:
            ref = str(t.get("source_ref"))
            due[ref] = max(close, due.get(ref, close))
            count[ref] += 1
    ctx.facts["contracts_past_close_unsettled"] = len(due)
    if not due:
        return Finding(OK, "no contract is past its close without a recorded settlement")
    if ctx.offline:
        return Finding(INFO, f"{len(due)} contract(s) past their close await settlement "
                       "(offline: Kalshi not asked)", detail=sorted(due)[:10])
    from neff.sources import kalshi
    out = []
    settled_missing: List[Tuple[str, datetime]] = []
    waiting: List[Tuple[str, datetime, str]] = []
    for ref, close in sorted(due.items(), key=lambda kv: kv[1])[:25]:
        r = ctx.http.get(f"{KALSHI_API}/markets/{ref}", headers={"Accept": "application/json"})
        try:
            market = (r.json().get("market") if r.ok else None) or {}
        except ValueError:
            market = {}
        if not market:
            waiting.append((ref, close, f"Kalshi unreadable: {r.error or r.status}"))
        elif kalshi.settlement_of(market) is not None:
            settled_missing.append((ref, close))
        else:
            waiting.append((ref, close, f"Kalshi status {market.get('status')}"))
    for ref, close in settled_missing:
        hours = (ctx.now - close).total_seconds() / 3600
        out.append(Finding(CLAUDE if hours > 30 else INFO,
                           f"Kalshi has settled {ref} ({count[ref]} task-days), but the record does not have it"
                           + ("" if hours > 30 else " yet -- the next daily run records it"),
                           severity="high" if hours > 30 else "low", playbook="resolve.pending"))
    if waiting:
        overdue = [w for w in waiting if ctx.now - w[1] > timedelta(days=2)]
        out.append(Finding(WATCH if overdue else INFO, f"{_plural(len(waiting), 'contract')} closed and "
                           "awaiting Kalshi's settlement", severity="low", playbook="resolve.pending",
                           detail=[f"{ref} (closed {close:%d %b %H:%M}; {why})" for ref, close, why in waiting[:10]]))
    return out


@check("resolve.upcoming", "What settles in the next two weeks",
       origin="09-22 and 09-23 listed the next settlements; the Week-5 fit needs 2 Oct payrolls")
def _resolve_upcoming(ctx: Ctx):
    from neff.analysis import resolution_event
    from neff.surprise import is_release_event
    resolved = ctx.resolved_ids()
    horizon = ctx.now + timedelta(days=14)
    events: Dict[str, List] = {}
    for t in ctx.primary_tasks():
        if t.get("kind") != "event" or str(t.get("task_id")) in resolved:
            continue
        close = _ts(t.get("resolves_after"))
        if close and ctx.now <= close <= horizon:
            ev = resolution_event(str(t.get("source_ref")))
            e = events.setdefault(ev, [close, 0])
            e[0], e[1] = max(e[0], close), e[1] + 1
    if not events:
        return Finding(INFO, "nothing settles in the next two weeks")
    lines = [f"{close:%a %d %b}  {ev}  ({n} task-days{', a listed release' if is_release_event(ev) else ''})"
             for ev, (close, n) in sorted(events.items(), key=lambda kv: kv[1][0])]
    ctx.facts["next_settlements"] = lines[:8]
    return Finding(INFO, f"{len(events)} contract events settle in the next two weeks", detail=lines[:12])


@check("resolve.eligibility", "Every market question resolves by the freeze (section 5.4(b))",
       origin="09-16: the builder was checked against 'eligible questions must resolve on or before 11 Dec'")
def _resolve_eligibility(ctx: Ctx):
    end = _ts(f"{config.DATA_FREEZE}T23:59:59+00:00")
    late = [f"{t.get('source_ref')} resolves {t.get('resolves_after')}" for t in ctx.primary_tasks()
            if t.get("kind") == "event" and (_ts(t.get("resolves_after")) or end) > end]
    filings = sum(1 for t in ctx.primary_tasks() if t.get("kind") == "filing")
    if late:
        return Finding(CLAUDE, f"{len(late)} market question(s) resolve after the freeze", severity="high",
                       playbook="resolve.eligibility", detail=late[:8])
    return [Finding(OK, "every market question resolves by 11 Dec"),
            Finding(KNOWN, f"{filings} filing questions carry no resolution date: a company files when it "
                    "files; late-window ones that cannot resolve are excluded on read (deviation 17 (8))",
                    playbook="resolve.eligibility")]


@check("resolve.surprise", "Every settled listed release has its surprise recorded",
       origin="09-13 and 09-19: the Week-5 calibration needs every settled release's surprise; the "
              "step that records it is allowed to fail quietly")
def _resolve_surprise(ctx: Ctx):
    from neff.analysis import resolution_event
    from neff.surprise import is_release_event
    rows = [r for r in ctx.rows("release_surprise") if r.get("role") == "study"]
    have = Counter(r.get("kalshi_event") for r in rows)
    dup = [e for e, n in have.items() if n > 1]
    resolved = ctx.resolved_ids()
    closes: Dict[str, datetime] = {}
    for t in ctx.primary_tasks():
        if t.get("kind") != "event" or str(t.get("task_id")) not in resolved:
            continue
        ev = resolution_event(str(t.get("source_ref")))
        close = _ts(t.get("resolves_after"))
        if close and is_release_event(ev):
            closes[ev] = max(close, closes.get(ev, close))
    missing = [f"{ev} (closed {c:%d %b})" for ev, c in sorted(closes.items(), key=lambda kv: kv[1])
               if ev not in have and ctx.now - c > timedelta(days=3)]
    out = []
    if dup:
        out.append(Finding(CLAUDE, "a release has its surprise recorded twice: " + ", ".join(dup),
                           severity="medium", playbook="resolve.surprise"))
    if missing:
        out.append(Finding(WATCH, "settled releases without a recorded surprise", severity="medium",
                           playbook="resolve.surprise", detail=missing,
                           steps=["Check the daily run's step 'Record the market surprise' (ci.steps)."]))
    return out or Finding(OK, f"{len(have)} settled releases have their surprise recorded")


# ======================================================================================
# ci -- GitHub Actions (public API, no login)
# ======================================================================================

def _gh(ctx: Ctx, path: str) -> Tuple[Any, str]:
    if ctx.flags.get("gh_limited"):
        return None, ctx.flags["gh_limited"]
    r = ctx.http.get(GITHUB_API + path, headers={"Accept": "application/vnd.github+json",
                                                  "X-GitHub-Api-Version": "2022-11-28"})
    if r.status in (403, 429) and r.headers.get("x-ratelimit-remaining") == "0":
        reset = datetime.fromtimestamp(int(r.headers.get("x-ratelimit-reset", "0") or 0), timezone.utc)
        ctx.flags["gh_limited"] = f"GitHub's hourly API allowance for this network is used up until {reset:%H:%M} UTC"
        return None, ctx.flags["gh_limited"]
    if not r.ok:
        return None, r.error or f"HTTP {r.status}"
    try:
        return r.json(), ""
    except ValueError:
        return None, "unreadable reply"


def _runs(ctx: Ctx) -> Tuple[Optional[List[dict]], str]:
    if "runs" not in ctx.flags:
        data, err = _gh(ctx, "/actions/runs?per_page=60")
        ctx.flags["runs"] = ((data or {}).get("workflow_runs") if data else None, err)
    return ctx.flags["runs"]


def _run_link(r: dict) -> str:
    return f"#{r.get('run_number')} {r.get('html_url', '')}"


@check("ci.runs", "Every recent GitHub Actions run passed", network=True,
       origin="every check-in from 09-03 read the runs list through the public API (gh is not installed)")
def _ci_runs(ctx: Ctx):
    runs, err = _runs(ctx)
    if runs is None:
        return Finding(WATCH if "allowance" in err else ERROR, f"could not read GitHub Actions: {err}",
                       severity="low", playbook="ci.runs")
    daily = [r for r in runs if r.get("name") == DAILY_WORKFLOW]
    tests = [r for r in runs if r.get("name") == TESTS_WORKFLOW]
    week = ctx.now - timedelta(days=7)
    out: List[Finding] = []
    for r in daily:
        created = _ts(r.get("created_at"))
        if not created or created < week or r.get("status") != "completed":
            continue
        if r.get("conclusion") not in ("success", "skipped", "neutral"):
            later = any(_ts(o.get("created_at")) and _ts(o.get("created_at")) > created
                        and o.get("conclusion") == "success" for o in daily)
            out.append(Finding(CLAUDE, f"daily run #{r.get('run_number')} ({created:%d %b %H:%M} UTC) ended "
                               f"'{r.get('conclusion')}'" + ("; a later run succeeded" if later else ""),
                               severity="medium" if later else "high", playbook="ci.runs",
                               detail=[r.get("html_url", "")]))
    ok_times = [_ts(r.get("created_at")) for r in daily if r.get("conclusion") == "success"]
    ok_times = [t for t in ok_times if t]
    if ok_times:
        last = max(ok_times)
        ctx.facts["last_daily_success"] = last.isoformat()
        hours = (ctx.now - last).total_seconds() / 3600
        if hours > 30:
            out.append(Finding(YOU, f"no successful collection run for {hours:.0f} hours", severity="critical",
                               playbook="ci.runs", steps=[
                                   f"Open {GITHUB_WEB}/actions and look for a yellow banner saying scheduled "
                                   "workflows are disabled; if there is one, click 'Enable'.",
                                   f"Then {GITHUB_WEB}/actions/workflows/daily.yml -> Run workflow -> Run workflow.",
                                   "Tell Claude, so it can find out why."]))
    running = [r for r in runs if r.get("status") in ("queued", "in_progress", "waiting", "pending")]
    for r in running:
        out.append(Finding(INFO, f"{r.get('name')} run #{r.get('run_number')} is {r.get('status')} now"))
    finished_tests = [r for r in tests if r.get("status") == "completed"]
    if finished_tests:
        t = finished_tests[0]
        ctx.facts["last_tests_run"] = {"number": t.get("run_number"), "conclusion": t.get("conclusion"),
                                       "sha": str(t.get("head_sha"))[:7]}
        if t.get("conclusion") not in ("success", "skipped", "cancelled"):
            out.append(Finding(CLAUDE, f"the tests workflow failed on {str(t.get('head_sha'))[:7]} "
                               f"({t.get('display_title', '')[:60]})", severity="high", playbook="ci.runs",
                               detail=[t.get("html_url", "")]))
    recent = [r for r in daily if (_ts(r.get("created_at")) or ctx.now) >= week]
    if not [f for f in out if f.status in (CLAUDE, YOU)]:
        latest = daily[0] if daily else None
        out.insert(0, Finding(OK, f"all {len(recent)} daily runs of the last week passed"
                              + (f"; latest #{latest.get('run_number')} at {_ts(latest.get('created_at')):%d %b %H:%M} UTC"
                                 if latest else "")))
    return out


def cron_slots(text: str) -> List[Tuple[int, int]]:
    """(hour, minute) of each daily cron in a workflow's text."""
    return sorted((int(h), int(m)) for m, h in re.findall(r"cron:\s*[\"']?(\d+)\s+(\d+)\s+\*\s+\*\s+\*", text))


def _cron_slots(ctx: Ctx) -> List[Tuple[int, int]]:
    """The slots GitHub actually ran: its copy of daily.yml, not an unpushed local edit."""
    shown = ctx.git("show", "origin/main:.github/workflows/daily.yml")
    text = shown.out if shown.ok else ""
    if not text:
        try:
            text = (ctx.root / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
        except OSError:
            text = ""
    return cron_slots(text) or [(13, 10), (20, 0)]


@check("ci.schedule", "The daily job gets its chances to run every day", network=True,
       origin="09-28: the 13:10 run never started; the evening backup alone collected the day")
def _ci_schedule(ctx: Ctx):
    runs, err = _runs(ctx)
    if runs is None:
        return None
    slots = _cron_slots(ctx)
    sched = [r for r in runs if r.get("name") == DAILY_WORKFLOW and r.get("event") == "schedule"]
    created = sorted(t for t in (_ts(r.get("created_at")) for r in sched) if t)
    if not created:
        return Finding(WATCH, "no scheduled daily runs found", severity="medium", playbook="ci.schedule")
    first_day = created[0].date()
    per_day = Counter(t.date() for t in created)
    days = [ctx.today - timedelta(days=k) for k in range(1, 14)]
    days = [d for d in days if d > first_day]
    single = [d for d in days if per_day.get(d, 0) == 1]
    none = [d for d in days if per_day.get(d, 0) == 0]
    delays: Dict[Tuple[int, int], List[float]] = defaultdict(list)
    crossed = []
    for t in created:
        cands = []
        for back in (0, 1):
            d = t.date() - timedelta(days=back)
            for h, m in slots:
                s = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
                if s <= t:
                    cands.append((s, (h, m)))
        if not cands:
            continue
        s, slot = max(cands)
        delays[slot].append((t - s).total_seconds() / 3600)
        if s.date() < t.date():
            crossed.append(f"{t:%d %b %H:%M} UTC (the {slot[0]:02d}:{slot[1]:02d} slot of {s:%d %b})")
    typical = {f"{h:02d}:{m:02d}": round(sorted(v)[len(v) // 2], 1) for (h, m), v in delays.items() if v}
    ctx.facts["cron_delay_hours_median"] = typical
    last_starts = defaultdict(list)
    for t in created:
        last_starts[t.date()].append(t)
    evening = [max(v) for d, v in last_starts.items() if d in days and len(v)]
    margin = sorted((24 * 60 - (t.hour * 60 + t.minute)) for t in evening)
    median_margin = margin[len(margin) // 2] if margin else None
    out = []
    detail = ["typical delay after each slot: " + ", ".join(f"{k} +{v} h" for k, v in sorted(typical.items()))]
    if median_margin is not None:
        detail.append(f"the day's last run typically starts {median_margin // 60} h {median_margin % 60:02d} min "
                      "before midnight UTC")
    if crossed:
        detail.append("started after midnight, so collected the NEXT day: " + ", ".join(crossed))
    detail.append(f"{len(slots)} daily slots on GitHub: " + ", ".join(f"{h:02d}:{m:02d}" for h, m in slots) + " UTC")
    try:
        here = cron_slots((ctx.root / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8"))
    except OSError:
        here = slots
    if here and here != slots:
        detail.append("this copy has " + ", ".join(f"{h:02d}:{m:02d}" for h, m in here)
                      + " UTC; GitHub runs them once they are pushed")
    if single or none:
        out.append(Finding(WATCH, "on " + ", ".join(f"{d:%d %b}" for d in sorted(single + none))
                           + " the day had one scheduled run or none",
                           severity="low", playbook="ci.schedule", detail=detail + [
                               "GitHub drops or delays scheduled runs under load; a day whose only run is "
                               "lost is lost for good. HEALTH-CHECK.md ci.schedule says what to do."]))
    else:
        out.append(Finding(OK, f"every one of the last {len(days)} days had at least two scheduled runs",
                           detail=detail))
    return out


@check("ci.steps", "No step fails quietly inside a green run", network=True,
       origin="09-24: steps marked continue-on-error can fail every day while the run stays green")
def _ci_steps(ctx: Ctx):
    runs, err = _runs(ctx)
    if runs is None:
        return None
    picked = [r for r in runs if r.get("name") == DAILY_WORKFLOW and r.get("status") == "completed"][:4]
    picked += [r for r in runs if r.get("name") == TESTS_WORKFLOW and r.get("status") == "completed"][:1]
    failures: Counter = Counter()
    jobs_seen = []
    for r in picked:
        data, e = _gh(ctx, f"/actions/runs/{r.get('id')}/jobs")
        if data is None:
            return Finding(INFO, f"could not read the runs' steps: {e}")
        for job in data.get("jobs", []):
            jobs_seen.append((r, job))
            for s in job.get("steps", []):
                c = s.get("conclusion")
                if c in ("success", None) or (c == "skipped" and s.get("name") not in ("Collect", "Commit the day")):
                    continue
                failures[(r.get("name"), s.get("name"), c)] += 1
    ctx.flags["jobs"] = jobs_seen
    if failures:
        return Finding(CLAUDE, "steps that did not succeed inside finished runs", severity="medium",
                       playbook="ci.steps", detail=[f"{w}: '{s}' {c} in {n} of the last runs"
                                                    for (w, s, c), n in failures.items()])
    return Finding(OK, f"every step of the last {len(picked)} runs succeeded")


@check("ci.annotations", "No warnings on the latest runs", network=True,
       origin="09-19: a Node 20 deprecation warning sat on every run, days before GitHub removed Node 20")
def _ci_annotations(ctx: Ctx):
    jobs = ctx.flags.get("jobs") or []
    picked, seen_workflows = [], set()
    for r, job in jobs:
        if r.get("name") not in seen_workflows:
            seen_workflows.add(r.get("name"))
            picked.append(job)
    notes = []
    for job in picked:
        data, e = _gh(ctx, f"/check-runs/{job.get('id')}/annotations")
        if data is None:
            return Finding(INFO, f"could not read annotations: {e}")
        for a in data:
            if a.get("annotation_level") in ("warning", "failure"):
                notes.append(f"{a.get('annotation_level')}: {(a.get('message') or '')[:240]}")
    notes = sorted(set(notes))
    if notes:
        return Finding(CLAUDE, f"{_plural(len(notes), 'warning')} on the latest runs", severity="medium",
                       playbook="ci.annotations", detail=notes[:8])
    return Finding(OK, "no warnings or failures annotated on the latest runs")


@check("ci.pins", "The workflows run on a named image, supported action runtimes and Python 3.11",
       network=True, origin="09-19: ubuntu-latest moves to 26.04 from 19 Oct; Node 20 removed 23 Sep")
def _ci_pins(ctx: Ctx):
    wf_dir = ctx.root / ".github" / "workflows"
    out = []
    cache = ctx.state.setdefault("cache", {}).setdefault("action_runtime", {})
    uses, runs_on = set(), set()
    for wf in sorted(wf_dir.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        runs_on |= set(re.findall(r"runs-on:\s*([\w.-]+)", text))
        uses |= set(re.findall(r"uses:\s*([\w.-]+/[\w.-]+)@([\w.-]+)", text))
    if "ubuntu-latest" in runs_on:
        out.append(Finding(CLAUDE, "a workflow runs on ubuntu-latest, which GitHub moves to Ubuntu 26.04 "
                           "mid-study", severity="medium", playbook="ci.pins",
                           steps=["Pin runs-on: ubuntu-24.04, as daily.yml does."]))
    old = []
    for repo, ref in sorted(uses):
        key = f"{repo}@{ref}"
        hit = cache.get(key)
        if not hit or (_ts(hit.get("at")) or ctx.now) < ctx.now - timedelta(days=7):
            using = None
            for fname in ("action.yml", "action.yaml"):
                r = ctx.http.get(f"https://raw.githubusercontent.com/{repo}/{ref}/{fname}")
                if r.ok:
                    m = re.search(r"^\s*using:\s*[\"']?([\w.-]+)", r.text, re.M)
                    using = m.group(1) if m else "unknown"
                    break
            if using is None:
                continue
            hit = cache[key] = {"using": using, "at": ctx.now.isoformat()}
        if hit["using"] in ("node12", "node16", "node20"):
            old.append(f"{key} runs on {hit['using']}")
    if old:
        out.append(Finding(CLAUDE, "actions on a Node runtime GitHub has removed", severity="medium",
                           playbook="ci.pins", detail=old))
    manifest = ctx.state.setdefault("cache", {}).get("py311_ubuntu2404")
    if not manifest or (_ts(manifest.get("at")) or ctx.now) < ctx.now - timedelta(days=7):
        r = ctx.http.get(PYTHON_VERSIONS_MANIFEST)
        if r.ok:
            try:
                versions = [v["version"] for v in r.json() if v.get("version", "").startswith("3.11.")
                            and any(f.get("platform") == "linux" and f.get("platform_version") == "24.04"
                                    for f in v.get("files", []))]
            except (ValueError, TypeError, KeyError):
                versions = []
            manifest = ctx.state["cache"]["py311_ubuntu2404"] = {"latest": versions[0] if versions else None,
                                                                  "at": ctx.now.isoformat()}
    if manifest and manifest.get("latest") is None:
        out.append(Finding(CLAUDE, "setup-python lists no Python 3.11 for ubuntu-24.04", severity="high",
                           playbook="ci.pins"))
    return out or Finding(OK, f"runners {', '.join(sorted(runs_on))}; {len(uses)} actions on current runtimes; "
                          f"Python 3.11 available ({(manifest or {}).get('latest') or '?'})")


# ======================================================================================
# plan -- the registered plan and its public copies
# ======================================================================================

@check("plan.freeze", "The registered plan is unchanged outside section 11",
       origin="every check-in since 09-03 ran scripts/freeze_prereg.py --check")
def _plan_freeze(ctx: Ctx):
    from scripts import freeze_prereg as fz
    doc = ctx.root / "PREREGISTRATION.md"
    text = doc.read_text(encoding="utf-8")
    h, recorded, body = fz.digest(text), fz.recorded_hash(text), fz.body_digest(text)
    devs = fz.logged_deviations(text)
    numbers = sorted(int(c[0]) for c in devs if c and c[0].isdigit())
    ctx.facts["deviations"] = len(devs)
    ctx.flags["deviation_numbers"] = numbers
    out = []
    if recorded and h == recorded:
        out.append(Finding(OK, "intact: matches the registered hash exactly"))
    elif body == fz.REGISTERED_BODY_SHA and devs:
        out.append(Finding(OK, f"intact outside section 11 ({len(devs)} deviations logged)"))
    else:
        return Finding(CLAUDE, "PREREGISTRATION.md changed outside section 11", severity="critical",
                       playbook="plan.freeze", steps=[
                           "git log -p -- PREREGISTRATION.md to find the edit, and undo it.",
                           "Anything that genuinely changed belongs in section 11 as a dated row."])
    if numbers and numbers != list(range(1, max(numbers) + 1)):
        out.append(Finding(WATCH, f"deviation numbers are not 1..{max(numbers)} without gaps: {numbers}",
                           severity="low", playbook="plan.freeze"))
    before = _seen(ctx).get("deviations")
    if isinstance(before, int) and len(devs) > before:
        new = [c for c in devs if c and c[0].isdigit() and int(c[0]) > before]
        out.append(Finding(INFO, f"new since the last check: {', '.join('deviation ' + c[0] + ' (' + c[1] + ')' for c in new)}",
                           playbook="plan.freeze"))
    _seen(ctx)["deviations"] = len(devs)
    return out


def _addendum_state(ctx: Ctx) -> Dict[str, Optional[bool]]:
    return ctx.flags.setdefault("addendum", {"zenodo": None, "osf_wiki": None, "osf_files": None})


@check("plan.registration", "The OSF registration is public and not withdrawn", network=True,
       origin="09-23: 'public, withdrawn=False, registered 08-29' -- never edit or withdraw it")
def _plan_registration(ctx: Ctx):
    r = ctx.http.get(f"{OSF_API}/registrations/{OSF_REGISTRATION}/")
    if not r.ok:
        return Finding(WATCH, f"could not read osf.io/{OSF_REGISTRATION} ({r.error or r.status})",
                       severity="low", playbook="plan.registration")
    try:
        a = r.json()["data"]["attributes"]
    except (ValueError, KeyError, TypeError):
        return Finding(WATCH, "OSF answered in an unexpected shape", severity="low")
    if a.get("withdrawn") or a.get("pending_withdrawal"):
        return Finding(YOU, "the OSF registration is withdrawn or being withdrawn", severity="critical",
                       playbook="plan.registration",
                       steps=["Do not confirm any withdrawal. Contact OSF support (osf.io/support) at once."])
    if a.get("public") is False:
        return Finding(YOU, "the OSF registration is not public", severity="critical",
                       playbook="plan.registration",
                       steps=[f"Open osf.io/{OSF_REGISTRATION} while logged in and check its status; "
                              "contact OSF support if it is not public."])
    return Finding(OK, f"osf.io/{OSF_REGISTRATION} is public, not withdrawn, registered "
                   f"{str(a.get('date_registered'))[:10]}")


@check("plan.zenodo", "The Zenodo record and its versions", network=True,
       origin="09-13 to 09-23: 'Zenodo has only v1.0-prereg' -- how the unposted addendum is detected")
def _plan_zenodo(ctx: Ctx):
    r = ctx.http.get(ZENODO_VERSIONS)
    if not r.ok:
        return Finding(WATCH, f"could not read Zenodo ({r.error or r.status})", severity="low")
    try:
        hits = r.json()["hits"]["hits"]
    except (ValueError, KeyError, TypeError):
        return Finding(WATCH, "Zenodo answered in an unexpected shape", severity="low")
    versions = [(h.get("metadata", {}).get("version") or "?", h.get("metadata", {}).get("publication_date") or "?")
                for h in hits]
    posted = any("addendum" in v.lower() for v, _ in versions) or len(versions) > 1
    _addendum_state(ctx)["zenodo"] = posted
    ctx.facts["zenodo_versions"] = [v for v, _ in versions]
    return Finding(OK, f"doi:10.5281/zenodo.{ZENODO_RECORD}: {_plural(len(versions), 'version')} "
                   f"({', '.join(v for v, _ in versions)})")


@check("plan.osf_project", "The OSF project's files and wiki", network=True,
       origin="09-19 to 09-23: 'OSF 965dz wiki has 0 pages, files unchanged since 08-24'")
def _plan_osf_project(ctx: Ctx):
    w = ctx.http.get(f"{OSF_API}/nodes/{OSF_PROJECT}/wikis/")
    f = ctx.http.get(f"{OSF_API}/nodes/{OSF_PROJECT}/files/osfstorage/")
    if not (w.ok and f.ok):
        return Finding(WATCH, f"could not read the OSF project ({w.error or w.status}, {f.error or f.status})",
                       severity="low")
    try:
        pages = [p["attributes"]["name"] for p in w.json().get("data", [])]
        files = [(x["attributes"]["name"], str(x["attributes"].get("date_modified"))[:10]) for x in f.json().get("data", [])]
    except (ValueError, KeyError, TypeError):
        return Finding(WATCH, "OSF answered in an unexpected shape", severity="low")
    st = _addendum_state(ctx)
    st["osf_wiki"] = any("addendum 1" in p.lower() for p in pages)
    st["osf_files"] = any(n.upper().startswith("OSF-ADDENDUM-1") for n, _ in files)
    return Finding(OK, f"osf.io/{OSF_PROJECT}: {_plural(len(pages), 'wiki page')}, {_plural(len(files), 'file')}",
                   detail=[f"{n} ({d})" for n, d in files])


@check("plan.addendum_scope", "The addendum covers every deviation logged so far",
       origin="09-16 and 09-19: each new deviation had to be folded into the unposted addendum")
def _plan_addendum_scope(ctx: Ctx):
    path = ctx.root / "OSF-ADDENDUM-1.md"
    numbers = ctx.flags.get("deviation_numbers") or []
    if not path.exists() or not numbers:
        return None
    covered = [int(n) for n in re.findall(r"deviations 1[-–](\d+)", path.read_text(encoding="utf-8"))]
    top = max(numbers)
    st = _addendum_state(ctx)
    posted = bool(st.get("zenodo")) and bool(st.get("osf_wiki") or st.get("osf_files"))
    if not covered:
        return Finding(INFO, "OSF-ADDENDUM-1.md does not state the range of deviations it covers")
    if posted and top > max(covered):
        return Finding(CLAUDE, f"deviations {max(covered) + 1}-{top} came after Addendum 1 was posted",
                       severity="medium", playbook="plan.addendum_scope",
                       steps=["Draft OSF-ADDENDUM-2.md in the same form as the first, then give the student "
                              "the posting steps."])
    if not posted and (max(covered) != top or min(covered) != top):
        return Finding(CLAUDE, f"OSF-ADDENDUM-1.md says 'deviations 1-{max(covered)}' but section 11 has {top}",
                       severity="medium", playbook="plan.addendum_scope",
                       steps=["Fold the new deviations into OSF-ADDENDUM-1.md before it is posted."])
    return Finding(OK, f"the addendum covers deviations 1-{top}, every one logged")


@check("plan.docs", "The public documents' numbers still match the study",
       origin="09-16 and 09-19 refreshed stale test counts and deviation ranges in README.md")
def _plan_docs(ctx: Ctx):
    readme = ctx.root / "README.md"
    if not readme.exists():
        return None
    text = readme.read_text(encoding="utf-8")
    out = []
    numbers = ctx.flags.get("deviation_numbers") or []
    for n in re.findall(r"deviations 1[-–](\d+)", text):
        if numbers and int(n) != max(numbers):
            out.append(f"README.md says 'deviations 1-{n}'; section 11 has {max(numbers)}")
    tests = ctx.facts.get("tests") or {}
    total = sum(tests.get(k, 0) for k in ("passed", "failed", "skipped"))
    for n in re.findall(r"about (\d+) tests", text):
        if total and abs(int(n) - total) > 0.1 * total:
            out.append(f"README.md says 'about {n} tests'; there are {total}")
    if out:
        return Finding(CLAUDE, "public documents quote numbers that are out of date", severity="low",
                       playbook="plan.docs", detail=out)
    return Finding(OK, "README.md's deviation range and test count are current")


# ======================================================================================
# code -- tests and the registered pipelines, blind
# ======================================================================================

BACKGROUND_JOBS = {
    "pytest": "code.tests",
    "analyze": "code.blind_analysis",
    "rehearsal": "code.rehearsal",
}


def _start_background(ctx: Ctx, selected: Iterable[str]) -> None:
    if ctx.quick:
        return
    wanted = set(selected)
    if "code.tests" in wanted:
        ctx.bg.start("pytest", [ctx.python, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider", "-rfE"],
                     ctx.root, env=_quiet_env(), timeout=1200)
    if "code.blind_analysis" in wanted:
        (ctx.tmp / "analysis").mkdir(parents=True, exist_ok=True)
        _script(ctx, "analyze.py", "--n-boot", "25", "--out", str(ctx.tmp / "analysis" / "blind.json"),
                background="analyze", timeout=900)
    if "code.rehearsal" in wanted:
        _script(ctx, "week5_prediction.py", background="rehearsal", timeout=600)


def week5_findings(text: str, rc: int, now: datetime) -> Tuple[List[Finding], Dict[str, bool]]:
    """What `week5_prediction.py --check` said, sorted into expected waiting and real problems."""
    from neff import prediction
    opens = _ts(prediction.PUBLISH_NOT_BEFORE)
    text = _strip_ansi(text)
    if "already published" in text:
        return [Finding(OK, "the Week-5 prediction is published")], {"done": True}
    if "READY: run" in text:
        return [Finding(YOU, "publish the Week-5 prediction now -- the record is ready and the window is open",
                        severity="critical", playbook="code.week5_check", due=(opens + timedelta(days=2)).isoformat(),
                        steps=["Tell Claude \"publish the week 5 prediction\" -- or, in Terminal in the r1 folder:",
                               "git pull --ff-only",
                               "./.venv/bin/python scripts/week5_prediction.py --check     (must say READY)",
                               "./.venv/bin/python scripts/week5_prediction.py --publish",
                               "Then follow the steps it prints, the same day: commit and push predictions/, "
                               "and post the SHA-256 on Zenodo and the OSF wiki."])], {"ready": True}
    if "window has not opened" in text:
        return [Finding(OK, "the record is current; the publish window has not opened")], {}
    problems = [ln.strip()[2:] for ln in text.splitlines() if ln.strip().startswith("- ")]
    expected, real = [], []
    for prob in problems:
        waiting = now < opens and ("collection is not in this copy yet" in prob
                                   or "inside the calibration window" in prob
                                   or "Publish after it has settled" in prob)
        if waiting or ("could not read" in prob and "Kalshi" in prob):
            expected.append(prob)
        else:
            real.append(prob)
    out = []
    if real:
        out.append(Finding(CLAUDE, "the Week-5 check names a problem that is not just waiting for 2 Oct",
                           severity="high" if now >= opens - timedelta(days=3) else "medium",
                           playbook="code.week5_check", detail=real[:6], due=prediction.PUBLISH_NOT_BEFORE))
    if expected:
        out.append(Finding(KNOWN, f"NOT READY for {_plural(len(expected), 'expected reason')} only: it waits for "
                           "2 Oct's collection and the September payrolls settlement", detail=expected[:4],
                           playbook="code.week5_check"))
    if not problems and rc != 0:
        out.append(Finding(ERROR, "week5_prediction.py --check failed", severity="medium",
                           detail=_tail(text, 8), playbook="code.week5_check"))
    return out, {}


@check("code.week5_check", "The Week-5 publisher would run from this copy (read-only --check)",
       network=True, origin="09-19 (deviation 22): the publisher refuses a copy that is not current; "
                            "09-22/23: 'NOT READY for the two expected reasons only'")
def _code_week5_check(ctx: Ctx):
    from neff import prediction
    if ctx.now > _ts(prediction.PUBLISH_NOT_BEFORE) + timedelta(days=60):
        return None
    p = _script(ctx, "week5_prediction.py", "--check", timeout=420)
    findings, flags = week5_findings(p.out + "\n" + p.err, p.rc, ctx.now)
    if flags.get("ready"):
        ctx.flags["week5_ready"] = True
    if flags.get("done"):
        ctx.flags["week5_done"] = True
    return findings


@check("code.milestones", "Dated commitments only a person can keep",
       origin="09-16: nothing in the repository mentioned the one-shot dates; scripts/milestones.py")
def _code_milestones(ctx: Ctx):
    work = ctx.tmp / "milestones"
    work.mkdir(parents=True, exist_ok=True)
    p = _script(ctx, "milestones.py", "--json", cwd=work, timeout=120)
    try:
        data = json.loads((work / "milestones.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Finding(ERROR, "scripts/milestones.py did not produce its report", severity="medium",
                       detail=_tail(p.out + p.err, 6), playbook="code.milestones")
    out = []
    for m in data.get("milestones", []):
        opens = _ts(m.get("opens"))
        state = m.get("state")
        if m.get("key") == "week5_prediction" and (ctx.flags.get("week5_ready") or ctx.flags.get("week5_done")):
            continue
        if state in ("due", "overdue"):
            out.append(Finding(YOU, f"{m['title']} -- {state.replace('_', ' ')} (window opened {_when(opens)})",
                               severity="critical", steps=list(m.get("how") or []), due=m.get("opens"),
                               playbook="code.milestones", detail=[m.get("detail") or ""]))
        elif state == "due_soon":
            out.append(Finding(YOU, f"{m['title']}: {_when(opens)}, in {_plural(m.get('days_until', 0), 'day')}",
                               severity="medium", steps=["Put it in your calendar. On the day, open a session "
                                                         "and Claude runs it with you:"] + list(m.get("how") or []),
                               due=m.get("opens"), playbook="code.milestones", detail=[m.get("detail") or ""]))
        elif state == "pending":
            out.append(Finding(INFO, f"{m['title']}: {opens:%d %b %Y} (in {m.get('days_until')} days)"))
        elif state == "done":
            out.append(Finding(OK, f"{m['title']}: done"))
    return out


@check("code.preflight", "scripts/preflight.py agrees nothing is missing",
       origin="08-21 onward: the readiness report (keys, verified models, push, OSF URL committed)")
def _code_preflight(ctx: Ctx):
    p = _script(ctx, "preflight.py", timeout=180)
    text = _strip_ansi(p.out)
    todo = [ln.strip() for ln in text.splitlines() if "[TODO]" in ln]
    real = [t for t in todo if "Pushed to a public GitHub repo" not in t and "API keys" not in t]
    out = []
    if real:
        out.append(Finding(CLAUDE, "preflight reports something missing", severity="medium",
                           playbook="code.preflight", detail=real))
    if any("API keys" in t for t in todo):
        out.append(Finding(INFO, "not all four API keys are in .env on this Mac (GitHub uses its own secrets; "
                           "the local copies are only for checks run here)"))
    if any("Pushed" in t for t in todo):
        out.append(Finding(KNOWN, "preflight says 'not pushed' -- the same unpushed local commits that "
                           "repo.sync lists", playbook="code.preflight"))
    return out or Finding(OK, "preflight: everything done")


@check("code.tests", "The full test suite passes here",
       origin="every check-in ran the suite; the daily job runs it before spending, so a failing test "
              "costs a collection day")
def _code_tests(ctx: Ctx):
    job = ctx.bg.wait("pytest")
    if job is None:
        return Finding(SKIP, "not run (--quick)") if ctx.quick else None
    counts = _pytest_summary(job.out)
    ctx.facts["tests"] = dict(counts, seconds=round(job.seconds))
    collected = sum(counts.get(k, 0) for k in ("passed", "failed", "skipped", "error"))
    before = _seen(ctx).get("tests_collected")
    out = []
    if job.rc == 0:
        out.append(Finding(OK, f"{counts.get('passed', 0)} passed, {counts.get('skipped', 0)} skipped "
                           f"({job.seconds:.0f} s, Python {_py_version(ctx)})"))
        if isinstance(before, int) and collected < before:
            out.append(Finding(WATCH, f"{before - collected} fewer tests than at the last check", severity="low",
                               playbook="code.tests"))
        _seen(ctx)["tests_collected"] = collected
    else:
        failing = _failing_tests(job.out)
        out.append(Finding(CLAUDE, f"the test suite fails here: {counts.get('failed', 0)} failed, "
                           f"{counts.get('error', 0)} errors" if counts else "the test suite did not finish",
                           severity="critical", playbook="code.tests",
                           detail=(failing[:15] or _tail(job.out + job.err, 12)),
                           steps=["Fix before the next 13:10 UTC run: the daily job runs this suite before it "
                                  "collects, and a failure there loses the day.",
                                  "Confirm on CI's Python: ./.venv/bin/python scripts/health_check.py --deep --only deep.ci_parity"]))
    return out


def _py_version(ctx: Ctx) -> str:
    p = _run([ctx.python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], ctx.root, timeout=30)
    return p.out.strip() or "?"


@check("code.blind_analysis", "Every registered analysis runs end to end -- blind",
       origin="09-13 and 09-16 ran scripts/analyze.py blind; December's look is the same code")
def _code_blind_analysis(ctx: Ctx):
    job = ctx.bg.wait("analyze")
    if job is None:
        return Finding(SKIP, "not run (--quick)") if ctx.quick else None
    try:
        result = json.loads((ctx.tmp / "analysis" / "blind.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result = {}
    if job.rc == 0 and result.get("blind") is True:
        return Finding(OK, f"primary estimate, the always-reported quantities and H1-H6 all ran on permuted "
                       f"outcomes ({job.seconds:.0f} s); no number from it is shown")
    return Finding(CLAUDE, "the registered analysis did not run end to end (blind)", severity="high",
                   playbook="code.blind_analysis", detail=_tail(job.err or job.out, 10),
                   steps=["The Week-5 fit and the December look run this code; fix it now. "
                          "Never test it unblinded on the real record: tests/test_unblinded_path.py."])


@check("code.rehearsal", "The Week-5 prediction pipeline runs, as a rehearsal on permuted outcomes",
       origin="09-19: the blind rehearsal of the Week-5 calibration")
def _code_rehearsal(ctx: Ctx):
    job = ctx.bg.wait("rehearsal")
    if job is None:
        return Finding(SKIP, "not run (--quick)") if ctx.quick else None
    if job.rc == 0 and "REHEARSAL" in job.out:
        return Finding(OK, "the rehearsal ran; its numbers are meaningless by design and are not shown")
    from neff import prediction
    return Finding(CLAUDE, "the Week-5 rehearsal failed", severity="high", playbook="code.rehearsal",
                   detail=_tail(job.err or job.out, 8), due=prediction.PUBLISH_NOT_BEFORE)


# ======================================================================================
# money
# ======================================================================================

def _last_ask_day() -> date:
    try:
        from scripts.check_days import LAST_ASK_DAY
        return LAST_ASK_DAY
    except Exception:                                                  # noqa: BLE001
        return date.fromisoformat(config.DATA_FREEZE) - timedelta(days=4)


def _asking_days_left(ctx: Ctx) -> List[date]:
    """Days still to be collected, from today (if not collected yet) to the last asking day."""
    start = ctx.today if ctx.today.isoformat() not in set(ctx.days_collected()) else ctx.today + timedelta(days=1)
    end = _last_ask_day()
    n = (end - start).days + 1
    return [start + timedelta(days=k) for k in range(max(0, n))]


@check("money.budget", "Spend against the $200 cap and the arm's cap, now and at the end",
       origin="the daily job's budget guard fails a run above 85%; 09-21 to 09-23 projected the spend")
def _money_budget(ctx: Ctx):
    from neff.ledger import Ledger
    led = Ledger(ctx.path("ledger"), cap_usd=config.BUDGET_USD, arm_caps=dict(config.ARM_CAPS_USD))
    s = led.summary()
    spent = float(s.get("spent_usd", 0))
    per_day: Dict[str, float] = defaultdict(float)
    for r in ctx.rows("ledger"):
        if r.get("arm") == config.PRIMARY_ARM:
            per_day[str(r.get("ts", ""))[:10]] += float(r.get("usd") or 0)
    complete = [d for d in sorted(per_day) if d < ctx.today.isoformat()][-7:]
    rate = sum(per_day[d] for d in complete) / len(complete) if complete else 0.0
    left = len(_asking_days_left(ctx))
    projected = spent + rate * left
    arm_spent = float((s.get("by_arm") or {}).get(config.PRIMARY_ARM, 0))
    arm_cap = config.ARM_CAPS_USD.get(config.PRIMARY_ARM, config.BUDGET_USD)
    ctx.facts["spend"] = {"spent": round(spent, 2), "per_day": round(rate, 4), "asking_days_left": left,
                          "projected_at_end": round(projected, 2), "cap": config.BUDGET_USD}
    line = (f"spent {_money(spent)} of {_money(config.BUDGET_USD)} ({s.get('pct_used')}%); "
            f"{_money(rate)} a day; about {_money(projected)} by the last question ({left} days left)")
    pct = float(s.get("pct_used") or 0)
    if pct > 85:
        return Finding(CLAUDE, line, severity="critical", playbook="money.budget",
                       detail=["The daily job's budget guard fails every run above 85%."])
    if pct > 60 or projected > 0.85 * config.BUDGET_USD or arm_spent + rate * left > 0.9 * arm_cap:
        return Finding(WATCH, line, severity="medium", playbook="money.budget")
    return Finding(OK, line)


def _openrouter_key(ctx: Ctx) -> Optional[str]:
    key = os.environ.get("OPENROUTER_API_KEY")
    env = ctx.root / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    return key or None


@check("money.openrouter", "OpenRouter's balance, read live", network=True,
       origin="09-21 to 09-23 read /api/v1/credits with the key in .env (never printed)")
def _money_openrouter(ctx: Ctx):
    key = _openrouter_key(ctx)
    if not key:
        return Finding(INFO, "no OpenRouter key on this Mac, so its balance is estimated instead")
    r = ctx.http.get(f"{OPENROUTER_API}/credits", headers={"Authorization": f"Bearer {key}"})
    if not r.ok:
        return Finding(WATCH, f"OpenRouter did not give the balance ({r.error or r.status})", severity="low")
    try:
        d = r.json()["data"]
        left = float(d["total_credits"]) - float(d["total_usage"])
    except (ValueError, KeyError, TypeError):
        return Finding(WATCH, "OpenRouter answered in an unexpected shape", severity="low")
    ctx.flags["openrouter_balance"] = left
    ctx.state.setdefault("balances", {})["openrouter"] = {"usd": round(left, 4), "as_of": ctx.now.isoformat(),
                                                          "source": "live"}
    return Finding(OK, f"OpenRouter: {_money(left)} left (read live)")


@check("money.balances", "Each API account has enough left to reach the last question",
       origin="09-22: per-account spend rates against the balances the student read out")
def _money_balances(ctx: Ctx):
    obs = ctx.rows("observations")
    complete = [d for d in ctx.days_collected() if d < ctx.today.isoformat()][-7:]
    index = ctx.task_index()
    rate: Dict[Tuple[str, bool], float] = defaultdict(float)
    spent_since: Dict[str, float] = defaultdict(float)
    balances = ctx.state.get("balances") or {}
    as_of = {v: _ts(b.get("as_of")) for v, b in balances.items()}
    for o in obs:
        usd = float(o.get("usd") or 0)
        vendor = VENDOR_OF_PROVIDER.get(str(o.get("provider")))
        created = _ts(o.get("created_at"))
        if vendor and created and as_of.get(vendor) and created > as_of[vendor]:
            spent_since[vendor] += usd
        t = index.get(str(o.get("task_id")))
        day = Ctx.task_day(t) if t else ""
        if day in complete:
            rate[(o.get("model_key"), int(o.get("prompt_variant", 0) or 0) == config.BRIDGE_VARIANT)] += usd
    n = max(1, len(complete))
    need = vendor_need({k: v / n for k, v in rate.items()}, _asking_days_left(ctx))
    out, lines, unknown = [], [], []
    for vendor in ("anthropic", "openai", "google", "openrouter"):
        want = need.get(vendor, 0.0)
        b = balances.get(vendor)
        if vendor == "openrouter" and ctx.flags.get("openrouter_balance") is not None:
            est, how = ctx.flags["openrouter_balance"], "live"
        elif b:
            est = float(b.get("usd", 0)) - spent_since.get(vendor, 0.0)
            how = f"you read {_money(float(b.get('usd', 0)))} on {str(b.get('as_of'))[:10]}"
        else:
            est, how = None, None
        name = VENDOR_NAMES[vendor]
        if est is None:
            lines.append(f"{name}: needs about {_money(want)} more; balance unknown")
            unknown.append(vendor)
            continue
        lines.append(f"{name}: about {_money(est)} left ({how}); needs about {_money(want)} to the last question")
        if est < want * 1.2:
            short = max(5.0, math.ceil(want * 1.5 - est))
            out.append(Finding(YOU, f"{name} may run out before the last question: about {_money(est)} left, "
                               f"about {_money(want)} needed", severity="high", playbook="money.balances",
                               steps=[f"Add about {_money(short)}:"] + VENDOR_TOPUP[vendor] +
                               ["Tell Claude the new balance."]))
        elif est < want * 1.5:
            out.append(Finding(WATCH, f"{name}: the margin is getting thin ({_money(est)} left for "
                               f"{_money(want)} needed)", severity="low", playbook="money.balances"))
    if unknown:
        names = ", ".join(VENDOR_NAMES[v] for v in unknown)
        out.append(Finding(YOU, f"tell Claude your balance{'s' if len(unknown) > 1 else ''} once ({names}), so running "
                           "out can be seen coming", severity="low", playbook="money.balances",
                           steps=[s for v in unknown for s in _balance_steps(v)] + [
                               "Tell Claude the numbers; it records them with: scripts/health_check.py --balance "
                               + " ".join(f"{v}=<amount>" for v in unknown)]))
    ctx.facts["balances"] = lines
    covered = not [f for f in out if f.status in (YOU, WATCH)]
    out.insert(0, Finding(OK if covered else INFO,
                          "every account covers the rest of the study" if covered
                          else "account balances against what is left to spend", detail=lines))
    return out


def vendor_need(daily_rate: Dict[Tuple[str, bool], float], days: Iterable[date]) -> Dict[str, float]:
    """What each account still pays, following each model's registered route day by day.

    `daily_rate[(model_key, is_bridge)]` is the model's spend per day. From a route's
    start the model would bill the route's vendor; the bridge bills its route's vendor
    while it runs (to 13 Oct); a retired member costs nothing (gpt_small from 23 Oct).
    """
    need: Dict[str, float] = defaultdict(float)
    for d in days:
        iso = d.isoformat()
        for key, spec in config.panel_by_key().items():
            if not spec.enabled or config.retired(spec, iso):
                continue
            need[VENDOR_OF_PROVIDER.get(config.routed(spec, iso).provider, "")] += daily_rate.get((key, False), 0.0)
            bridge = config.bridge_spec(spec, iso)
            if bridge is not None:
                need[VENDOR_OF_PROVIDER.get(bridge.provider, "")] += daily_rate.get((key, True), 0.0)
    return dict(need)


def _balance_steps(vendor: str) -> List[str]:
    return {
        "anthropic": ["platform.claude.com -> Billing: the credit balance is at the top."],
        "openai": ["platform.openai.com -> Settings (gear) -> Billing: 'Credit balance'."],
        "google": ["aistudio.google.com -> Billing: the 'Available credits' card."],
        "openrouter": ["openrouter.ai -> Credits."],
    }.get(vendor, [])


# ======================================================================================
# vendors -- retirements and hosts
# ======================================================================================

_MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
           "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
DATE_RE = re.compile(rf"\b(?:({_MONTHS})\.?\s+(\d{{1,2}}),\s+(\d{{4}})|(\d{{4}})-(\d{{2}})-(\d{{2}}))\b")
_MONTH_NO = {m.lower()[:3]: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _dates_in(text: str) -> List[date]:
    out = []
    for m in DATE_RE.finditer(text):
        try:
            if m.group(1):
                out.append(date(int(m.group(3)), _MONTH_NO[m.group(1).lower()[:3]], int(m.group(2))))
            else:
                out.append(date(int(m.group(4)), int(m.group(5)), int(m.group(6))))
        except (ValueError, KeyError):
            continue
    return out


def page_text(raw_html: str) -> str:
    s = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", raw_html)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_lib.unescape(s).replace("‑", "-").replace("‐", "-").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _aliases(model_id: str) -> List[str]:
    tail = model_id.split("/")[-1]
    out = [tail]
    undated = re.sub(r"-(\d{4}-\d{2}-\d{2}|\d{8})$", "", tail)
    if undated != tail:
        out.append(undated)
    return out


def retirement_rows(vendor: str, text: str, model_id: str) -> List[Dict[str, Any]]:
    """The rows of a vendor's retirement page that are about `model_id` itself.

    Each vendor lays its page out differently, and every page also names models as
    *replacements* for others. So a row is taken only where the page's own layout
    says it describes this model: Anthropic's status table (id, status, dates),
    OpenAI's shutdown tables (a date, then the models it shuts down), Google's model
    table (id, release date, shutdown), Azure's retirement table.
    """
    rows = []
    for alias in _aliases(model_id):
        esc = re.escape(alias) + r"(?![\w.*-])"
        if vendor == "anthropic":
            for m in re.finditer(esc + r"\s+(Active|Legacy|Deprecated|Retired)\b(.{0,120}?)"
                                 r"(?=\s+claude-|\s+Deprecation history|$)", text):
                rest = m.group(2)
                not_sooner = re.search(r"Not sooner than\s+(" + DATE_RE.pattern + ")", rest)
                rows.append({"row": f"{alias} {m.group(1)}{rest}", "status": m.group(1),
                             "not_sooner": (_dates_in(not_sooner.group(1)) or [None])[0] if not_sooner else None,
                             "dates": [d for d in _dates_in(rest)
                                       if not not_sooner or d not in _dates_in(not_sooner.group(1))]})
        elif vendor == "openai":
            for m in re.finditer(esc, text):
                pre = text[max(0, m.start() - 110):m.start()]
                found = list(DATE_RE.finditer(pre))
                if not found:
                    continue
                between = pre[found[-1].end():]
                if " or " in between or not re.fullmatch(r"[\s\w.\-|,/()]*", between) or len(between) > 90:
                    continue
                rows.append({"row": (pre[found[-1].start():] + text[m.start():m.end() + 40]).strip(),
                             "status": "shutdown", "dates": _dates_in(found[-1].group(0)), "not_sooner": None})
        elif vendor == "google":
            # "<id> <release date> <shutdown date | No shutdown date announced>"
            for m in re.finditer(esc + r"\s+(" + DATE_RE.pattern + r")\s+(No shutdown date announced|"
                                 + DATE_RE.pattern + ")", text):
                rest = text[m.end(1) - len(m.group(1)):m.end()]
                shutdown = [] if "No shutdown" in rest else _dates_in(rest)[1:]
                rows.append({"row": f"{alias} {rest}", "status": "listed", "dates": shutdown,
                             "not_sooner": None, "no_shutdown": "No shutdown" in rest})
        elif vendor == "azure":
            # The base-model table: "<id> <version> <lifecycle> <retirement date> <replacement>".
            # The fine-tuned table puts "No earlier than" after the version, and is not this.
            for m in re.finditer(esc + r"\s+(\d{4}-\d{2}-\d{2})\s+(GA|Preview|Legacy|Deprecated|Retired)\s+"
                                 r"(\d{4}-\d{2}-\d{2}|\u2014|-)", text):
                version, lifecycle, retires = m.group(1), m.group(2), m.group(3)
                rows.append({"row": f"{alias} {version} {lifecycle} retires {retires}", "status": lifecycle,
                             "version": version, "dates": _dates_in(retires), "not_sooner": None})
        if rows:
            break
    return rows


def assess_retirement(ctx: Ctx, vendor: str, key: str, model_id: str, rows: List[dict],
                      handled_until: Optional[date], handled_how: str = "") -> List[Finding]:
    freeze = date.fromisoformat(config.DATA_FREEZE)
    out: List[Finding] = []
    label = f"{key} ({model_id})"
    if not rows:
        return [Finding(OK, f"{label}: not on {vendor}'s retirement page")]
    for r in rows:
        status = r.get("status")
        dates = [d for d in r.get("dates", []) if d >= ctx.today - timedelta(days=1)]
        if vendor == "anthropic":
            if status in ("Deprecated", "Legacy", "Retired"):
                out.append(Finding(CLAUDE, f"{label} is marked {status} by Anthropic", severity="critical",
                                   playbook="vendors.retirements", detail=[r["row"]]))
                continue
            ns = r.get("not_sooner")
            earliest = ctx.today + timedelta(days=ANTHROPIC_NOTICE_DAYS)
            if ns and ns <= freeze and earliest <= freeze:
                out.append(Finding(WATCH, f"{label}: Active; guaranteed only to {ns:%d %b %Y} and no notice yet",
                                   severity="low", playbook="vendors.retirements",
                                   detail=[f"A retirement needs {ANTHROPIC_NOTICE_DAYS} days' notice, so even a notice "
                                           f"today would retire it no sooner than {earliest:%d %b} -- inside the window "
                                           f"until {freeze - timedelta(days=ANTHROPIC_NOTICE_DAYS):%d %b}.",
                                           "Watch the student's e-mail for an Anthropic deprecation notice."]))
            else:
                out.append(Finding(OK, f"{label}: Active" + (f", not before {ns:%d %b %Y}" if ns else "")))
            continue
        inside = [d for d in dates if d <= freeze]
        if inside:
            d = min(inside)
            if handled_until and handled_until <= d:
                how = handled_how or f"it moves to its registered route on {handled_until:%d %b} (deviation 23)"
                out.append(Finding(KNOWN, f"{label}: {vendor} shuts it down on {d:%d %b %Y} -- handled: {how}",
                                   playbook="vendors.retirements"))
            else:
                out.append(Finding(CLAUDE, f"{label}: {vendor} lists a shutdown on {d:%d %b %Y}, before the freeze",
                                   severity="critical", playbook="vendors.retirements", detail=[r["row"]],
                                   steps=["Read the page yourself to confirm, then bring the student the choice "
                                          "(as on 19 Sep for gpt_small): another host of the same snapshot, or "
                                          "let the model drop out -- with a recommendation."]))
        elif r.get("no_shutdown"):
            out.append(Finding(OK, f"{label}: no shutdown date announced"))
        elif dates:
            out.append(Finding(INFO, f"{label}: a date after the freeze ({max(dates):%d %b %Y})"))
        else:
            out.append(Finding(OK, f"{label}: listed, no date inside the study"))
    return out


@check("vendors.retirements", "No model of the panel is due to retire before the freeze", network=True,
       origin="09-19: OpenAI's page had listed gpt-4.1-nano's 23 Oct shutdown since April, and nobody "
              "had read it; 09-21 and 09-23 re-read all three pages")
def _vendors_retirements(ctx: Ctx):
    pages: Dict[str, Optional[str]] = {}

    def text_of(vendor: str) -> Optional[str]:
        if vendor not in pages:
            r = ctx.http.get(RETIREMENT_PAGES[vendor], headers={"User-Agent": BROWSER_AGENT}, timeout=40)
            pages[vendor] = page_text(r.text) if r.ok and len(r.text) > 2000 else None
        return pages[vendor]

    out: List[Finding] = []
    rows_seen = ctx.state.setdefault("seen", {}).setdefault("retirement_rows", {})
    freeze = date.fromisoformat(config.DATA_FREEZE)
    # Routes first: a route whose own host retires the model before it takes over
    # handles nothing, and the model's own shutdown must not read as handled.
    targets: List[Tuple[str, str, str, Optional[date], str]] = []
    for key, route in config.SERVING_ROUTES.items():
        if route.provider == "openrouter_azure":
            targets.append(("azure", f"{key} route", route.model_id, None, ""))
    bridge_stops = date.fromisoformat(config.BRIDGE_END) + timedelta(days=1)
    for key, route in config.BRIDGE_ROUTES.items():
        if route.provider == "openrouter_azure":
            targets.append(("azure", f"{key} bridge", route.model_id, bridge_stops,
                            f"the bridge's last day is {config.BRIDGE_END} (deviation 24)"))
    for spec in config.enabled_panel():
        if spec.provider not in RETIREMENT_PAGES:
            continue
        route, gone = config.SERVING_ROUTES.get(spec.key), config.RETIREMENTS.get(spec.key)
        if gone:
            targets.append((spec.provider, spec.key, spec.model_id, date.fromisoformat(gone),
                            f"it is not asked from {gone}, when no host serves it (deviation 24)"))
        else:
            targets.append((spec.provider, spec.key, spec.model_id,
                            date.fromisoformat(route.starts) if route else None, ""))
    dead_route: Dict[str, date] = {}
    for vendor, key, model_id, handled, how in targets:
        text = text_of(vendor)
        if text is None:
            out.append(Finding(WATCH, f"could not read {vendor}'s retirement page for {key}", severity="low",
                               playbook="vendors.retirements", detail=[RETIREMENT_PAGES[vendor]]))
            continue
        rows = retirement_rows(vendor, text, model_id)
        stamp = f"{vendor}:{model_id}"
        now_rows = sorted(r["row"] for r in rows)
        before = rows_seen.get(stamp)
        if before is not None and before != now_rows:
            out.append(Finding(CLAUDE, f"{vendor}'s retirement page changed what it says about {model_id}",
                               severity="high", playbook="vendors.retirements",
                               detail=["was: " + (" | ".join(before) or "(not listed)"),
                                       "now: " + (" | ".join(now_rows) or "(not listed)")],
                               steps=[f"Read {RETIREMENT_PAGES[vendor]} and decide whether it touches the study."]))
        rows_seen[stamp] = now_rows
        if key.endswith(" route"):
            inside = [d for r in rows for d in r.get("dates", []) if ctx.today <= d <= freeze]
            if inside:
                dead_route[key[:-len(" route")]] = min(inside)
        if handled and key in dead_route and dead_route[key] <= handled and not how:
            got = assess_retirement(ctx, vendor, key, model_id, rows, None)
            for f in got:
                if f.status == CLAUDE:
                    f.status, f.severity = INFO, "low"
                    f.summary += (f" -- the route that was to take over on {handled:%d %b} retires first "
                                  f"({dead_route[key]:%d %b}); see that finding")
                    f.steps = []
        else:
            got = assess_retirement(ctx, vendor, key, model_id, rows, handled, how)
        out += got
    unique: List[Finding] = []
    for f in out:
        if not any(u.status == f.status and u.summary == f.summary for u in unique):
            unique.append(f)
    return unique


@check("vendors.hosts", "Every OpenRouter model has a working host, and Azure still serves the "
       "gpt_small route", network=True,
       origin="09-13 and 09-23: qwen down to one host; 09-19: the Azure route probed before 23 Oct")
def _vendors_hosts(ctx: Ctx):
    try:
        from neff.providers import OpenRouterProvider
        ignored = set(OpenRouterProvider.EXTRA_BODY["provider"].get("ignore", []))
    except Exception:                                                  # noqa: BLE001
        ignored = set()
    targets = [(s.key, s.model_id, None) for s in config.enabled_panel() if s.provider == "openrouter"]
    targets += [(f"{k} route", r.model_id, "Azure") for k, r in config.SERVING_ROUTES.items()
                if r.provider == "openrouter_azure"]
    seen = _seen(ctx).setdefault("openrouter_hosts", {})
    out, lines = [], []
    freeze = date.fromisoformat(config.DATA_FREEZE)
    for key, model_id, required in targets:
        r = ctx.http.get(f"{OPENROUTER_API}/models/{model_id}/endpoints")
        if not r.ok:
            out.append(Finding(WATCH, f"could not read OpenRouter's hosts for {model_id} ({r.error or r.status})",
                               severity="low", playbook="vendors.hosts"))
            continue
        try:
            data = r.json().get("data") or {}
        except ValueError:
            continue
        eps = data.get("endpoints") or []
        names = sorted({str(e.get("provider_name")) for e in eps})
        usable = [e for e in eps if e.get("provider_name") not in ignored and e.get("status") in (0, None)
                  and ("temperature" in (e.get("supported_parameters") or ["temperature"]))]
        if required:
            usable = [e for e in usable if e.get("provider_name") == required]
        lines.append(f"{key}: {', '.join(names) or 'none'}" + (f" (ignored: {', '.join(sorted(set(names) & ignored))})"
                                                               if set(names) & ignored else ""))
        expiry = _day(data.get("expiration_date") or data.get("deprecation_date"))
        if expiry and expiry <= freeze:
            out.append(Finding(CLAUDE, f"OpenRouter lists {model_id} as expiring on {expiry:%d %b %Y}",
                               severity="critical", playbook="vendors.hosts"))
        if not usable:
            out.append(Finding(CLAUDE, f"no working host for {model_id}" + (f" on {required}" if required else ""),
                               severity="critical", playbook="vendors.hosts", detail=[lines[-1]]))
        before = set(seen.get(model_id, []))
        if before and set(names) != before:
            added, gone = sorted(set(names) - before), sorted(before - set(names))
            out.append(Finding(INFO, f"{key}: hosts changed" + (f"; new {', '.join(added)}" if added else "")
                               + (f"; gone {', '.join(gone)}" if gone else ""), playbook="vendors.hosts"))
        seen[model_id] = names
    ctx.facts["openrouter_hosts"] = lines
    out.insert(0, Finding(OK if not [f for f in out if f.status == CLAUDE] else INFO,
                          "OpenRouter hosts: " + "; ".join(lines)))
    return out


# ======================================================================================
# dates
# ======================================================================================

@check("dates.calendar", "The dates ahead",
       origin="every check-in ended on the next dates: the Week-5 window, the route switch, the freeze, the fair")
def _dates_calendar(ctx: Ctx):
    from neff import prediction
    items = [(_ts(prediction.PUBLISH_NOT_BEFORE), "Week-5 prediction: the publish window opens (a person runs it)")]
    for key, route in config.SERVING_ROUTES.items():
        items.append((_ts(f"{route.starts}T00:00:00+00:00"), f"{key} moves to {route.provider}"))
    items.append((_ts(f"{config.BRIDGE_END}T00:00:00+00:00"), "the bridge's last day (deviation 24)"))
    for key, gone in config.RETIREMENTS.items():
        items.append((_ts(f"{gone}T00:00:00+00:00"), f"{key} is retired: not asked from this day (deviation 24)"))
    items.append((_ts(f"{_last_ask_day().isoformat()}T00:00:00+00:00"), "the last day questions are asked"))
    items.append((_ts(f"{config.DATA_FREEZE}T00:00:00+00:00"), "data freeze; the registered final look opens after it"))
    for name, d in FAIR_DATES.items():
        items.append((_ts(f"{d}T14:00:00+00:00"), name))
    ahead = sorted((w, what) for w, what in items if w and w >= ctx.now - timedelta(days=1))
    lines = [f"{w:%a %d %b %Y} (in {(w.date() - ctx.today).days} days): {what}" for w, what in ahead]
    ctx.facts["calendar"] = lines
    return Finding(INFO, "next: " + (lines[0] if lines else "nothing"), detail=lines)


@check("dates.retirements", "A retired member stops on its day, and the bridge ends on its day",
       origin="09-30 (deviation 24): gpt_small is not asked from 23 Oct, when no host serves it, and "
              "the bridge to Azure ends on 13 Oct, the day before Azure retires the model")
def _dates_retirements(ctx: Ctx):
    out = []
    today = ctx.today.isoformat()
    for key, gone in sorted(config.RETIREMENTS.items()):
        if today < gone:
            out.append(Finding(INFO, f"{key} is asked until {date.fromisoformat(gone) - timedelta(days=1)}; "
                               f"from {gone} it is retired (deviation 24), in "
                               f"{(date.fromisoformat(gone) - ctx.today).days} days"))
            continue
        late = [o for o in ctx.primary_obs() if o.get("model_key") == key and o["_day"] >= gone]
        if late:
            out.append(Finding(CLAUDE, f"{key} was asked {len(late)} time(s) after its retirement on {gone}",
                               severity="high", playbook="dates.retirements",
                               detail=sorted({o["_day"] for o in late})[:6]))
        else:
            out.append(Finding(OK, f"{key} has not been asked since its retirement on {gone}"))
    if today <= config.BRIDGE_END:
        out.append(Finding(INFO, f"the bridge runs until {config.BRIDGE_END} (deviation 24)"))
    else:
        late = [o for o in ctx.primary_obs() if int(o.get("prompt_variant", 0) or 0) == config.BRIDGE_VARIANT
                and o["_day"] > config.BRIDGE_END]
        out.append(Finding(CLAUDE, f"{len(late)} bridge answers after its last day, {config.BRIDGE_END}",
                           severity="high", playbook="dates.retirements") if late else
                   Finding(OK, f"the bridge ended on {config.BRIDGE_END}, as registered"))
    for key, route in sorted(config.SERVING_ROUTES.items()):      # none since deviation 24
        if today < route.starts:
            out.append(Finding(INFO, f"{key} moves to {route.provider} on {route.starts}"))
            continue
        rows = [o for o in ctx.primary_obs() if o.get("model_key") == key and o["_day"] >= route.starts
                and int(o.get("prompt_variant", 0) or 0) == 0]
        wrong = [o for o in rows if o.get("provider") != route.provider]
        if not rows or wrong:
            out.append(Finding(CLAUDE, f"{key} is not being answered by its route {route.provider}",
                               severity="high", playbook="dates.retirements"))
    return out or None


@check("dates.after_freeze", "After the freeze: what the plan allows and requires",
       origin="PREREGISTRATION.md 9 and 11 (deviation 17): the final look is registered for after 11 Dec")
def _dates_after_freeze(ctx: Ctx):
    if ctx.today.isoformat() <= config.DATA_FREEZE:
        return None
    return Finding(YOU, "the data freeze has passed: the registered final look is now allowed", severity="medium",
                   playbook="dates.after_freeze", steps=[
                       "Ask Claude to run the final look with you -- the one registered unblinded run: "
                       "./.venv/bin/python scripts/analyze.py --unblind --out results.json",
                       "and the Week-5 verdict: ./.venv/bin/python scripts/week5_prediction.py --evaluate",
                       "Nothing else changes: interpretation is yours (ISEF rules)."])


@check("dates.web", "Checks that need judgement and a web search are up to date",
       origin="09-19 and 09-22: shutdown risk to the 2 Oct payrolls, the Region 6 date, GitHub's changes")
def _dates_web(ctx: Ctx):
    due, done = [], []
    for key, (days, title, how) in WEB_CHECKS.items():
        a = ctx.ack(key)
        if a:
            done.append(f"{title}: done {str(a.get('at'))[:10]}" + (f" ({a.get('note')})" if a.get("note") else ""))
        else:
            due.append((key, title, how))
    out = []
    if due:
        out.append(Finding(CLAUDE, f"{_plural(len(due), 'web check')} due: " + "; ".join(t for _, t, _ in due),
                           severity="low", playbook="dates.web",
                           steps=[f"{t}: {h} Then: scripts/health_check.py --ack {k} \"what you found\""
                                  for k, t, h in due]))
    if done:
        out.append(Finding(OK, "web checks current", detail=done))
    return out


# ======================================================================================
# you -- only the student can do these
# ======================================================================================

@check("you.addendum", "Addendum 1 is posted publicly", network=True,
       origin="drafted 09-09; unposted at every check-in since 09-13; its value is being public before "
              "the first registered look on 2 Oct")
def _you_addendum(ctx: Ctx):
    from neff import prediction
    st = _addendum_state(ctx)
    if ctx.ack("you.addendum"):
        return Finding(OK, "Addendum 1: marked posted")
    if st.get("zenodo") is None and st.get("osf_wiki") is None:
        return Finding(INFO, "whether Addendum 1 is posted could not be read (Zenodo/OSF unreachable)")
    parts = {"Zenodo": bool(st.get("zenodo")), "OSF files": bool(st.get("osf_files")),
             "OSF wiki": bool(st.get("osf_wiki"))}
    ctx.facts["addendum_posted"] = parts
    if all(parts.values()):
        return Finding(OK, "Addendum 1 is posted on Zenodo and on the OSF project")
    opens = _ts(prediction.PUBLISH_NOT_BEFORE)
    sev = "high" if ctx.now >= opens - timedelta(days=3) else "medium"
    top = max(ctx.flags.get("deviation_numbers") or [0])
    steps = []
    if not parts["Zenodo"]:
        steps.append(f"Zenodo: open zenodo.org/records/{ZENODO_RECORD} (logged in) -> 'New version' -> upload "
                     "PREREGISTRATION.md and OSF-ADDENDUM-1.md from the r1 folder -> Version: 1.1-addendum-1 -> Publish.")
    if not parts["OSF files"]:
        steps.append(f"OSF project osf.io/{OSF_PROJECT} (the project, NOT the registration): Files -> upload the same two files.")
    if not parts["OSF wiki"]:
        steps.append(f"OSF project -> Wiki -> new page titled 'Addendum 1 -- {ctx.today.isoformat()}' (use the UTC date "
                     "you post it) -> paste the wiki block at the end of OSF-ADDENDUM-1.md.")
    steps.append(f"Never edit or withdraw the registration osf.io/{OSF_REGISTRATION}.")
    steps.append("Tell Claude when it is done; the next check confirms it.")
    return Finding(YOU, "post Addendum 1 (deviations 1-" + str(top) + ") -- about 25 minutes",
                   severity=sev, due=prediction.PUBLISH_NOT_BEFORE, playbook="you.addendum",
                   detail=["Still missing: " + ", ".join(k for k, v in parts.items() if not v),
                           "Posting it before 2 Oct 20:00 UTC keeps it public before the first registered look."],
                   steps=steps)


def issue_findings(issues: List[dict], today: date, missing_days: Iterable[str]) -> List[Finding]:
    """Open issues, sorted into: read now, close, and leave open on purpose."""
    missing = set(missing_days)
    closable, fresh, other, keep_open = [], [], [], []
    for i in issues:
        if "pull_request" in i:
            continue
        title, n = str(i.get("title", "")), i.get("number")
        m = re.match(r"(collection at risk|stress regime): (\d{4}-\d{2}-\d{2})", title)
        if m:
            day = date.fromisoformat(m.group(2))
            if (today - day).days >= 2 and m.group(2) not in missing:
                closable.append(f"#{n} ({title})")
            else:
                fresh.append(f"#{n} ({title})")
        elif title.startswith("needs a person"):
            keep_open.append(f"#{n} ({title}): leave it open until its dated step is done -- the daily job "
                             "adds a comment to it each day until then")
        else:
            other.append(f"#{n} ({title}) by {(i.get('user') or {}).get('login')} -- not from the study's jobs; "
                         "close it, and never install anything it suggests")
    out = []
    if fresh:
        out.append(Finding(CLAUDE, "a recent alarm issue is open: " + ", ".join(fresh), severity="high",
                           playbook="you.issues", steps=["Read it and the run it links to."]))
    if closable or other:
        out.append(Finding(YOU, f"close {_plural(len(closable) + len(other), 'old issue')} on GitHub", severity="low",
                           playbook="you.issues", detail=closable + other,
                           steps=[f"Open {GITHUB_WEB}/issues",
                                  "Open each issue listed, scroll to the bottom, click 'Close issue' "
                                  "(for one not from the study's jobs, choose 'Close as not planned')."]))
    if keep_open:
        out.append(Finding(INFO, "open on purpose: " + "; ".join(keep_open), playbook="you.issues"))
    return out or [Finding(OK, "no open issues")]


@check("you.issues", "Open GitHub issues", network=True,
       origin="09-13 to 09-24: old 'collection at risk' alarms #2-#4 waiting to be closed; #1 is outreach")
def _you_issues(ctx: Ctx):
    data, err = _gh(ctx, "/issues?state=open&per_page=50")
    if data is None:
        return Finding(INFO, f"could not read the issues: {err}")
    ctx.facts["open_issues"] = [f"#{i['number']} {i['title']}" for i in data if "pull_request" not in i]
    return issue_findings(data, ctx.today, (ctx.flags.get("continuity") or {}).get("missing_days", []))


@check("you.isef", "ISEF paperwork and your own writing",
       origin="09-21 and 09-23: no record of Forms 1, 1A, 1B, 2A or the student's Research Plan; "
              "AI-USE-LOG.md 'What only you can do'")
def _you_isef(ctx: Ctx):
    steps = []
    if not ctx.ack("you.isef"):
        steps += ["Forms 1, 1A and 1B with your adult sponsor and a parent; date each one on the day it is "
                  "actually signed (never backdate).",
                  "Form 2A (Student Support Disclosure, new for 2026-27): describe the AI help in your own words; "
                  "AI-USE-LOG.md has the facts.",
                  "Your own Research Plan, in your own words, with its seven parts.",
                  "When they are done, tell Claude (it records: --ack you.isef)."]
    if not ctx.ack("you.fair_ai_answer"):
        steps += ["Keep the fair's answer on AI use in writing: save the e-mail, or e-mail the Region 6 director "
                  "to confirm what they told you and keep the reply (then: --ack you.fair_ai_answer)."]
    if not steps:
        return Finding(OK, "ISEF paperwork and the fair's AI answer: marked done")
    return Finding(YOU, "ISEF paperwork, if it is not done yet", severity="low", playbook="you.isef", steps=steps)


def _transcripts_dir(ctx: Ctx) -> Path:
    slug = "-" + str(ctx.root.resolve()).strip("/").replace("/", "-")
    return ctx.home / ".claude" / "projects" / slug


@check("you.prompt_log", "The prompt log the ISEF rules require is safe -- and safe to share",
       origin="AI-USE-LOG.md: the transcripts ARE the prompt log, and a credential pasted into a chat "
              "stays in them in plain text")
def _you_prompt_log(ctx: Ctx):
    folder = _transcripts_dir(ctx)
    files = sorted(folder.glob("*.jsonl")) if folder.exists() else []
    if not files:
        return Finding(INFO, "no Claude Code transcripts on this Mac for this folder")
    kinds: Dict[str, set] = defaultdict(set)
    where: Dict[str, set] = defaultdict(set)
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _LOG_KEY_RE.finditer(text):
            kinds[_key_kind(m)].add(m.group(0)[-6:])
            where[_key_kind(m)].add(f.name[:8])
    newest = datetime.fromtimestamp(max(f.stat().st_mtime for f in files), timezone.utc)
    ctx.facts["transcripts"] = {"count": len(files), "newest": newest.isoformat()}
    out = [Finding(INFO, f"{len(files)} session transcripts in {folder} (newest {newest:%d %b})")]
    if kinds:
        summary = ", ".join(f"{_plural(len(v), k)} in {_plural(len(where[k]), 'transcript')}" for k, v in kinds.items())
        revoked = bool(ctx.ack("you.github_token"))
        out.append(Finding(YOU, f"the prompt log contains secrets: {summary} (values not shown)",
                           severity="medium" if revoked else "high", playbook="you.prompt_log",
                           steps=([] if revoked else [
                               "Revoke it. For a GitHub token: github.com -> your photo -> Settings -> Developer "
                               "settings -> Personal access tokens -> the token -> Delete. (Anyone holding a "
                               "token with write access could rewrite the study's public history.)",
                               "Make a new one the same way, and tell Claude, so pushing from this Mac keeps working.",
                               "Then: scripts/health_check.py --ack you.github_token"]) + [
                               "Never share the transcripts as they are: ask Claude for a redacted copy to share, "
                               "and keep the originals private."]))
    if not ctx.ack("you.prompt_log_backup"):
        out.append(Finding(YOU, "back up the prompt log (weekly)", severity="low", playbook="you.prompt_log",
                           steps=[f"Copy the folder {folder} to a USB stick or a private cloud folder.",
                                  "Then: scripts/health_check.py --ack you.prompt_log_backup"]))
    return out


# ======================================================================================
# local -- this Mac
# ======================================================================================

@check("local.python", "The local Python can run everything",
       origin="09-13 onward: this Mac runs Python 3.9 while GitHub runs 3.11")
def _local_python(ctx: Ctx):
    p = _run([ctx.python, "-c", "import sys, numpy, pandas, scipy, httpx; print('%d.%d.%d' % sys.version_info[:3])"],
             ctx.root, timeout=60)
    if not p.ok:
        return Finding(CLAUDE, f"{ctx.python} cannot import the study's packages", severity="high",
                       playbook="local.python", detail=_tail(p.err, 3))
    version = p.out.strip()
    ctx.facts["local_python"] = version
    return Finding(OK, f"Python {version} with the study's packages"
                   + ("; GitHub runs 3.11, which --deep tests" if not version.startswith("3.11") else ""))


@check("local.leftovers", "No leftovers from earlier sessions outside the repository",
       origin="09-24: `uv python install` had left ~/.local/bin/python3.11 pointing into a deleted scratchpad")
def _local_leftovers(ctx: Ctx):
    bin_dir = ctx.home / ".local" / "bin"
    stale = []
    if bin_dir.is_dir():
        for p in bin_dir.iterdir():
            if not p.is_symlink():
                continue
            target = os.readlink(p)
            # Only links into a Claude scratch folder: anything else is not ours to judge.
            if "/claude-" in target and ("/tmp/" in target or target.startswith("/private/tmp")):
                stale.append(p)
    if not stale:
        return Finding(OK, "nothing left behind")
    if not ctx.fix:
        return Finding(INFO, "leftover links into deleted scratch folders: " + ", ".join(map(str, stale)))
    for p in stale:
        p.unlink()
    for d in (bin_dir, bin_dir.parent):
        try:
            d.rmdir()                                                  # only if now empty
        except OSError:
            break
    return Finding(FIXED, f"removed {_plural(len(stale), 'leftover link')} into deleted scratch folders",
                   detail=[str(p) for p in stale])


@check("local.disk", "Enough disk space for the checks and the deep checks",
       origin="the deep checks build a Python 3.11 environment and several copies of the repository")
def _local_disk(ctx: Ctx):
    free = shutil.disk_usage(str(ctx.root)).free / 1e9
    if free < 3:
        return Finding(WATCH, f"only {free:.1f} GB free", severity="medium", playbook="local.disk")
    return Finding(OK, f"{free:.0f} GB free")


# ======================================================================================
# deep -- slow checks, run with --deep
# ======================================================================================

def _cache_dir(ctx: Ctx) -> Path:
    _ensure_state_dir(ctx.state_dir)
    d = ctx.state_dir / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _working_copy(ctx: Ctx, dest: Path) -> Optional[str]:
    """A fresh clone of HEAD with this copy's uncommitted changes applied: what CI would see."""
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    p = _run(["git", "clone", "-q", str(ctx.root), str(dest)], ctx.root.parent, timeout=300)
    if not p.ok:
        return "git clone failed: " + " ".join(_tail(p.err, 2))
    diff = ctx.git("diff", "HEAD", "--binary")
    if diff.out.strip():
        patch = dest.parent / f"{dest.name}.patch"
        patch.write_text(diff.out, encoding="utf-8")
        a = _run(["git", "apply", str(patch)], dest, timeout=120)
        if not a.ok:
            return "could not apply this copy's uncommitted changes: " + " ".join(_tail(a.err, 2))
    for rel in ctx.git.out("ls-files", "--others", "--exclude-standard").splitlines():
        if rel.startswith((".health/", "data/")):
            continue
        src, dst = ctx.root / rel, dest / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return None


def _constraints_digest(ctx: Ctx) -> str:
    h = hashlib.sha256()
    for name in ("requirements.txt", "constraints.txt"):
        p = ctx.root / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _py311(ctx: Ctx) -> Tuple[Optional[str], str]:
    """A Python 3.11 environment installed exactly as CI installs it, cached between runs."""
    if "py311" in ctx.flags:
        return ctx.flags["py311"]
    cache = _cache_dir(ctx)
    venv = cache / "venv311"
    py = venv / "bin" / "python"
    marker = venv / ".constraints"
    digest = _constraints_digest(ctx)
    if py.exists() and marker.exists() and marker.read_text().strip() == digest:
        ctx.flags["py311"] = (str(py), "")
        return ctx.flags["py311"]
    uv = cache / "uvlib" / "bin" / "uv"
    if not uv.exists():
        p = _run([ctx.python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--target",
                  str(cache / "uvlib"), "uv"], ctx.root, timeout=600)
        if not p.ok:
            ctx.flags["py311"] = (None, "could not install uv: " + " ".join(_tail(p.err, 2)))
            return ctx.flags["py311"]
    env = dict(os.environ, UV_PYTHON_INSTALL_DIR=str(cache / "uvpy"), UV_CACHE_DIR=str(cache / "uvcache"),
               PYTHONPATH=str(cache / "uvlib"))
    shutil.rmtree(venv, ignore_errors=True)
    steps = [
        [str(uv), "venv", "--seed", "--python", "3.11", "--python-preference", "only-managed", str(venv)],
        [str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--upgrade", "pip",
         "-c", "constraints.txt"],
        [str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r", "requirements.txt",
         "-c", "constraints.txt"],
    ]
    for argv in steps:
        p = _run(argv, ctx.root, timeout=1200, env=env)
        if not p.ok:
            ctx.flags["py311"] = (None, f"{Path(argv[0]).name} {' '.join(argv[1:3])} failed: " + " ".join(_tail(p.err, 3)))
            return ctx.flags["py311"]
    marker.write_text(digest)
    ctx.flags["py311"] = (str(py), "")
    return ctx.flags["py311"]


@check("deep.ci_parity", "The suite passes on CI's Python 3.11, installed exactly as CI installs it",
       deep=True, network=True,
       origin="09-13, 09-16, 09-19, 09-24: a failure only on 3.11 would stop the next collection")
def _deep_ci_parity(ctx: Ctx):
    py, why = _py311(ctx)
    if not py:
        return Finding(ERROR, f"could not build Python 3.11: {why}", severity="medium", playbook="deep.ci_parity")
    freeze = _run([py, "-m", "pip", "freeze"], ctx.root, timeout=120).out
    installed = {ln.split("==")[0].lower().replace("_", "-"): ln.split("==")[1] for ln in freeze.splitlines() if "==" in ln}
    pins = {}
    for ln in (ctx.root / "constraints.txt").read_text(encoding="utf-8").splitlines():
        ln = ln.split("#")[0].strip()
        if "==" in ln:
            name, ver = ln.split("==", 1)
            pins[name.strip().lower().replace("_", "-")] = ver.strip()
    drift = [f"{k} {installed.get(k)} (pinned {v})" for k, v in pins.items()
             if k != "pip" and installed.get(k) not in (None, v)]
    clone = ctx.tmp / "parity"
    err = _working_copy(ctx, clone)
    if err:
        return Finding(ERROR, err, severity="medium", playbook="deep.ci_parity")
    p = _run([py, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider", "-rfE"], clone, timeout=2400,
             env=_quiet_env(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1"))
    counts = _pytest_summary(p.out)
    ctx.facts["tests_py311"] = counts
    out = []
    if p.ok:
        out.append(Finding(OK, f"Python 3.11, fresh copy, pinned packages: {counts.get('passed', 0)} passed, "
                           f"{counts.get('skipped', 0)} skipped ({p.seconds:.0f} s)"))
    else:
        out.append(Finding(CLAUDE, "the suite fails on CI's Python 3.11", severity="critical",
                           playbook="deep.ci_parity", detail=_failing_tests(p.out)[:15] or _tail(p.out + p.err, 12)))
    if drift:
        out.append(Finding(CLAUDE, "the 3.11 environment does not match constraints.txt", severity="medium",
                           playbook="deep.ci_parity", detail=drift))
    return out


# The instants a date-dependent bug would show itself: the Week-5 window's edges and
# hold, the bridge's last day and gpt_small's retirement (deviation 24), month ends,
# the last asking days, the freeze, and after it.
TIME_TRAVEL_INSTANTS = [
    "2026-10-02 19:59:30", "2026-10-02 20:00:30", "2026-10-02 23:50:00", "2026-10-04 19:59:30",
    "2026-10-04 20:00:30", "2026-10-13 23:50:00", "2026-10-14 00:05:00", "2026-10-14 13:15:00",
    "2026-10-22 23:50:00", "2026-10-23 00:05:00", "2026-10-23 13:15:00",
    "2026-11-01 13:15:00", "2026-11-02 13:15:00", "2026-12-07 13:15:00", "2026-12-07 23:50:00",
    "2026-12-08 13:15:00", "2026-12-08 23:50:00", "2026-12-10 23:50:00", "2026-12-11 13:15:00",
    "2026-12-11 23:59:30", "2026-12-12 00:05:00", "2026-12-12 23:50:00", "2027-01-05 13:15:00",
    "2027-01-28 13:15:00", "2027-02-01 13:15:00",
]

SITECUSTOMIZE = '''\
import os
_when = os.environ.get("TT_WHEN")
if _when:
    try:
        # pandas subclasses datetime in C and fails to import once the clock is faked
        try:
            import pandas  # noqa: F401
        except Exception:
            pass
        import freezegun
        freezegun.freeze_time(_when, tick=True).start()
    except Exception as exc:  # pragma: no cover
        import sys
        sys.stderr.write("tt sitecustomize failed: %r\\n" % (exc,))
'''


@check("deep.time_travel", "The suite passes at every date that matters from here to 2027",
       deep=True, network=True,
       origin="09-13 and 09-24: the whole suite, clock set to every remaining day; no test may unblind "
              "the real record at any date")
def _deep_time_travel(ctx: Ctx):
    py, _ = _py311(ctx)
    py = py or ctx.python
    cache = _cache_dir(ctx)
    lib, tt = cache / "ttlib", cache / "tt"
    if not (lib / "freezegun").exists():
        p = _run([py, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--target", str(lib),
                  "freezegun"], ctx.root, timeout=600)
        if not p.ok:
            return Finding(ERROR, "could not install freezegun: " + " ".join(_tail(p.err, 2)), severity="low")
    tt.mkdir(parents=True, exist_ok=True)
    (tt / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    instants = [w for w in TIME_TRAVEL_INSTANTS if _ts(w.replace(" ", "T")) and _ts(w.replace(" ", "T")) > ctx.now]
    if not instants:
        return Finding(INFO, "no future instants left to test")
    workers = max(1, min(4, (os.cpu_count() or 2) // 2))
    clones = []
    for i in range(workers):
        dest = ctx.tmp / "tt" / f"w{i}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        err = _working_copy(ctx, dest)
        if err:
            return Finding(ERROR, err, severity="low", playbook="deep.time_travel")
        clones.append(dest)
    import concurrent.futures
    import queue
    work: "queue.Queue[str]" = queue.Queue()
    for w in instants:
        work.put(w)
    results: List[Tuple[str, Proc, str]] = []

    def worker(i: int):
        while True:
            try:
                w = work.get_nowait()
            except queue.Empty:
                return
            env = _quiet_env(TT_WHEN=w, PYTHONPATH=f"{tt}{os.pathsep}{lib}", OMP_NUM_THREADS="1",
                             OPENBLAS_NUM_THREADS="1", VECLIB_MAXIMUM_THREADS="1", MKL_NUM_THREADS="1")
            seen = _run([py, "-c", "import datetime; print(datetime.datetime.utcnow().isoformat(' '))"],
                        clones[i], timeout=120, env=env).out.strip()
            if seen[:13] != w[:13]:
                results.append((w, Proc(1, "", f"the clock did not move to {w} (saw {seen!r})"), "clock"))
                continue
            bt = ctx.tmp / "tt" / f"bt-{i}-{w[:10]}-{w[11:13]}{w[14:16]}"
            p = _run([py, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider", "-rfE", f"--basetemp={bt}"],
                     clones[i], timeout=1800, env=env)
            results.append((w, p, "tests"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(worker, range(workers)))
    bad = [(w, p, kind) for w, p, kind in sorted(results) if not p.ok]
    ctx.facts["time_travel"] = {"instants": len(results), "failing": [w for w, _, _ in bad]}
    if bad:
        return Finding(CLAUDE, f"the suite fails at {_plural(len(bad), 'future instant')}", severity="critical",
                       playbook="deep.time_travel",
                       detail=[f"{w}: " + ("; ".join(_failing_tests(p.out)[:3]) or " ".join(_tail(p.err or p.out, 2)))
                               for w, p, _ in bad[:10]])
    return Finding(OK, f"the suite passes at all {len(results)} future instants, from "
                   f"{instants[0][:10]} to {instants[-1][:10]}")


@check("deep.actionlint", "Both workflows pass actionlint", deep=True, network=True,
       origin="09-24: every workflow edit was linted before it was committed")
def _deep_actionlint(ctx: Ctx):
    lib = _cache_dir(ctx) / "lintlib"
    binary = lib / "bin" / "actionlint"
    if not binary.exists():
        p = _run([ctx.python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--target", str(lib),
                  "actionlint-py"], ctx.root, timeout=600)
        if not p.ok or not binary.exists():
            return Finding(ERROR, "could not install actionlint", severity="low", detail=_tail(p.err, 2))
    files = sorted(str(p.relative_to(ctx.root)) for p in (ctx.root / ".github" / "workflows").glob("*.yml"))
    p = _run([str(binary), "-shellcheck=", "-pyflakes=", *files], ctx.root, timeout=120)
    if p.ok:
        return Finding(OK, f"actionlint: {', '.join(files)} clean")
    return Finding(CLAUDE, "actionlint found problems in the workflows", severity="medium",
                   playbook="deep.actionlint", detail=_tail(p.out + p.err, 12))


@check("deep.linux_install", "The pinned packages still install on GitHub's Linux with Python 3.11",
       deep=True, network=True,
       origin="09-24: constraints.txt is pip's Linux/3.11 resolution; a yanked or vanished pin would stop CI")
def _deep_linux_install(ctx: Ctx):
    py, why = _py311(ctx)
    if not py:
        return Finding(ERROR, f"could not build Python 3.11: {why}", severity="low")
    report = ctx.tmp / "linux-report.json"
    p = _run([py, "-m", "pip", "install", "--dry-run", "--quiet", "--disable-pip-version-check", "--report",
              str(report), "--ignore-installed", "--only-binary=:all:", "--platform", "manylinux_2_28_x86_64",
              "--platform", "manylinux2014_x86_64", "--python-version", "3.11", "--implementation", "cp",
              "--target", str(ctx.tmp / "never-used"), "-r", "requirements.txt", "-c", "constraints.txt"],
             ctx.root, timeout=900)
    if not p.ok:
        return Finding(CLAUDE, "the pinned set no longer resolves for Linux / Python 3.11", severity="high",
                       playbook="deep.linux_install", detail=_tail(p.err, 8))
    try:
        got = {i["metadata"]["name"].lower().replace("_", "-"): i["metadata"]["version"]
               for i in json.loads(report.read_text())["install"]}
    except (OSError, ValueError, KeyError):
        return Finding(ERROR, "pip's install report could not be read", severity="low")
    pins = {}
    for ln in (ctx.root / "constraints.txt").read_text(encoding="utf-8").splitlines():
        ln = ln.split("#")[0].strip()
        if "==" in ln:
            n, v = ln.split("==", 1)
            pins[n.strip().lower().replace("_", "-")] = v.strip()
    diff = [f"{k}: {v} (pinned {pins.get(k)})" for k, v in got.items() if pins.get(k) not in (None, v)]
    unpinned = sorted(set(got) - set(pins))
    if diff or unpinned:
        detail = diff + ([f"not pinned: {', '.join(unpinned)}"] if unpinned else [])
        return Finding(CLAUDE, "Linux resolves a different set than constraints.txt pins", severity="medium",
                       playbook="deep.linux_install", detail=detail)
    return Finding(OK, f"all {len(got)} pinned packages resolve for Linux / Python 3.11 exactly as pinned")


# ======================================================================================
# running, judging, reporting
# ======================================================================================

def _normalise(result: Any) -> List[Finding]:
    if result is None:
        return []
    if isinstance(result, Finding):
        return [result]
    return [f for f in result if f is not None]


def run_checks(ctx: Ctx, selected: Optional[Sequence[str]] = None) -> List[Finding]:
    _ensure_state_dir(ctx.state_dir)          # self-ignoring before anything could be written into it
    # One fixing run at a time: two runs replaying commits or putting back data/ at the
    # same moment would trip over each other. A run started while another is fixing (a
    # --deep run in the background, say) still checks everything, and changes nothing.
    with (_flock(ctx.state_dir / "fix.lock", wait=False) if ctx.fix else nullcontext(True)) as alone:
        if not alone:
            ctx.fix = False
            ctx.facts["fix_skipped"] = "another health check was running and fixing; this one only reported"
        return _run_checks(ctx, selected)


def _run_checks(ctx: Ctx, selected: Optional[Sequence[str]]) -> List[Finding]:
    wanted = [c for c in CHECKS if _selected(c, selected)]
    findings: List[Finding] = []
    started = False
    ctx.facts["checks_run"] = []
    for chk in wanted:
        if not started and chk.group != "repo":
            _start_background(ctx, [c.id for c in wanted])
            started = True
        if chk.deep and not ctx.deep:
            continue
        if chk.network and ctx.offline:
            findings.append(Finding(SKIP, "not run (--offline)", check=chk.id, group=chk.group))
            continue
        t0 = time.time()
        try:
            got = _normalise(chk.fn(ctx))
        except Exception as exc:                                       # noqa: BLE001
            got = [Finding(ERROR, f"the check itself failed: {type(exc).__name__}: {exc}", severity="medium",
                           playbook="checker-errors",
                           detail=[ln for ln in traceback.format_exc().splitlines()[-6:]])]
        for f in got:
            f.check, f.group = chk.id, chk.group
        ctx.results[chk.id] = got
        ctx.facts["checks_run"].append({"id": chk.id, "seconds": round(time.time() - t0, 2)})
        findings.extend(got)
    if not started:
        _start_background(ctx, [c.id for c in wanted])
    return findings


def _selected(chk: Check, selected: Optional[Sequence[str]]) -> bool:
    if not selected:
        return True
    return any(chk.id == s or chk.id.startswith(s.rstrip(".") + ".") for s in selected)


def verdict(findings: List[Finding]) -> Dict[str, Any]:
    act = [f for f in findings if f.status in ACTIONABLE]
    critical = [f for f in act if f.severity == "critical"]
    serious = [f for f in act if (f.status in (CLAUDE, ERROR) and _RANK[f.severity] >= 1)
               or (f.status == YOU and _RANK[f.severity] >= 2)]
    counts = Counter(f.status for f in findings)
    n_claude = sum(1 for f in act if f.status in (CLAUDE, ERROR))
    n_you = sum(1 for f in act if f.status == YOU)
    if critical:
        level, headline = "red", "URGENT -- " + critical[0].summary
        code = 2
    elif serious:
        level, code = "attention", 1
        bits = ([_plural(n_claude, "thing") + " for Claude to fix"] if n_claude else []) + \
               ([_plural(n_you, "thing") + " for you"] if n_you else [])
        headline = "NEEDS ATTENTION -- " + ", ".join(bits)
    else:
        level, code = "green", 0
        headline = "ALL GOOD -- the study is collecting every day and on plan"
        if n_you:
            headline += f"; {_plural(n_you, 'small thing')} for you, none urgent"
    return {"level": level, "headline": headline, "exit_code": code, "counts": dict(counts),
            "for_claude": n_claude, "for_you": n_you}


def _sort_key(f: Finding) -> Tuple:
    return (-_RANK.get(f.severity, 0), f.due or "9999", [g for g, _ in GROUPS].index(f.group)
            if f.group in GROUP_TITLES else 99)


def _summary_line(ctx: Ctx, v: Dict[str, Any]) -> str:
    f = ctx.facts
    bits = [f"{ctx.today.isoformat()}: {v['level']}"]
    if f.get("days_collected"):
        bits.append(f"{f['days_collected']} days collected ({f.get('first_day')}..{f.get('last_day')})")
    if f.get("tests"):
        bits.append(f"{f['tests'].get('passed', 0)} tests pass")
    if f.get("deviations") is not None:
        bits.append(f"{f['deviations']} deviations")
    if f.get("spend"):
        bits.append(f"${f['spend']['spent']} of ${f['spend']['cap']:.0f}")
    low = min((f.get("coverage_window") or {}).items(), key=lambda kv: kv[1], default=None)
    if low:
        bits.append(f"lowest 7-day coverage {low[0]} {_pct(low[1])}")
    if f.get("unpushed_commits"):
        bits.append(f"{f['unpushed_commits']} local commit(s) unpushed")
    posted = f.get("addendum_posted")
    if posted is not None:
        bits.append("Addendum 1 posted" if all(posted.values()) else "Addendum 1 NOT posted")
    return "; ".join(bits)


def render_terminal(ctx: Ctx, findings: List[Finding], v: Dict[str, Any], verbose: bool = False,
                    partial: bool = False) -> str:
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    def c(code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if color else text

    tone = {"green": "32;1", "attention": "33;1", "red": "31;1"}[v["level"]]
    lines = [c("1", f"Correlated Minds -- health check -- {_when(ctx.now)}"), "",
             c(tone, v["headline"]), ""]
    if ctx.facts.get("fix_skipped"):
        lines += [f"Report only: {ctx.facts['fix_skipped']}.", ""]
    fixed = [f for f in findings if f.status == FIXED]
    claude = sorted([f for f in findings if f.status in (CLAUDE, ERROR)], key=_sort_key)
    you = sorted([f for f in findings if f.status == YOU], key=_sort_key)
    watch = sorted([f for f in findings if f.status == WATCH], key=_sort_key)
    known = [f for f in findings if f.status == KNOWN]
    if fixed:
        lines.append(c("1", "Fixed automatically"))
        for f in fixed:
            lines.append(f"  + {f.summary}")
            lines += [f"      {d}" for d in f.detail if d]
        lines.append("")
    if claude:
        lines.append(c("1", "For Claude (HEALTH-CHECK.md says how)"))
        for f in claude:
            lines.append(f"  ! [{f.severity}] {f.summary}  ({f.check})")
            lines += [f"      {d}" for d in f.detail[:6] if d]
        lines.append("")
    if you:
        lines.append(c("1", "For you"))
        for i, f in enumerate(you, 1):
            due = f"  -- by {_when(_ts(f.due))}" if f.due and _ts(f.due) else ""
            lines.append(f"  {i}. {f.summary}{due}")
            lines += [f"       {d}" for d in f.detail[:8] if d]
            lines += [f"       {chr(96 + k)}. {s}" for k, s in enumerate(f.steps, 1)]
        lines.append("")
    if watch:
        lines.append(c("1", "Watching (not a problem yet)"))
        lines += [f"  ~ {f.summary}" for f in watch]
        lines.append("")
    ran = sorted({f.check for f in findings if f.status != SKIP})
    quiet = [c for c in ran if all(f.status in (OK, INFO, KNOWN, FIXED)
                                   for f in findings if f.check == c)]
    skipped = sorted({f.check for f in findings if f.status == SKIP})
    lines.append(f"{len(ran)} checks ran; {len(quiet)} found nothing to do"
                 + (f" ({len(known)} findings are known and explained)" if known else "")
                 + (f"; {len(skipped)} skipped" if skipped else "") + ". -v lists every one.")
    if verbose:
        lines.append("")
        for group, title in GROUPS:
            got = [f for f in findings if f.group == group]
            if not got:
                continue
            lines.append(c("1", title))
            for f in got:
                lines.append(f"  {f.status:6} {f.check:22} {f.summary}")
                if f.status in (OK, INFO, KNOWN):
                    lines += [f"{'':31}{d}" for d in f.detail[:8] if d]
    lines.append(("Report of this partial run: " if partial else "Full report: ")
                 + str(ctx.state_dir / f"{report_name(partial)}.md"))
    return "\n".join(lines)


def render_markdown(ctx: Ctx, findings: List[Finding], v: Dict[str, Any]) -> str:
    out = [f"# Health check -- {_when(ctx.now)}", "", f"**{v['headline']}**", "",
           f"Mode: {'fix' if ctx.fix else 'report only'}{', offline' if ctx.offline else ''}"
           f"{' (another check was fixing)' if ctx.facts.get('fix_skipped') else ''}"
           f"{', deep' if ctx.deep else ''}{', quick' if ctx.quick else ''}.", "",
           f"Summary line: `{_summary_line(ctx, v)}`", ""]
    for label, statuses in (("Fixed automatically", (FIXED,)), ("For Claude", (CLAUDE, ERROR)),
                            ("For you", (YOU,)), ("Watching", (WATCH,))):
        got = sorted([f for f in findings if f.status in statuses], key=_sort_key)
        if not got:
            continue
        out += [f"## {label}", ""]
        for f in got:
            due = f" (by {_when(_ts(f.due))})" if f.due and _ts(f.due) else ""
            out.append(f"- **{f.summary}**{due} -- `{f.check}`, {f.severity}")
            out += [f"  - {d}" for d in f.detail if d]
            out += [f"  {k}. {s}" for k, s in enumerate(f.steps, 1)]
        out.append("")
    out += ["## Every check", ""]
    for group, title in GROUPS:
        got = [f for f in findings if f.group == group]
        if not got:
            continue
        out += [f"### {title}", ""]
        for f in got:
            out.append(f"- `{f.status}` `{f.check}` -- {f.summary}")
            out += [f"  - {d}" for d in f.detail if d]
        out.append("")
    out += ["## Facts", "", "```json", json.dumps(ctx.facts, indent=2, default=str), "```", ""]
    return "\n".join(out)


def report_name(partial: bool) -> str:
    # A run of a few checks (--only) must not replace the last full report, which is
    # what a check-in reads.
    return "last-partial" if partial else "last-report"


def write_reports(ctx: Ctx, findings: List[Finding], v: Dict[str, Any], extra_json: Optional[Path] = None,
                  partial: bool = False) -> None:
    _ensure_state_dir(ctx.state_dir)
    ctx.facts["summary_line"] = _summary_line(ctx, v)
    name = report_name(partial)
    payload = {
        "schema": 1,
        "generated_at": ctx.now.isoformat(),
        "partial": partial,
        "mode": {"fix": ctx.fix, "offline": ctx.offline, "deep": ctx.deep, "quick": ctx.quick},
        "verdict": v,
        "findings": [f.as_dict() for f in sorted(findings, key=_sort_key)],
        "facts": ctx.facts,
    }
    text = json.dumps(payload, indent=2, default=str)
    (ctx.state_dir / f"{name}.json").write_text(text, encoding="utf-8")
    (ctx.state_dir / f"{name}.md").write_text(render_markdown(ctx, findings, v), encoding="utf-8")
    if extra_json:
        Path(extra_json).write_text(text, encoding="utf-8")
    with (ctx.state_dir / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": ctx.now.isoformat(), "partial": partial, "level": v["level"],
                             "headline": v["headline"], "counts": v["counts"],
                             "summary": ctx.facts["summary_line"]}) + "\n")
    if not partial:
        ctx.state.setdefault("runs", {})["deep" if ctx.deep else "standard"] = ctx.now.isoformat()
    _save_state(ctx)


# ======================================================================================
# command line
# ======================================================================================

def _list_checks() -> str:
    lines = []
    for group, title in GROUPS:
        got = [c for c in CHECKS if c.group == group]
        if not got:
            continue
        lines.append(f"{title}")
        for c in got:
            tags = ",".join(t for t, on in (("network", c.network), ("deep", c.deep)) if on)
            lines.append(f"  {c.id:24} {c.title}" + (f"  [{tags}]" if tags else ""))
            lines.append(f"  {'':24} why: {c.origin}")
        lines.append("")
    return "\n".join(lines)


def _apply_admin(ctx: Ctx, args) -> List[str]:
    """--ack, --unack, --balance: record what a person reports, then stop."""
    said = []
    acks = ctx.state.setdefault("acks", {})
    for key, *note in args.ack or []:
        if key not in ACK_KEYS:
            raise SystemExit(f"unknown key {key!r}; known: {', '.join(sorted(ACK_KEYS))}")
        acks[key] = {"at": ctx.now.isoformat(), "note": " ".join(note)}
        said.append(f"recorded: {key} -- {ACK_KEYS[key][1]}")
    for key in args.unack or []:
        acks.pop(key, None)
        said.append(f"cleared: {key}")
    as_of = _ts(args.as_of) if args.as_of else ctx.now
    for item in args.balance or []:
        vendor, _, amount = item.partition("=")
        vendor = vendor.strip().lower()
        if vendor not in VENDOR_NAMES:
            raise SystemExit(f"unknown account {vendor!r}; use anthropic, openai, google or openrouter")
        ctx.state.setdefault("balances", {})[vendor] = {"usd": float(amount.strip().lstrip("$")),
                                                        "as_of": as_of.isoformat(), "source": "you"}
        said.append(f"recorded: {VENDOR_NAMES[vendor]} balance {_money(float(amount.strip().lstrip('$')))} "
                    f"as of {as_of:%Y-%m-%d %H:%M} UTC")
    if said:
        _save_state(ctx)
    return said


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-fix", action="store_true", help="report only; change nothing")
    parser.add_argument("--offline", action="store_true", help="skip everything that needs the network")
    parser.add_argument("--quick", action="store_true", help="skip the test suite and the blind pipeline runs")
    parser.add_argument("--deep", action="store_true",
                        help="also run the slow checks: Python 3.11 suite, time travel, actionlint, Linux install")
    parser.add_argument("--only", help="comma-separated check ids or groups (e.g. record,ci.runs)")
    parser.add_argument("--list", action="store_true", help="list every check and why it exists")
    parser.add_argument("--json", type=Path, help="also write the JSON report here")
    parser.add_argument("-v", "--verbose", action="store_true", help="print every check, not just what needs doing")
    parser.add_argument("--ack", nargs="+", action="append", metavar=("KEY", "NOTE"),
                        help="record that a person-only item is done: " + ", ".join(sorted(ACK_KEYS)))
    parser.add_argument("--unack", action="append", metavar="KEY")
    parser.add_argument("--balance", nargs="+", metavar="ACCOUNT=USD",
                        help="record balances read in the accounts, e.g. anthropic=17.37 openai=8.83 google=8.98")
    parser.add_argument("--as-of", help="when those balances were read (ISO time, UTC); default now")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.list:
        print(_list_checks())
        return 0
    ctx = Ctx(args.root, fix=not args.no_fix, offline=args.offline, deep=args.deep, quick=args.quick)
    said = _apply_admin(ctx, args)
    if said:
        print("\n".join(said))
        return 0
    selected = [s.strip() for s in args.only.split(",")] if args.only else None
    try:
        findings = run_checks(ctx, selected)
        v = verdict(findings)
        write_reports(ctx, findings, v, args.json, partial=bool(selected))
        print(render_terminal(ctx, findings, v, verbose=args.verbose, partial=bool(selected)))
        return v["exit_code"]
    finally:
        ctx.cleanup()


if __name__ == "__main__":
    sys.exit(main())

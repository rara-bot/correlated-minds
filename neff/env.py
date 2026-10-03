"""Load `.env` into the process environment at package import.

`providers.py` reads keys from `os.environ` only, but SETUP.md tells you to put
them in `.env` -- and `preflight.py` reads that file directly. Without this
module the two disagree: preflight reports all four keys green while the very
next command fails with "ANTHROPIC_API_KEY not set". A setup step that reports
success and then fails is worse than one that never claimed to work.

Existing environment variables always win. GitHub Actions injects the keys as
real env vars (see .github/workflows/daily.yml), and a stale committed `.env`
must never be able to override the secrets configured for the live study.
"""

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_PATH) -> int:
    """Read KEY=value lines into os.environ. Returns how many were set.

    Never raises: a missing or malformed `.env` is a normal state (mock runs,
    CI, offline tests) and must not stop the process from starting.
    """
    try:
        if not path.exists():
            return 0
        text = path.read_text()
    except OSError:
        return 0

    loaded = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        # Tolerate quotes: pasting from a provider console often brings them along.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded

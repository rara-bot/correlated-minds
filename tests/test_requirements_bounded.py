"""Every dependency is capped below its next major version.

The daily job installs `requirements.txt` fresh on every run, unattended, for fifteen
weeks. An uncapped line means the day a new major version is published is the day the
job starts installing it -- and a collection day that fails cannot be re-run later.

This is not hypothetical. `httpx>=0.27` was uncapped until 2026-09-19, when httpx
1.0.dev6 was checked: it has no `httpx.get`, `httpx.post`, `httpx.stream` or
`httpx.RequestError`, which is every call this study makes to a model and every
fetch from Kalshi, FRED and EDGAR. The day 1.0 was released, the suite would have
failed its "verify estimator before spending anything" step and the day would have
been lost, and so would every day after it until someone noticed.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
LINES = [line.strip() for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
         if line.strip() and not line.strip().startswith("#")]


@pytest.mark.parametrize("line", LINES)
def test_every_requirement_has_an_upper_bound(line):
    assert "<" in line, f"{line!r} has no upper bound; cap it below the next major version"


def test_httpx_stays_below_the_rewrite():
    [line] = [l for l in LINES if re.match(r"httpx\b", l)]
    upper = re.search(r"<\s*([0-9.]+)", line).group(1)
    assert tuple(int(p) for p in upper.split(".")) <= (1, 0), line


def test_the_installed_httpx_has_every_call_the_study_makes():
    # neff/providers.py, neff/sources/http.py, neff/sources/spf.py, scripts/pin_spf_inputs.py
    for name in ("get", "post", "head", "stream", "RequestError", "HTTPError", "ConnectTimeout"):
        assert hasattr(httpx, name), f"httpx {httpx.__version__} has no httpx.{name}"

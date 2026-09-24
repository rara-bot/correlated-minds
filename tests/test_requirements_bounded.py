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

A cap on a direct dependency says nothing about the packages it pulls in: httpx
depends on anyio, and matplotlib on pillow and fonttools, with no bound of their
own. So `constraints.txt` pins every installed package exactly, inside these caps,
and both workflows install through it.
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


CONSTRAINTS = ROOT / "constraints.txt"


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins() -> dict:
    pins = {}
    for raw in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            name, sep, version = line.partition("==")
            assert sep, f"constraints.txt: {raw!r} is not an exact pin"
            pins[_canon(name)] = version.strip()
    return pins


@pytest.mark.parametrize("line", LINES)
def test_every_requirement_is_pinned_inside_its_bounds(line):
    from packaging.requirements import Requirement   # installed with pytest itself

    req, pins = Requirement(line), _pins()
    assert _canon(req.name) in pins, f"{req.name} has no exact pin in constraints.txt"
    pinned = pins[_canon(req.name)]
    assert req.specifier.contains(pinned), (
        f"constraints.txt pins {req.name}=={pinned}, outside requirements.txt's {req.specifier}")


@pytest.mark.parametrize("workflow", ["daily.yml", "tests.yml"])
def test_both_workflows_install_through_the_pins(workflow):
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    assert "python -m pip install --upgrade pip -c constraints.txt" in text
    assert "pip install -r requirements.txt -c constraints.txt" in text

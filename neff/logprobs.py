"""The logprob leg of 5.4(a): which stored logprobs are valid, and the probability they imply.

PREREGISTRATION.md 5.4(a) registers, "for the models exposing logprobs", a
re-estimate "on logprob-derived probabilities". Deviation 10 stores the token
alternatives at the digit positions of every answer, and deviation 12 counts
the rows that carry them. Nothing checked that what arrived describes the answer
it came with, and the plan never defines the probability. Both are fixed here,
in deviation 19, from forecasts alone -- no outcome is read -- before any analysis
has used a logprob.

WHICH LOGPROBS ARE VALID

Sampling is pinned at temperature 0 (9), so a model decodes greedily: the token
it emits is the most likely one at that position, and it is listed among that
position's alternatives. A row that breaks either shows that its logprobs do not
describe the answer beside them -- the host sampled, or reported alternatives
from somewhere else. A SOURCE is a model and the host that served it, because
the same weights behind different hosts behave differently (deviation 7):

  consistent(row)   at every stored position the emitted token is listed, and
                    no alternative beats it by more than GREEDY_TOLERANCE
  usable source     every row the source returned with logprobs is consistent

One inconsistent row condemns its source, not just itself: the rows that happen
to pass come from the same serving stack, and a rule that kept them would keep
whichever rows the stack's fault did not reach.

Measured on 2026-09-09 to 2026-09-13: every row served by OpenAI (gpt_mid,
gpt_small, gpt_frontier) and by llama's four hosts is consistent. deepseek fails
on both hosts that send logprobs at all. Google lists alternatives that belong to
another position: the emitted token is missing from 31 of its 51 lists.
DigitalOcean emits a token that is not the most likely on 21 of 31 rows.

THE DERIVED PROBABILITY

Every answer states `"probability": 0.xx`, its digits are the first stored
positions, and on every row collected so far its decimals arrive as ONE token
("35", "7"). The derived probability is the expectation over that token's
listed alternatives, with the integer part held as emitted:

    p_hat = sum_k exp(lp_k) * value_k / sum_k exp(lp_k)

k runs over the alternatives that read as a number in [0, 1] once placed after
the emitted integer part ("3" -> 0.3, "35" -> 0.35). Anything else is dropped and
the rest renormalised, since a list of five omits the tail anyway. None -- never
the emitted value -- when the answer's own numeral cannot be found at the start
of the stored digits, has no decimal part, splits its decimals across tokens, or
disagrees with the stored forecast.
"""

import math
import re
from typing import Any, Dict, Iterable, Optional, Tuple

# Stored logprobs are rounded to four decimals (providers._digit_logprobs), so an
# alternative must beat the emitted token by more than rounding to count as more
# likely.
GREEDY_TOLERANCE = 0.01

# ASCII digits only: the lists also carry look-alikes such as "۰" and
# "０", which Python's \d and float() would both accept as zero.
_NUMERAL = re.compile(r'"probability"\s*:\s*"?\s*([0-9]*\.?[0-9]+)')
_NOT_DIGIT = re.compile(r"[^0-9]")
_NUMERIC_TOKEN = re.compile(r"\s*[0-9.]*[0-9][0-9.]*")


def _get(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def source(row: Any) -> Tuple[str, str]:
    """(model, host). A direct vendor API names no upstream host; it IS the host."""
    return _get(row, "model_key"), _get(row, "upstream_provider") or _get(row, "provider")


def consistent(row: Any) -> bool:
    """Could these logprobs have produced this answer under greedy decoding?"""
    positions = _get(row, "logprobs") or []
    if not positions:
        return False
    for position in positions:
        alternatives = position.get("top") or []
        if position.get("t") not in [token for token, _ in alternatives]:
            return False
        emitted = float(position.get("lp", 0.0))
        if any(float(lp) > emitted + GREEDY_TOLERANCE for _, lp in alternatives):
            return False
    return True


def usable_sources(rows: Iterable[Any]) -> Dict[Tuple[str, str], bool]:
    """Each source that returned logprobs: usable only if all of its rows are consistent."""
    verdict: Dict[Tuple[str, str], bool] = {}
    for row in rows:
        if _get(row, "logprobs"):
            key = source(row)
            verdict[key] = verdict.get(key, True) and consistent(row)
    return verdict


def derived_probability(row: Any) -> Optional[float]:
    """The expectation of the stated probability under its own logprobs, or None."""
    positions = _get(row, "logprobs") or []
    forecast = _get(row, "forecast")
    match = _NUMERAL.search(_get(row, "raw_response") or "")
    if not positions or forecast is None or match is None:
        return None
    numeral = match.group(1)
    whole, _, decimals = numeral.partition(".")
    if not decimals or abs(float(numeral) - float(forecast)) > 1e-9:
        return None

    stored = [_NOT_DIGIT.sub("", str(p.get("t", ""))) for p in positions]
    digits = whole + decimals
    if not "".join(stored).startswith(digits):
        return None

    # The position carrying the first decimal digit, and the digits before it.
    consumed, prefix, index = 0, "", None
    for i, token_digits in enumerate(stored):
        if consumed + len(token_digits) > len(whole):
            index = i
            break
        consumed += len(token_digits)
        prefix += token_digits
    if index is None or consumed + len(stored[index]) != len(digits):
        return None

    weight = total = 0.0
    for token, lp in positions[index].get("top") or []:
        if not _NUMERIC_TOKEN.fullmatch(str(token)):
            continue
        candidate = prefix + _NOT_DIGIT.sub("", str(token))
        value = float(candidate[:len(whole)] + "." + candidate[len(whole):]) \
            if len(candidate) > len(whole) else float(candidate)
        if 0.0 <= value <= 1.0:
            weight += math.exp(float(lp))
            total += math.exp(float(lp)) * value
    return total / weight if weight > 0 else None


def summary(rows: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """Per model: rows with logprobs, how many are inconsistent, and how many the leg can use."""
    carrying = [row for row in rows if _get(row, "logprobs")]
    verdict = usable_sources(carrying)
    out: Dict[str, Dict[str, Any]] = {}
    for row in carrying:
        model, host = source(row)
        entry = out.setdefault(model, {"with_logprobs": 0, "inconsistent": 0, "usable": 0,
                                       "derived": 0, "hosts": {}})
        by_host = entry["hosts"].setdefault(host, {"rows": 0, "inconsistent": 0,
                                                   "usable": verdict[(model, host)]})
        ok = consistent(row)
        entry["with_logprobs"] += 1
        entry["inconsistent"] += not ok
        by_host["rows"] += 1
        by_host["inconsistent"] += not ok
        if verdict[(model, host)]:
            entry["usable"] += 1
            entry["derived"] += derived_probability(row) is not None
    return out

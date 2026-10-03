"""A discarded response is a hole in the panel, so recover what is recoverable.

`llama` intermittently omits the closing quote on a string value, swallowing the
next key into it:

    {"probability": 0.83, "direction": "yes, confidence": 0.7, ...}
                                            ^ closing quote missing

Measured across the 21-22 Aug pilots: 2 of 16 calls, ~12%, both exactly this
shape. The model's answer is unambiguous -- 0.83, yes, 0.7 -- and only the
punctuation is malformed, so dropping the observation discards a good forecast
over a missing character.

It matters more for this model than most. `llama` is the panel's ONLY Meta model,
so a sustained 12% loss walks it toward the 80% coverage floor of
PREREGISTRATION.md §3.3 -- and losing it would take the panel from six vendor
families to five, which is a structural change to what the study can claim.

The repair runs ONLY after strict parsing has already failed, so it can never
reinterpret JSON that was valid to begin with. These tests hold that line: the
recovery cases, and just as importantly the cases it must NOT touch.
"""

import json

import pytest

from neff.providers import _extract_json

# The two responses that actually failed, copied from data/observations.jsonl.
REAL_FAILURES = [
    (
        '{"probability": 0.83, "direction": "yes, confidence": 0.7, '
        '"rationale": "Recent growth trend exceeds threshold."}',
        {"probability": 0.83, "direction": "yes", "confidence": 0.7},
    ),
    (
        '{"probability": 0.7, "direction": "yes, confidence": 0.8, '
        '"rationale": "Historical trends suggest growth"}',
        {"probability": 0.7, "direction": "yes", "confidence": 0.8},
    ),
]


class TestRealFailuresRecover:
    @pytest.mark.parametrize("raw,expected", REAL_FAILURES, ids=["pilot-1", "pilot-2"])
    def test_observed_llama_output_parses(self, raw, expected):
        got = _extract_json(raw)
        assert got is not None, "this exact string was thrown away in the pilot"
        for k, v in expected.items():
            assert got[k] == v, f"{k}: recovered {got[k]!r}, model meant {v!r}"

    def test_recovered_values_are_the_model_s_own(self, ):
        """The repair must not invent or shift a number. A wrong forecast is far
        worse than a missing one -- a hole is visible, a fabrication is not."""
        raw, expected = REAL_FAILURES[0]
        got = _extract_json(raw)
        assert got["probability"] == 0.83
        assert got["rationale"] == "Recent growth trend exceeds threshold."

    def test_rationale_survives_intact(self):
        raw = ('{"probability": 0.5, "direction": "no, confidence": 0.6, '
               '"rationale": "Mixed signals, no clear trend"}')
        got = _extract_json(raw)
        assert got["rationale"] == "Mixed signals, no clear trend"
        assert got["direction"] == "no"


class TestValidJsonIsNeverTouched:
    """The repair is a last resort. If it ever runs on parseable input it could
    silently alter a good observation."""

    @pytest.mark.parametrize(
        "raw",
        [
            '{"probability": 0.4, "direction": "no", "confidence": 0.9, "rationale": "x"}',
            '{"probability": 0.4, "rationale": "up, down, sideways"}',
            '{"a": "one, two", "b": 1}',
            '{"rationale": "CPI, PPI and payrolls all point the same way"}',
        ],
        ids=["clean", "comma-in-value", "comma-then-word", "commas-in-prose"],
    )
    def test_valid_input_round_trips_unchanged(self, raw):
        assert _extract_json(raw) == json.loads(raw)

    def test_a_comma_inside_a_properly_quoted_value_is_preserved(self):
        """`"rationale": "growth, inflation"` is legal JSON and must survive --
        this is the case a careless repair would corrupt."""
        raw = '{"direction": "yes", "rationale": "growth, inflation both rising"}'
        got = _extract_json(raw)
        assert got["rationale"] == "growth, inflation both rising"
        assert got["direction"] == "yes"

    def test_fenced_json_still_works(self):
        raw = '```json\n{"probability": 0.25, "direction": "no"}\n```'
        assert _extract_json(raw)["probability"] == 0.25

    def test_preamble_before_json_still_works(self):
        raw = 'Here is my forecast:\n{"probability": 0.6, "direction": "yes"}'
        assert _extract_json(raw)["probability"] == 0.6


class TestUnrecoverableStaysUnrecoverable:
    """Recovering too eagerly would be worse than failing. A missing observation
    is handled pairwise and reported (§5.4); a fabricated one is not detectable
    at all."""

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "I cannot provide a forecast.",
            "{",
            '{"probability": ',
            "not json at all",
            '{"probability": 0.92,',          # the truncated Gemini case
        ],
        ids=["empty", "refusal", "brace", "truncated-key", "prose", "gemini-truncation"],
    )
    def test_returns_none_rather_than_guessing(self, raw):
        assert _extract_json(raw) is None

    def test_repair_does_not_loop_forever(self):
        """The repair re-enters _extract_json; it must terminate."""
        assert _extract_json('{"a": "b, c": "d, e": "f, g":') is None


class TestCoverageImpact:
    """Why this is worth doing at all."""

    def test_recovery_rate_on_the_observed_failures(self):
        recovered = sum(1 for raw, _ in REAL_FAILURES if _extract_json(raw))
        assert recovered == len(REAL_FAILURES)

    def test_llama_is_the_only_meta_model(self):
        """Which is why its coverage carries a whole vendor family."""
        from neff.config import primary_panel

        meta = [m.key for m in primary_panel() if m.family == "meta"]
        assert meta == ["llama"]

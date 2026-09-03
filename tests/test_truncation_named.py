"""A reply cut off at the token cap is not a model that cannot write JSON.

Both arrive as `_extract_json(...) is None`, and until now both were filed as
`unparseable response`. That reading cost real time: across 1-2 Sep 2026,
`claude_sonnet` returned 7 such rows and its coverage line read 87% with the
implication that Sonnet could not follow the output format.

It follows the format fine. Its successful replies land in 60-105 output tokens.
The 7 failures were billed at exactly 400 -- `config.MAX_OUTPUT_TOKENS` -- every
one of them. Sonnet occasionally reasons in prose first and runs out of room
before it reaches the JSON object, which is a budget dial, not a roster problem.
The two call for opposite responses, so the log has to tell them apart.

The signal is the billed output count rather than a stop-reason field: the four
providers spell that four different ways, and the count is one we already record
and already reconcile against the ledger.
"""

import pytest

from neff import config
from neff.ledger import Ledger
from neff.providers import PROVIDERS, Provider, ask

# Copied from data/observations.jsonl, obs on 2026-09-01: Sonnet reasoning out
# loud about JPM's Q1 2015 revenue and being guillotined before the object.
REAL_TRUNCATION = (
    "Looking at this question, I need to determine if JPM's Q1 2015 revenue "
    "(the quarter following 2014-12-31) will exceed $23.16B.\n\nKey data points:"
    "\n- Q1 2014: $22.99B\n- Q2 2014: $24.45B\n\nJPM's Q1 2015 actual results "
    "(which I can reason about from historical knowledge): JPM reported Q1 2015 "
    "revenue of approximately $24.8B, which would c"
)


class _StubProvider(Provider):
    """Returns whatever it is told to, with whatever token count it is told to."""

    name = "stub"

    def __init__(self, text, output_tokens):
        self._text = text
        self._output_tokens = output_tokens

    def complete(self, spec, prompt, max_tokens, timeout):
        return self._text, spec.model_id, 100, self._output_tokens


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.jsonl", cap_usd=100.0,
                  arm_caps=dict(config.ARM_CAPS_USD))


@pytest.fixture
def spec():
    return config.primary_panel()[0]


def _ask_with(monkeypatch, ledger, spec, text, output_tokens, max_tokens=400):
    monkeypatch.setitem(PROVIDERS, spec.provider, _StubProvider(text, output_tokens))
    return ask(spec=spec, task_id="t1", prompt="Q?", ledger=ledger,
               arm=config.PRE_REGISTRATION_ARM, max_tokens=max_tokens)


class TestTruncationIsNamedNotGuessedAt:
    def test_a_reply_billed_at_the_cap_is_reported_as_truncated(
        self, monkeypatch, ledger, spec
    ):
        obs = _ask_with(monkeypatch, ledger, spec, REAL_TRUNCATION, 400)
        assert obs.forecast is None
        assert "truncated at max_tokens=400" in obs.error
        assert "unparseable response" not in obs.error

    def test_the_error_carries_the_number_needed_to_act_on_it(
        self, monkeypatch, ledger, spec
    ):
        """Whoever reads this in a log should not have to go and look up the cap."""
        obs = _ask_with(monkeypatch, ledger, spec, REAL_TRUNCATION, 400)
        assert "400 output tokens billed" in obs.error

    def test_malformed_json_well_under_the_cap_is_still_unparseable(
        self, monkeypatch, ledger, spec
    ):
        """The distinction only helps if it does not swallow the original case."""
        obs = _ask_with(monkeypatch, ledger, spec, "not json at all", 12)
        assert "unparseable response" in obs.error
        assert "truncated" not in obs.error

    def test_valid_json_at_exactly_the_cap_is_not_called_truncated(
        self, monkeypatch, ledger, spec
    ):
        """The check runs only after parsing has already failed, so a reply that
        happens to end on the cap boundary and still parses is untouched."""
        obs = _ask_with(
            monkeypatch, ledger, spec,
            '{"probability": 0.4, "direction": "no", "confidence": 0.6,'
            ' "rationale": "fits"}',
            400,
        )
        assert obs.error is None, obs.error
        assert obs.forecast == 0.4

    def test_a_truncated_call_still_books_the_tokens_it_burned(
        self, monkeypatch, ledger, spec
    ):
        """The money left the account whether or not the JSON arrived.

        This is why truncation is diagnosed here rather than raised from the
        provider: a raise unwinds past `ledger.record`, so the call would be
        retried twice more and all three would be invisible to the cap that
        exists to stop exactly that.
        """
        obs = _ask_with(monkeypatch, ledger, spec, REAL_TRUNCATION, 400)
        assert obs.usd > 0
        assert ledger.spent > 0

    def test_truncation_is_not_retried(self, monkeypatch, ledger, spec):
        """Temperature is 0 and the cap does not move, so attempts 2 and 3 would
        return the identical truncated reply at identical cost."""
        calls = []

        class _Counting(_StubProvider):
            def complete(self, spec, prompt, max_tokens, timeout):
                calls.append(1)
                return super().complete(spec, prompt, max_tokens, timeout)

        monkeypatch.setitem(PROVIDERS, spec.provider, _Counting(REAL_TRUNCATION, 400))
        ask(spec=spec, task_id="t1", prompt="Q?", ledger=ledger,
            arm=config.PRE_REGISTRATION_ARM, max_tokens=400)
        assert len(calls) == 1

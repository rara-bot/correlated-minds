"""A registered sensitivity had no data, and could never be given any.

PREREGISTRATION.md §5.4(a) names forecast granularity as one of three threats
that could produce our predicted result for reasons unrelated to the hypothesis,
and fixes the handling in advance. One of the three pre-committed responses is:
"for the models exposing logprobs, re-estimate on logprob-derived probabilities."
The plan then states which models those are -- gpt_mid, gpt_small, llama,
deepseek -- and says it was "confirmed by live call, not assumed".

`config.ModelSpec.supports_logprobs` was set for exactly those models.
`store.Observation.logprobs` existed. Nothing ever asked an API for them, and
**0 of 2,390 collected observations carried any**. The store is append-only, so
this was not a gap waiting to be filled: every collection day that passed was a
day the registered leg could never be run on.

Asking is a change to the request body of a live panel, so it is built so it
cannot cost an observation. `ask()` retries a ProviderError with an identical
body -- three attempts carrying the same rejected parameter would fail together,
which is precisely how qwen lost 2026-09-01 and 2026-09-07 to Novita (deviation
4). So the fallback lives in the provider: a 4xx that names the parameter is
retried once without it, and the observation lands exactly as it would have.
"""

import json

import pytest

from neff import config
from neff.ledger import Ledger
from neff.providers import (
    PROVIDERS,
    MAX_LOGPROB_POSITIONS,
    TOP_LOGPROBS,
    OpenAICompatProvider,
    OpenRouterProvider,
    ask,
)

BY_KEY = {m.key: m for m in config.PANEL}
LOGPROB_MODELS = [m for m in config.PANEL if m.supports_logprobs]

CONTENT = '{"probability": 0.62, "direction": "yes", "confidence": 0.7, "rationale": "r"}'


def _token(tok, lp=-0.1, top=(("0", -0.1), ("1", -2.3))):
    return {"token": tok, "logprob": lp,
            "top_logprobs": [{"token": t, "logprob": l} for t, l in top]}


def _payload(with_logprobs=True, tokens=None):
    out = {
        "model": "gpt-4.1-mini-2025-04-14",
        "choices": [{"message": {"content": CONTENT}}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 40},
    }
    if with_logprobs:
        toks = tokens if tokens is not None else [
            _token('{"'), _token("probability"), _token('":'),
            _token(" 0"), _token("."), _token("62"),
            _token(', "direction'), _token('": "yes'),
            _token(', "confidence": '), _token("0.7"),
        ]
        out["choices"][0]["logprobs"] = {"content": toks}
    return out


class FakeResponse:
    def __init__(self, payload, status_code=200, text=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def api(monkeypatch):
    """Record every request body sent, and serve a scripted list of responses."""
    box = {"sent": [], "responses": [FakeResponse(_payload())]}

    def fake_post(url, headers=None, json=None, timeout=None):
        box["sent"].append(json)
        i = min(len(box["sent"]) - 1, len(box["responses"]) - 1)
        return box["responses"][i]

    monkeypatch.setattr("neff.providers.httpx.post", fake_post)
    for k in ("OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(k, "test-key")
    return box


class TestTheRegisteredModelsAreTheOnesAsked:
    def test_the_roster_matches_what_the_plan_names(self):
        """§5.4(a) names four; a fifth (gpt_frontier) is secondary panel."""
        primary = {m.key for m in LOGPROB_MODELS if m.primary}
        assert primary == {"gpt_mid", "gpt_small", "llama", "deepseek"}

    def test_qwen_is_not_asked(self):
        """"`qwen` returns none in practice and is excluded from this leg.\""""
        assert BY_KEY["qwen"].supports_logprobs is False

    @pytest.mark.parametrize("spec", LOGPROB_MODELS, ids=lambda s: s.key)
    def test_every_declared_model_actually_asks(self, api, spec):
        provider = (OpenRouterProvider() if spec.provider == "openrouter"
                    else OpenAICompatProvider())
        provider.complete(spec, "q", 400, 10.0)
        assert api["sent"][0]["logprobs"] is True
        assert api["sent"][0]["top_logprobs"] == TOP_LOGPROBS

    def test_a_model_that_does_not_support_them_is_not_asked(self, api):
        """Sending the parameter to a host that rejects it is how a day is lost."""
        OpenAICompatProvider().complete(BY_KEY["qwen"], "q", 400, 10.0)
        assert "logprobs" not in api["sent"][0]

    def test_nothing_else_about_the_request_moves(self, api):
        spec = BY_KEY["gpt_mid"]
        OpenAICompatProvider().complete(spec, "the prompt", 400, 10.0)
        body = api["sent"][0]
        assert body["model"] == spec.model_id
        assert body["temperature"] == config.TEMPERATURE
        assert body["messages"] == [{"role": "user", "content": "the prompt"}]


class TestOnlyTheDigitsAreKept:
    """The full token stream with five alternatives each would add ~18 KB to
    every row -- a quarter-gigabyte of append-only file over 15 weeks to carry
    the same answer. §5.4(a) asks whether the emitted VALUE was nearly a
    different value, so the digit positions are the ones that answer it."""

    def test_digit_positions_are_captured_with_their_alternatives(self, api):
        done = OpenAICompatProvider().complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        assert done.logprobs
        assert [e["t"] for e in done.logprobs] == [" 0", "62", "0.7"]
        assert done.logprobs[0]["top"] == [["0", -0.1], ["1", -2.3]]

    def test_scaffolding_tokens_are_dropped(self, api):
        done = OpenAICompatProvider().complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        assert not any("direction" in e["t"] for e in done.logprobs)

    def test_the_number_of_positions_is_bounded(self, api):
        api["responses"] = [FakeResponse(_payload(
            tokens=[_token(str(i % 10)) for i in range(500)]))]
        done = OpenAICompatProvider().complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        assert len(done.logprobs) == MAX_LOGPROB_POSITIONS

    def test_absent_logprobs_read_as_none_not_empty(self, api):
        """"not offered" and "offered and empty" are different facts."""
        api["responses"] = [FakeResponse(_payload(with_logprobs=False))]
        done = OpenAICompatProvider().complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        assert done.logprobs is None

    def test_a_reply_with_no_digits_at_all_is_none(self, api):
        api["responses"] = [FakeResponse(_payload(tokens=[_token("refuse")]))]
        assert OpenAICompatProvider().complete(
            BY_KEY["gpt_mid"], "q", 400, 10.0).logprobs is None


class TestAskingCanNeverCostTheObservation:
    """The whole risk of this change, contained."""

    def test_a_rejection_is_retried_without_the_parameter(self, api):
        api["responses"] = [
            FakeResponse({}, 400, text='{"error":"logprobs is not supported"}'),
            FakeResponse(_payload(with_logprobs=False)),
        ]
        done = OpenAICompatProvider().complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        assert done.text == CONTENT, "the observation was lost to the new parameter"
        assert "logprobs" in api["sent"][0]
        assert "logprobs" not in api["sent"][1]
        assert done.logprobs is None

    def test_the_refusal_is_remembered_for_the_run(self, api):
        """Otherwise every call of every day pays two requests for the same fact."""
        api["responses"] = [
            FakeResponse({}, 400, text='{"error":"logprobs is not supported"}'),
            FakeResponse(_payload(with_logprobs=False)),
        ]
        provider = OpenAICompatProvider()
        provider.complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        provider.complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        assert len(api["sent"]) == 3
        assert "logprobs" not in api["sent"][2]

    def test_an_unrelated_failure_is_not_silently_downgraded(self, api):
        """A 429 must reach the ordinary retry path. Treating every error as a
        logprob rejection would drop the registered leg the first time a host
        rate-limited, with nothing saying the data had stopped arriving."""
        api["responses"] = [FakeResponse({}, 429, text="rate limited")]
        provider = OpenAICompatProvider()
        with pytest.raises(Exception):
            provider.complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        assert len(api["sent"]) == 1
        assert provider._logprobs_refused == set()

    def test_a_server_error_is_not_treated_as_a_rejection(self, api):
        api["responses"] = [FakeResponse({}, 500, text="logprobs exploded")]
        with pytest.raises(Exception):
            OpenAICompatProvider().complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        assert len(api["sent"]) == 1


class TestItReachesTheRecord:
    @pytest.fixture
    def ledger(self, tmp_path):
        return Ledger(tmp_path / "l.jsonl", cap_usd=100.0,
                      arm_caps=dict(config.ARM_CAPS_USD))

    def test_the_observation_carries_them(self, api, ledger, monkeypatch):
        monkeypatch.setitem(PROVIDERS, "openai", OpenAICompatProvider())
        obs = ask(spec=BY_KEY["gpt_mid"], task_id="t1", prompt="Q?", ledger=ledger,
                  arm=config.PRE_REGISTRATION_ARM, max_tokens=400)
        assert obs.forecast == 0.62
        assert obs.logprobs and obs.logprobs[0]["t"] == " 0"

    def test_they_survive_the_jsonl_round_trip(self, api, ledger, monkeypatch, tmp_path):
        from neff.store import JsonlStore

        monkeypatch.setitem(PROVIDERS, "openai", OpenAICompatProvider())
        obs = ask(spec=BY_KEY["gpt_mid"], task_id="t1", prompt="Q?", ledger=ledger,
                  arm=config.PRE_REGISTRATION_ARM, max_tokens=400)
        store = JsonlStore(tmp_path / "obs.jsonl")
        store.append(obs)
        assert store.read_all()[0]["logprobs"][0]["t"] == " 0"

    def test_a_model_outside_the_leg_stores_none(self, api, ledger, monkeypatch):
        monkeypatch.setitem(PROVIDERS, "openrouter", OpenRouterProvider())
        obs = ask(spec=BY_KEY["qwen"], task_id="t1", prompt="Q?", ledger=ledger,
                  arm=config.PRE_REGISTRATION_ARM, max_tokens=400)
        assert obs.logprobs is None

"""PREREGISTRATION.md 11, deviation 29: when no host will take `logprobs`, ask without.

On 2026-11-24 DigitalOcean left deepseek/deepseek-v3.2 on OpenRouter. It was the
last host that served deepseek's request with `logprobs`; the three that remain
advertise temperature and max_tokens but not logprobs. Under `require_parameters`
(deviation 4) OpenRouter then has nowhere to send the call and answers

    HTTP 404 {"error":{"message":"No endpoints found that can handle the
    requested parameters. ..."}}

The reissue-without-logprobs path of deviation 10 looked for a 4xx that NAMES the
parameter, so it never fired, and deepseek lost all 27 answers on 2026-11-24 and
again on 2026-11-25. These tests hold the narrow widening that closes that gap:
this one reply, on a call that carried `logprobs`, is reissued once without them,
and nothing else about the request moves.
"""

import json

import pytest

from neff import config
from neff.providers import (
    NO_HOST_FOR_PARAMETERS,
    OpenRouterProvider,
    _rejects_logprobs,
)

BY_KEY = {m.key: m for m in config.PANEL}
DEEPSEEK = BY_KEY["deepseek"]

CONTENT = '{"probability": 0.62, "direction": "yes", "confidence": 0.7, "rationale": "r"}'

# The body recorded on every deepseek row of 2026-11-24 and 2026-11-25 (the row
# keeps the first 300 characters; OpenRouter's code field is restored here).
RECORDED_404 = (
    '{"error":{"message":"No endpoints found that can handle the requested '
    'parameters. To learn more about provider routing, visit: '
    'https://openrouter.ai/docs/guides/routing/provider-selection","code":404}}'
)


def _ok(host="DeepInfra"):
    return {
        "model": DEEPSEEK.model_id,
        "provider": host,
        "choices": [{"message": {"content": CONTENT}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }


class FakeResponse:
    def __init__(self, payload, status_code=200, text=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def api(monkeypatch):
    box = {"sent": [], "responses": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        box["sent"].append(json)
        i = min(len(box["sent"]) - 1, len(box["responses"]) - 1)
        return box["responses"][i]

    monkeypatch.setattr("neff.providers.httpx.post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    return box


class TestTheRecordedReply:
    def test_it_does_not_name_logprobs(self):
        """Why deviation 10's reissue never fired on 24 and 25 Nov."""
        assert "logprob" not in RECORDED_404.lower()

    def test_it_is_now_read_as_a_refusal_of_logprobs(self):
        assert _rejects_logprobs(FakeResponse({}, 404, text=RECORDED_404))

    def test_the_phrase_is_matched_whatever_its_case(self):
        assert NO_HOST_FOR_PARAMETERS == NO_HOST_FOR_PARAMETERS.lower()
        assert _rejects_logprobs(FakeResponse({}, 404, text=RECORDED_404.upper()))


class TestTheWideningStaysNarrow:
    def test_a_404_saying_anything_else_is_not_a_refusal(self):
        """A missing model is a retirement, for the health check and the student."""
        body = '{"error":{"message":"No endpoints found for deepseek/deepseek-v3.2.","code":404}}'
        assert not _rejects_logprobs(FakeResponse({}, 404, text=body))

    def test_a_rate_limit_is_not_a_refusal(self):
        assert not _rejects_logprobs(FakeResponse({}, 429, text="rate limited"))

    def test_a_server_error_quoting_the_phrase_is_not_a_refusal(self):
        assert not _rejects_logprobs(FakeResponse({}, 503, text=RECORDED_404))


class TestTheAnswerIsNoLongerLost:
    def test_the_call_is_reissued_without_logprobs_and_lands(self, api):
        api["responses"] = [FakeResponse({}, 404, text=RECORDED_404), FakeResponse(_ok())]
        done = OpenRouterProvider().complete(DEEPSEEK, "Q?", 400, 10.0)
        assert done.text == CONTENT
        assert done.logprobs is None
        assert done.upstream_provider == "DeepInfra"
        assert api["sent"][0].get("logprobs") is True
        assert "logprobs" not in api["sent"][1]
        assert "top_logprobs" not in api["sent"][1]

    def test_nothing_else_about_the_request_moves(self, api):
        api["responses"] = [FakeResponse({}, 404, text=RECORDED_404), FakeResponse(_ok())]
        OpenRouterProvider().complete(DEEPSEEK, "Q?", 400, 10.0)
        first, second = dict(api["sent"][0]), dict(api["sent"][1])
        first.pop("logprobs"), first.pop("top_logprobs")
        assert first == second
        assert second["provider"]["require_parameters"] is True, "deviation 4 still holds"
        assert second["temperature"] == 0

    def test_the_refusal_is_remembered_for_the_run_only(self, api):
        """27 calls a day pay for the discovery once; tomorrow's run asks again,
        so if a host that takes logprobs comes back, the leg resumes by itself."""
        api["responses"] = [FakeResponse({}, 404, text=RECORDED_404), FakeResponse(_ok())]
        provider = OpenRouterProvider()
        provider.complete(DEEPSEEK, "Q?", 400, 10.0)
        provider.complete(DEEPSEEK, "Q?", 400, 10.0)
        assert len(api["sent"]) == 3
        assert "logprobs" not in api["sent"][2]
        assert OpenRouterProvider()._logprobs_refused == set()

    def test_if_no_host_takes_it_even_without_logprobs_the_row_fails(self, api):
        """Then the missing parameter is not logprobs, and the failure is recorded
        as it is rather than retried into something else."""
        api["responses"] = [FakeResponse({}, 404, text=RECORDED_404)]
        with pytest.raises(Exception) as err:
            OpenRouterProvider().complete(DEEPSEEK, "Q?", 400, 10.0)
        assert "404" in str(err.value)
        assert len(api["sent"]) == 2

    def test_a_model_never_asked_for_logprobs_is_never_reissued(self, api):
        """qwen is outside the logprob leg (5.4(a)); its 404 stays a 404."""
        qwen = BY_KEY["qwen"]
        assert not qwen.supports_logprobs
        api["responses"] = [FakeResponse({}, 404, text=RECORDED_404)]
        with pytest.raises(Exception):
            OpenRouterProvider().complete(qwen, "Q?", 400, 10.0)
        assert len(api["sent"]) == 1

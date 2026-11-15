"""An HTTP 200 is not always an answer, and a fallback is not always a host.

Between 2026-11-03 and 2026-11-13 deepseek lost 23 of 297 answers, 10 of them on
2026-11-09, to two faults of its transport. The model was fine on every row
around them.

THE FALLBACK THAT COULD NOT ANSWER. DigitalOcean served deepseek that fortnight.
When it throttled, OpenRouter fell back to AtlasCloud, which rejected the request:

    HTTP 400 -- {"code":400,"msg":"invalid request params"}
    (provider_name: AtlasCloud, previous_errors: DigitalOcean 429)

Probed 2026-11-14: AtlasCloud answers the same request once `logprobs` is left
out, and no third host accepts the request as sent. The 400 names no parameter,
so the reissue-without-logprobs path (deviation 10) did not see it; it is not a
429, so the wait (deviation 11) did not see it; and three attempts inside eight
seconds all took the same road. 13 rows.

THE REPLY THAT CARRIED NOTHING. OpenRouter sends the status line when a host
accepts the request. If the host then fails, the reply is a 200 whose body holds
only an error object; a host that is warming up can send a 200 with no content.
The provider read the status, found no text, and the row was filed as
"unparseable response" -- the label for a model that will not follow the format
-- without one retry. 10 rows, and 9 of qwen's: no text, no tokens billed, no
host named.

PREREGISTRATION.md 11, deviation 28 ignores the one host and raises the empty
reply as the failed call it is. These tests hold both, and hold the line on the
other side: what a model actually said is still an observation, never retried.
"""

import json

import pytest

from neff import config, providers
from neff.ledger import Ledger
from neff.providers import (
    OpenAICompatProvider,
    OpenRouterProvider,
    ProviderError,
    RateLimitAllowance,
    _rate_limited,
    _rejects_logprobs,
    ask,
)

BY_KEY = {m.key: m for m in config.PANEL}
DEEPSEEK = BY_KEY["deepseek"]

# Verbatim from the record: the error on the deepseek row lost on 2026-11-04,
# after "failed after 3 attempts: ProviderError: ".
RECORDED_400 = (
    'openrouter HTTP 400: {"error":{"message":"Provider returned error","code":400,'
    '"metadata":{"raw":"{\\"code\\":400,\\"msg\\":\\"invalid request params\\"}",'
    '"provider_name":"AtlasCloud","is_byok":false,"previous_errors":[{"code":429,'
    '"message":"Provider returned error","provider_name":"DigitalOcean","raw":'
    '"deepseek/deepseek-v3.2 '
)

CONTENT = ('{"probability": 0.62, "direction": "yes", "confidence": 0.7, '
           '"rationale": "r"}')

ANSWER = {
    "choices": [{"message": {"content": CONTENT}}],
    "usage": {"prompt_tokens": 590, "completion_tokens": 45},
    "model": "deepseek/deepseek-v3.2",
    "provider": "DigitalOcean",
}
# What OpenRouter documents for a host that accepts the request and then fails.
ERROR_IN_200 = {"error": {"message": "Provider returned error", "code": 502,
                          "metadata": {"provider_name": "DigitalOcean"}}}
THROTTLE_IN_200 = {"error": {"message": "Provider returned error", "code": 429,
                             "metadata": {"provider_name": "DigitalOcean"}}}
# What it documents for a host that is warming up.
NO_CONTENT = {"choices": [{"message": {"content": ""}}],
              "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
NULL_CONTENT = {"choices": [{"message": {"content": None}}], "usage": None}
# The model's own doing: the whole budget spent, no JSON reached.
SPENT_BUDGET = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 590, "completion_tokens": 400},
                "model": "deepseek/deepseek-v3.2", "provider": "DigitalOcean"}
PROSE = {"choices": [{"message": {"content": "About sixty percent, I think."}}],
         "usage": {"prompt_tokens": 590, "completion_tokens": 9},
         "model": "deepseek/deepseek-v3.2", "provider": "DigitalOcean"}


class Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def replies(monkeypatch):
    """Answer each request with the next scripted body; count the requests."""
    box = {"queue": [], "calls": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        box["calls"] += 1
        body = box["queue"].pop(0) if len(box["queue"]) > 1 else box["queue"][0]
        return Response(body)

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return box


@pytest.fixture
def slept(monkeypatch):
    """Record every sleep instead of taking it."""
    record = []
    monkeypatch.setattr(providers.time, "sleep", record.append)
    return record


@pytest.fixture
def asking(replies, tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl", cap_usd=100.0,
                    arm_caps=dict(config.ARM_CAPS_USD))

    def go(bodies, rate_limits=None):
        replies["queue"] = list(bodies)
        return ask(spec=DEEPSEEK, task_id="t1", prompt="Q?", ledger=ledger,
                   arm=config.PRE_REGISTRATION_ARM, max_tokens=400,
                   rate_limits=rate_limits)

    return go


def complete(replies, body, provider=None):
    replies["queue"] = [body]
    return (provider or OpenRouterProvider()).complete(DEEPSEEK, "Q?", 400, 10.0)


class TestWhyTheRecordedFallbackWasLost:
    def test_the_400_is_not_a_rate_limit_though_it_quotes_one(self):
        """The 429 is DigitalOcean's, quoted inside AtlasCloud's 400. The wait is
        anchored on the status so that a quoted 429 does not count -- which is
        right, and is why nothing waited."""
        assert "429" in RECORDED_400
        assert not _rate_limited(ProviderError(RECORDED_400))

    def test_the_400_does_not_name_the_parameter_it_rejects(self):
        """So the reissue without `logprobs` never fired either."""
        body = RECORDED_400.split(": ", 1)[1]

        class Rejected:
            status_code = 400
            text = body

        assert not _rejects_logprobs(Rejected())

    def test_so_the_host_is_ignored(self):
        ignored = OpenRouterProvider.EXTRA_BODY["provider"]["ignore"]
        assert "AtlasCloud" in ignored
        assert "Novita" in ignored, "deviation 4 still stands"


class TestAReplyThatCarriesNothingIsAFailedCall:
    def test_an_error_inside_a_200_is_raised_with_the_status_it_reports(self, replies):
        with pytest.raises(ProviderError,
                           match=r"^openrouter HTTP 502: error inside an HTTP 200 reply"):
            complete(replies, ERROR_IN_200)

    def test_a_429_inside_a_200_is_still_a_rate_limit(self, replies):
        with pytest.raises(ProviderError) as raised:
            complete(replies, THROTTLE_IN_200)
        assert _rate_limited(raised.value)

    @pytest.mark.parametrize("code", ["rate_limited", None, 200, 42])
    def test_an_error_without_an_http_code_keeps_the_200(self, replies, code):
        body = {"error": {"message": "x", "code": code}}
        with pytest.raises(ProviderError, match=r"^openrouter HTTP 200: error inside"):
            complete(replies, body)

    def test_an_error_that_is_not_an_object_is_raised_too(self, replies):
        with pytest.raises(ProviderError, match=r"^openrouter HTTP 200: error inside"):
            complete(replies, {"error": "upstream closed the connection"})

    @pytest.mark.parametrize("body", [NO_CONTENT, NULL_CONTENT, {"choices": []}, {}],
                             ids=["empty", "null", "no-choices", "empty-body"])
    def test_no_content_and_no_tokens_is_an_empty_reply(self, replies, body):
        with pytest.raises(ProviderError, match=r"^openrouter HTTP 200: empty reply"):
            complete(replies, body)

    def test_it_holds_for_every_provider_that_shares_the_shape(self, replies):
        with pytest.raises(ProviderError, match=r"^openai HTTP 200: empty reply"):
            replies["queue"] = [NO_CONTENT]
            OpenAICompatProvider().complete(BY_KEY["gpt_mid"], "Q?", 400, 10.0)


class TestWhatTheModelSaidIsStillAnObservation:
    def test_an_answer_arrives_exactly_as_before(self, replies):
        result = complete(replies, ANSWER)
        assert result.text == CONTENT
        assert (result.input_tokens, result.output_tokens) == (590, 45)
        assert result.model_id == "deepseek/deepseek-v3.2"
        assert result.upstream_provider == "DigitalOcean"

    def test_a_reply_that_spent_its_budget_is_recorded_not_retried(
            self, asking, replies, slept):
        obs = asking([SPENT_BUDGET])
        assert replies["calls"] == 1 and slept == []
        assert "truncated at max_tokens=400" in obs.error
        assert obs.output_tokens == 400

    def test_a_reply_that_is_not_json_is_recorded_not_retried(
            self, asking, replies, slept):
        obs = asking([PROSE])
        assert replies["calls"] == 1 and slept == []
        assert obs.error == " | unparseable response"
        assert obs.raw_response == "About sixty percent, I think."
        assert obs.upstream_provider == "DigitalOcean"


class TestTheRowIsRetriedLikeAnyOtherFailedCall:
    def test_a_row_that_would_have_been_lost_now_lands(self, asking, replies, slept):
        obs = asking([ERROR_IN_200, ANSWER])
        assert obs.forecast == 0.62
        assert not obs.error
        assert obs.upstream_provider == "DigitalOcean"
        assert replies["calls"] == 2 and slept == [2.0]

    def test_an_empty_reply_gets_the_ordinary_retries(self, asking, replies, slept):
        obs = asking([NO_CONTENT, NO_CONTENT, ANSWER])
        assert obs.forecast == 0.62
        assert replies["calls"] == 3 and slept == [2.0, 4.0]

    def test_a_throttle_inside_a_200_is_waited_out(self, asking, replies, slept):
        obs = asking([THROTTLE_IN_200, ANSWER], RateLimitAllowance())
        assert obs.forecast == 0.62
        assert slept == [15.0]

    def test_a_row_that_still_fails_says_why(self, asking, replies, slept):
        """The cause, not "unparseable response": the model never spoke."""
        obs = asking([NO_CONTENT])
        assert replies["calls"] == 3 and slept == [2.0, 4.0]
        assert obs.forecast is None
        assert obs.error.startswith(
            "failed after 3 attempts: ProviderError: openrouter HTTP 200: empty reply")
        assert "unparseable" not in obs.error
        assert obs.usd == 0.0 and obs.output_tokens == 0

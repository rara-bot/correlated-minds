"""Gemini nearly cost the study a panel member, three different ways.

The 21 Aug pilot scored `gemini_flash_pro` at **0 of 8 usable observations**.
Sustained, that is a model below the 80% coverage floor of PREREGISTRATION.md
§3.3 and therefore out of the primary panel -- and it is half of the Google
within-family pair, so H3 would have dropped from three within-family pairs to
two. Three within-family pairs is the whole reason the panel went from seven
models to nine (AUDIT.md finding 6).

Three separate causes, none of which raised anything at the time:

1. `maxOutputTokens` is a budget SHARED with internal thinking, and the model
   expands its thinking to fill it. At the collection budget of 400: thoughts=383,
   visible=13, `finishReason=MAX_TOKENS`, and the answer arrived truncated as
   `{"probability": 0.92,`. The JSON parser returned None and the observation was
   dropped with nothing in the log explaining why.

2. Thinking tokens are BILLED AS OUTPUT and were not counted. A call burning 867
   thinking tokens and emitting 65 visible ones was recorded as 65 -- a 14x
   undercount at the panel's most expensive output rate. The $200 cap is enforced
   against recorded spend, so this is the cap quietly ceasing to protect the
   account.

3. The fix for (1) broke the other Google model: `gemini-3.5-flash-lite` answers
   HTTP 400 to a request containing `thinkingConfig` at all.

And underneath all three, the finding that actually decides whether the roster
can stand: the free tier allows **20 requests per day** for `gemini-3.5-flash`,
against a panel that asks 25.
"""

import json

import pytest

from neff import providers
from neff.config import PANEL, TASKS_PER_DAY

BY_KEY = {m.key: m for m in PANEL}
REASONING = BY_KEY["gemini_flash_pro"]      # thinking_budget = 0
LITE = BY_KEY["gemini_flash"]               # thinking_budget = None


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _usage(prompt=346, candidates=65, thoughts=0):
    u = {"promptTokenCount": prompt, "candidatesTokenCount": candidates}
    if thoughts:
        u["thoughtsTokenCount"] = thoughts
    return u


def _ok_payload(text='{"probability": 0.5}', finish="STOP", **usage_kw):
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": finish}
        ],
        "usageMetadata": _usage(**usage_kw),
        "modelVersion": "gemini-3.5-flash",
    }


@pytest.fixture
def captured(monkeypatch):
    """Capture the request body the provider sends."""
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        return FakeResponse(sent.get("_payload", _ok_payload()))

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    return sent


def _call(spec, max_tokens=400):
    return providers.GoogleProvider().complete(
        spec=spec, prompt="q", max_tokens=max_tokens, timeout=10.0
    )


class TestThinkingConfigIsPerModel:
    def test_reasoning_model_gets_thinking_disabled(self, captured):
        _call(REASONING)
        cfg = captured["json"]["generationConfig"]
        assert cfg["thinkingConfig"] == {"thinkingBudget": 0}

    def test_lite_model_gets_no_thinking_field_at_all(self, captured):
        """`gemini-3.5-flash-lite` returns HTTP 400 `Request contains an invalid
        argument` if `thinkingConfig` is present, so it must be absent -- not
        present-and-null."""
        _call(LITE)
        assert "thinkingConfig" not in captured["json"]["generationConfig"]

    def test_config_still_carries_the_registered_temperature(self, captured):
        _call(REASONING)
        assert captured["json"]["generationConfig"]["temperature"] == providers.TEMPERATURE
        assert providers.TEMPERATURE == 0.0

    def test_max_output_tokens_is_passed_through(self, captured):
        _call(REASONING, max_tokens=400)
        assert captured["json"]["generationConfig"]["maxOutputTokens"] == 400

    def test_the_reasoning_model_is_configured_in_the_roster(self):
        """If this flips back to None the truncation returns silently."""
        assert REASONING.thinking_budget == 0
        assert LITE.thinking_budget is None


class TestThinkingTokensAreBilled:
    def test_thoughts_count_toward_output_tokens(self, captured):
        """Google bills thinking as output. Recording only the visible tokens
        understated this model by 14x."""
        captured["_payload"] = _ok_payload(candidates=65, thoughts=867)
        _text, _mid, in_tok, out_tok = _call(REASONING)
        assert in_tok == 346
        assert out_tok == 65 + 867

    def test_absent_thoughts_field_is_not_an_error(self, captured):
        captured["_payload"] = _ok_payload(candidates=60)
        _t, _m, _i, out_tok = _call(LITE)
        assert out_tok == 60

    def test_cost_reflects_the_thinking_tokens(self, captured):
        captured["_payload"] = _ok_payload(candidates=65, thoughts=867)
        _t, _m, in_tok, out_tok = _call(REASONING)
        billed = REASONING.price.estimate(in_tok, out_tok)
        visible_only = REASONING.price.estimate(in_tok, 65)
        assert billed > 5 * visible_only


class TestTruncationIsLoud:
    def test_max_tokens_finish_reason_raises(self, captured):
        """A truncated response parsed to None and was recorded as a generic
        `unparseable response` -- true, but it named the symptom rather than the
        cause, and the cause was ours."""
        captured["_payload"] = _ok_payload(
            text='{"probability": 0.92,', finish="MAX_TOKENS", candidates=13, thoughts=383
        )
        with pytest.raises(providers.ProviderError, match="truncated"):
            _call(REASONING)

    def test_the_error_names_the_budget_and_the_split(self, captured):
        captured["_payload"] = _ok_payload(
            text='{"probability": 0.92,', finish="MAX_TOKENS", candidates=13, thoughts=383
        )
        with pytest.raises(providers.ProviderError) as exc:
            _call(REASONING, max_tokens=400)
        msg = str(exc.value)
        assert "maxOutputTokens=400" in msg
        assert "13" in msg and "383" in msg

    def test_a_normal_stop_does_not_raise(self, captured):
        captured["_payload"] = _ok_payload(finish="STOP")
        text, _m, _i, _o = _call(REASONING)
        assert text


class TestFreeTierQuotaIsNamed:
    """MEASURED 21 Aug 2026: 20 requests/day for gemini-3.5-flash on the free
    tier, against a panel that asks TASKS_PER_DAY = 25. A generic "rate limited"
    reads as transient; the quota number is what says the study cannot run as
    designed on this billing plan."""

    QUOTA_429 = {
        "error": {
            "code": 429,
            "message": "You exceeded your current quota",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [
                        {
                            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                            "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                            "quotaValue": "20",
                        }
                    ],
                }
            ],
        }
    }

    def test_daily_quota_is_extracted(self):
        assert providers.google_daily_quota(self.QUOTA_429) == 20

    def test_missing_quota_detail_returns_none(self):
        assert providers.google_daily_quota({"error": {"code": 429}}) is None

    def test_per_minute_quota_is_not_mistaken_for_a_daily_one(self):
        payload = {
            "error": {
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {"quotaId": "GenerateRequestsPerMinutePerProject", "quotaValue": "5"}
                        ],
                    }
                ]
            }
        }
        assert providers.google_daily_quota(payload) is None

    def test_429_message_names_the_quota_and_the_shortfall(self, captured, monkeypatch):
        def fake_post(url, headers=None, json=None, timeout=None):
            return FakeResponse(self.QUOTA_429, status_code=429)

        monkeypatch.setattr(providers.httpx, "post", fake_post)
        with pytest.raises(providers.ProviderError) as exc:
            _call(REASONING)
        msg = str(exc.value)
        assert "20 requests/day" in msg
        assert f"{TASKS_PER_DAY} questions/day" in msg
        assert "80%" in msg
        assert "BEFORE the freeze" in msg

    def test_a_quota_above_the_panel_size_is_not_alarming(self, captured, monkeypatch):
        payload = json.loads(json.dumps(self.QUOTA_429))
        payload["error"]["details"][0]["violations"][0]["quotaValue"] = "1000"

        def fake_post(url, headers=None, json=None, timeout=None):
            return FakeResponse(payload, status_code=429)

        monkeypatch.setattr(providers.httpx, "post", fake_post)
        with pytest.raises(providers.ProviderError) as exc:
            _call(REASONING)
        assert "BEFORE the freeze" not in str(exc.value)

    def test_unparseable_429_still_produces_an_error(self, monkeypatch):
        class Bad:
            status_code = 429
            text = "not json"

            def json(self):
                raise ValueError("nope")

        monkeypatch.setattr(providers.httpx, "post", lambda *a, **k: Bad())
        monkeypatch.setenv("GOOGLE_API_KEY", "k")
        with pytest.raises(providers.ProviderError, match="429"):
            _call(REASONING)


class TestTheCoverageFloorMath:
    """The arithmetic that makes this blocking rather than annoying."""

    def test_twenty_a_day_cannot_clear_the_eighty_percent_floor(self):
        quota = 20
        assert quota < TASKS_PER_DAY
        best_coverage = quota / TASKS_PER_DAY
        assert best_coverage <= 0.80, (
            "a model capped at 20 requests/day cannot exceed the §3.3 floor"
        )

    def test_losing_this_model_costs_h3_a_within_family_pair(self):
        from neff.config import primary_panel

        fams = {}
        for m in primary_panel():
            fams.setdefault(m.family, []).append(m.key)
        within = sum(len(v) * (len(v) - 1) // 2 for v in fams.values())
        assert within == 3

        without = {f: [k for k in v if k != "gemini_flash_pro"] for f, v in fams.items()}
        within_without = sum(len(v) * (len(v) - 1) // 2 for v in without.values())
        assert within_without == 2, "dropping it must visibly cost a within-family pair"

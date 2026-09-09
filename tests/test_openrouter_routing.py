"""qwen lost two entire days to an upstream host, not to the model.

OpenRouter is an aggregator: it chooses an upstream per request, and the choice
is invisible unless the response is asked for it. Probed 2026-09-09, one host
each: qwen -> DeepInfra, llama -> Parasail, deepseek -> Venice. When qwen was
routed to Novita instead, every call that day returned

    HTTP 400 INVALID_REQUEST_BODY -- "model: qwen/qwen-2.5-72b-instruct does
    not support endpoint: completions"   (provider_name: Novita)

and all three retries landed on the same host, so the retry loop could not save
it. 2026-09-01 and 2026-09-07 lost all 27 qwen observations each.

That is not cosmetic. PREREGISTRATION.md §5.6 excludes any model below 80%
usable coverage from the PRIMARY PANEL, and those two days put qwen at 72.9%
all-time. One more and a registered panel member is gone, taking M from 9 to 8 --
and M sits inside the estimator itself, N_eff = M / (1 + (M-1) rho_bar).

The same shape of failure already nearly cost the study gemini_flash_pro
(tests/test_google_provider.py). The lesson that generalises is that a model can
be lost by its transport while the model itself is fine.
"""

import json

import pytest

from neff import providers
from neff.config import PANEL

BY_KEY = {m.key: m for m in PANEL}
OPENROUTER_MODELS = [m for m in PANEL if m.provider == "openrouter"]


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _ok():
    return {
        "choices": [{"message": {"content": '{"probability": 0.5}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "model": "qwen/qwen-2.5-72b-instruct",
    }


@pytest.fixture
def sent(monkeypatch):
    box = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        box["url"] = url
        box["json"] = json
        return FakeResponse(_ok())

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return box


class TestTheRoutingGuardIsSent:
    def test_openrouter_requests_carry_a_routing_preference(self, sent):
        spec = BY_KEY["qwen"]
        providers.OpenRouterProvider().complete(spec, "q", 400, 10.0)
        assert "provider" in sent["json"], (
            "no routing preference sent -- the upstream is whatever the "
            "aggregator picks, which is how two days were lost"
        )

    def test_the_observed_bad_upstream_is_excluded(self, sent):
        providers.OpenRouterProvider().complete(BY_KEY["qwen"], "q", 400, 10.0)
        assert "Novita" in sent["json"]["provider"]["ignore"]

    def test_hosts_that_cannot_serve_the_request_are_filtered(self, sent):
        """The general form. Naming Novita fixes the failure we saw; this is
        what catches the next host that cannot serve the call as sent."""
        providers.OpenRouterProvider().complete(BY_KEY["qwen"], "q", 400, 10.0)
        assert sent["json"]["provider"]["require_parameters"] is True

    def test_fallbacks_stay_on(self, sent):
        """A filter that narrows to one host would trade an intermittent
        failure for a single point of failure."""
        providers.OpenRouterProvider().complete(BY_KEY["qwen"], "q", 400, 10.0)
        assert sent["json"]["provider"]["allow_fallbacks"] is True

    @pytest.mark.parametrize("spec", OPENROUTER_MODELS, ids=lambda s: s.key)
    def test_every_openrouter_model_is_covered(self, sent, spec):
        """Three of the ten panel members route through the aggregator, so the
        guard belongs to the provider, not to qwen."""
        providers.OpenRouterProvider().complete(spec, "q", 400, 10.0)
        assert sent["json"]["provider"]["require_parameters"] is True


class TestItDoesNotLeakToDirectVendors:
    def test_openai_sends_no_routing_field(self, sent):
        """OpenAI serves its own models. A `provider` key in that body is at
        best ignored and at worst a 400."""
        providers.OpenAICompatProvider().complete(BY_KEY["gpt_mid"], "q", 400, 10.0)
        assert "provider" not in sent["json"]

    def test_the_registered_request_shape_is_otherwise_unchanged(self, sent):
        """The guard must add routing and change nothing that reaches the model:
        same model id, same temperature, same prompt, same token ceiling."""
        spec = BY_KEY["qwen"]
        providers.OpenRouterProvider().complete(spec, "the prompt", 400, 10.0)
        body = sent["json"]
        assert body["model"] == spec.model_id
        assert body["temperature"] == providers.TEMPERATURE
        assert body["messages"] == [{"role": "user", "content": "the prompt"}]
        assert body["max_tokens"] == 400

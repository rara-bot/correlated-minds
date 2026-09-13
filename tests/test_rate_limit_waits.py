"""A rate limit is a queue, not a verdict.

`qwen` has had one usable host since deviation 4 put Novita on the ignore list:
OpenRouter lists DeepInfra and Novita for `qwen/qwen-2.5-72b-instruct`, and
nothing else. When DeepInfra's shared pool throttles, the call comes back

    HTTP 429 -- "qwen/qwen-2.5-72b-instruct is temporarily rate-limited
    upstream. Please retry shortly"

and `ask()` used to spend all three attempts inside six seconds. That cost 24 of
27 qwen observations on 2026-09-09 and 5 more on 2026-09-11, with qwen already
under the 80% coverage floor that removes a panel member (PREREGISTRATION.md
§3.3, §5.6). A failed row is written and then reads as done, so the evening
backup run cannot recover it. The only place left to wait is inside the call.

Waiting has its own way to lose a day. The workflow kills the job at 45 minutes,
before it has committed anything, so every wait is drawn from one allowance for
the whole run. These tests hold both lines: wait long enough to outlast an
episode, and never long enough to cost the day.
"""

import json
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from neff import collect, config, providers
from neff.ledger import Ledger
from neff.providers import (
    PROVIDERS,
    RATE_LIMIT_ALLOWANCE_S,
    RATE_LIMIT_WAITS_S,
    Completion,
    OpenRouterProvider,
    ProviderError,
    RateLimitAllowance,
    _rate_limited,
    ask,
)
from neff.store import JsonlStore, Task

ROOT = Path(__file__).resolve().parent.parent
BY_KEY = {m.key: m for m in config.PANEL}

# Verbatim from the record: the error on the first qwen row lost on 2026-09-09.
RECORDED_429 = (
    'openrouter HTTP 429: {"error":{"message":"Provider returned error","code":429,'
    '"metadata":{"raw":"qwen/qwen-2.5-72b-instruct is temporarily rate-limited '
    'upstream. Please retry shortly, or add your own key to accumulate your rate '
    'limits: https://openrouter.ai/settings/integrations","provider_name":"DeepInfra",'
    '"is_byok":fa'
)

CONTENT = ('{"probability": 0.62, "direction": "yes", "confidence": 0.7, '
           '"rationale": "r"}')


def limited():
    return ProviderError(RECORDED_429)


class Scripted:
    """A provider that fails with the scripted errors in order, then answers."""

    name = "scripted"

    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    def complete(self, spec, prompt, max_tokens, timeout):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return Completion(text=CONTENT, model_id=spec.model_id, input_tokens=10,
                          output_tokens=10, upstream_provider="DeepInfra")


class Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return self._body


@pytest.fixture
def slept(monkeypatch):
    """Record every sleep instead of taking it."""
    record = []
    monkeypatch.setattr(providers.time, "sleep", record.append)
    return record


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.jsonl", cap_usd=100.0,
                  arm_caps=dict(config.ARM_CAPS_USD))


@pytest.fixture
def asking(monkeypatch, ledger):
    def go(errors, rate_limits):
        provider = Scripted(errors)
        monkeypatch.setitem(PROVIDERS, "openrouter", provider)
        obs = ask(spec=BY_KEY["qwen"], task_id="t1", prompt="Q?", ledger=ledger,
                  arm=config.PRE_REGISTRATION_ARM, max_tokens=400,
                  rate_limits=rate_limits)
        return obs, provider

    return go


class TestTheRecordedFailureIsTheOneRecognised:
    def test_the_fixture_is_the_record_not_an_invention(self):
        rows = (json.loads(line) for line in
                (ROOT / "data" / "observations.jsonl").read_text().splitlines()
                if line.strip())
        assert any(RECORDED_429 in (r.get("error") or "") for r in rows)

    def test_the_deepinfra_throttle_is_a_rate_limit(self):
        assert _rate_limited(limited())

    @pytest.mark.parametrize("message", [
        'openai HTTP 429: {"error": {"type": "rate_limit_exceeded"}}',
        'anthropic HTTP 429: {"type": "error", "error": {"type": "rate_limit_error"}}',
        'google HTTP 429 (rate limited): {"error": {"code": 429}}',
    ], ids=["openai", "anthropic", "google"])
    def test_every_providers_rate_limit_is_recognised(self, message):
        assert _rate_limited(ProviderError(message))

    def test_an_exhausted_daily_quota_is_not_one(self):
        """Built by the real message function. Waiting inside a run does not
        refill a quota that resets tomorrow."""

        class QuotaResponse:
            status_code = 429
            text = "{}"

            def json(self):
                return {"error": {"code": 429, "details": [{
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [{
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        "quotaValue": "20",
                    }],
                }]}}

        message = providers._google_quota_message(QuotaResponse(), BY_KEY["gemini_flash"])
        assert "DAILY QUOTA" in message
        assert not _rate_limited(ProviderError(message))

    def test_an_account_out_of_credit_is_not_one(self):
        message = ('openai HTTP 429: {"error": {"message": "You exceeded your current '
                   'quota, please check your plan and billing details.", '
                   '"type": "insufficient_quota", "code": "insufficient_quota"}}')
        assert not _rate_limited(ProviderError(message))

    @pytest.mark.parametrize("exc", [
        ProviderError("openrouter HTTP 500: upstream exploded"),
        ProviderError('openrouter HTTP 400: {"error":{"message":"model: '
                      'qwen/qwen-2.5-72b-instruct does not support endpoint: '
                      'completions","provider_name":"Novita"}}'),
        ProviderError('openrouter HTTP 400: {"note": "an upstream HTTP 429 quoted in a body"}'),
        ProviderError("OPENROUTER_API_KEY not set"),
        httpx.ConnectTimeout("timed out"),
        RuntimeError("openrouter HTTP 429: the right words on the wrong type"),
    ], ids=["500", "novita-400", "429-quoted-inside-a-400", "no-key", "timeout",
            "wrong-type"])
    def test_nothing_else_is_mistaken_for_one(self, exc):
        assert not _rate_limited(exc)


class TestTheCallWaitsItOut:
    def test_a_row_that_would_have_been_lost_now_lands(self, asking, slept):
        obs, provider = asking([limited(), limited(), limited()], RateLimitAllowance())
        assert obs.forecast == 0.62
        assert not obs.error
        assert obs.upstream_provider == "DeepInfra"
        assert slept == [15.0, 30.0, 60.0]
        assert provider.calls == 4

    def test_the_schedule_runs_out_before_the_old_retries_resume(self, asking, slept):
        obs, provider = asking([limited()] * 20, RateLimitAllowance())
        assert slept == [*RATE_LIMIT_WAITS_S, 2.0, 4.0]
        assert provider.calls == len(RATE_LIMIT_WAITS_S) + 3
        assert obs.forecast is None
        assert obs.error.startswith(
            f"failed after {provider.calls} attempts, "
            f"{len(RATE_LIMIT_WAITS_S)} of them after waiting out a rate limit: ")
        assert "HTTP 429" in obs.error, "the row must still say why it failed"

    def test_a_wait_does_not_use_up_a_retry(self, asking, slept):
        server_error = ProviderError("openrouter HTTP 500: x")
        obs, _ = asking([limited(), server_error, limited(), server_error],
                        RateLimitAllowance())
        assert obs.forecast == 0.62
        assert slept == [15.0, 2.0, 30.0, 4.0]

    def test_an_ordinary_failure_is_retried_exactly_as_before(self, asking, slept):
        allowance = RateLimitAllowance()
        obs, provider = asking([ProviderError("openrouter HTTP 500: x")] * 5, allowance)
        assert slept == [2.0, 4.0]
        assert provider.calls == 3
        assert obs.error.startswith("failed after 3 attempts: ")
        assert allowance.summary()["waits"] == 0

    def test_an_exhausted_quota_takes_the_ordinary_path(self, asking, slept):
        quota = ProviderError('openai HTTP 429: {"error": {"type": "insufficient_quota"}}')
        allowance = RateLimitAllowance()
        asking([quota] * 5, allowance)
        assert slept == [2.0, 4.0]
        assert allowance.summary()["waited_s"] == 0

    def test_a_caller_without_an_allowance_sees_no_change(self, asking, slept):
        """`neff.verify`, and every other caller outside the daily run."""
        obs, provider = asking([limited()] * 5, None)
        assert slept == [2.0, 4.0]
        assert provider.calls == 3
        assert obs.error.startswith("failed after 3 attempts: ")


class TestWaitingCannotCostTheDay:
    def test_the_allowance_is_never_exceeded(self, asking, slept):
        allowance = RateLimitAllowance(40.0)
        asking([limited()] * 20, allowance)
        assert slept == [15.0, 25.0, 2.0, 4.0]
        assert allowance.summary() == {
            "waits": 2, "waited_s": 40.0, "allowance_s": 40.0, "refused": 3,
        }

    def test_one_allowance_is_shared_by_every_call_in_the_run(self, asking, slept):
        allowance = RateLimitAllowance(50.0)
        asking([limited()] * 20, allowance)
        asking([limited()] * 20, allowance)
        assert slept == [15.0, 30.0, 5.0, 2.0, 4.0, 2.0, 4.0]
        assert allowance.summary()["waited_s"] == 50.0

    def test_concurrent_threads_can_never_overdraw_it(self):
        allowance = RateLimitAllowance(100.0)
        granted = []
        lock = threading.Lock()
        start = threading.Barrier(32)

        def worker():
            start.wait()
            got = allowance.take(10.0)
            with lock:
                granted.append(got)

        threads = [threading.Thread(target=worker) for _ in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sum(granted) == 100.0
        assert allowance.summary() == {
            "waits": 10, "waited_s": 100.0, "allowance_s": 100.0, "refused": 22,
        }

    def test_the_allowance_fits_inside_the_job_that_spends_it(self):
        """The job is killed at `timeout-minutes` and commits nothing until
        collection ends, so an allowance that could approach that limit trades
        one model's rows for every model's. Held to a third of the job, leaving
        room for install, the test gate and an ordinary four-minute collection."""
        workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text()
        minutes = int(re.search(r"timeout-minutes:\s*(\d+)", workflow).group(1))
        assert RATE_LIMIT_ALLOWANCE_S <= minutes * 60 / 3

    def test_one_call_cannot_spend_the_whole_run(self):
        assert sum(RATE_LIMIT_WAITS_S) < RATE_LIMIT_ALLOWANCE_S

    def test_the_schedule_outlasts_the_longest_streak_on_record(self):
        """On 2026-09-09 eighteen consecutive qwen calls failed between
        17:09:20 and 17:10:53 UTC: 93 seconds."""
        assert sum(RATE_LIMIT_WAITS_S) > 93


class TestTheDailyRunUsesIt:
    """End to end through the runner that collects the study."""

    ANSWER = {
        "model": "qwen/qwen-2.5-72b-instruct",
        "provider": "DeepInfra",
        "choices": [{"message": {"content": CONTENT}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    @pytest.fixture
    def run(self, tmp_path, monkeypatch, slept):
        close = datetime.now(timezone.utc) + timedelta(days=30)
        tasks = [Task(task_id="t0", kind="event", prompt="Will X?",
                      resolves_after=close.isoformat(), source="kalshi",
                      source_ref="TICKER-0", outcome_kind="binary",
                      state={"asked_on": "2026-09-09"})]
        monkeypatch.setattr(collect, "TASKS_PATH", tmp_path / "tasks.jsonl")
        monkeypatch.setattr(collect, "OBS_PATH", tmp_path / "observations.jsonl")
        monkeypatch.setattr(collect, "LEDGER_PATH", tmp_path / "ledger.jsonl")
        monkeypatch.setattr(collect, "build_daily_tasks", lambda **kw: tasks)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setitem(PROVIDERS, "openrouter", OpenRouterProvider())
        throttled_body = RECORDED_429.split(": ", 1)[1]

        def go(throttled_calls):
            box = {"n": 0}

            def fake_post(url, headers=None, json=None, timeout=None):
                box["n"] += 1
                if box["n"] <= throttled_calls:
                    return Response(429, throttled_body)
                return Response(200, self.ANSWER)

            monkeypatch.setattr("neff.providers.httpx.post", fake_post)
            summary = collect.run_day(
                config=config.RunConfig(arm="pilot", tasks_per_day=1,
                                        model_keys=["qwen"], replicates_per_day=0),
                as_of=date(2026, 9, 9),
            )
            return summary, JsonlStore(tmp_path / "observations.jsonl").read_all()

        return go

    def test_a_throttled_call_still_reaches_the_record(self, run, slept):
        summary, rows = run(throttled_calls=2)
        assert [r["forecast"] for r in rows] == [0.62]
        assert slept == [15.0, 30.0]
        assert summary["rate_limit_waits"]["waits"] == 2
        assert summary["rate_limit_waits"]["waited_s"] == 45.0

    def test_the_log_says_how_long_it_waited(self, run, capsys):
        run(throttled_calls=1)
        assert "rate limits: 1 wait(s), 15s of the 900s allowance" in capsys.readouterr().out

    def test_a_healthy_day_reports_no_waits_and_no_warning(self, run, capsys):
        summary, _ = run(throttled_calls=0)
        out = capsys.readouterr().out
        assert summary["rate_limit_waits"]["waits"] == 0
        assert "rate limits:" not in out
        assert "ALLOWANCE" not in out

    def test_a_spent_allowance_is_named_and_the_day_still_closes(
        self, run, capsys, monkeypatch
    ):
        monkeypatch.setattr(collect, "RATE_LIMIT_ALLOWANCE_S", 20.0)
        summary, rows = run(throttled_calls=10_000)
        out = capsys.readouterr().out
        assert "!! RATE-LIMIT ALLOWANCE SPENT" in out
        assert summary["observations"] == 1
        assert rows[0]["forecast"] is None
        assert "HTTP 429" in rows[0]["error"]

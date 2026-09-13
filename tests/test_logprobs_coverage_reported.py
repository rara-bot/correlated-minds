"""A registered sensitivity was losing most of one model's rows, and nothing said so.

Deviation 10 made logprobs requested and stored for the models §5.4(a) names.
On the four days that followed, `deepseek` carried them on 26 of 108 rows. Every
row served by DigitalOcean or Google had them. Every row served by AtlasCloud or
StreamLake had none, although OpenRouter's own catalogue lists both as supporting
the parameter, which is why `require_parameters` does not filter them out.
Probed live on 2026-09-13 with one call pinned to each host: HTTP 200, a
complete answer, and `logprobs: null`. `llama` loses its rows from Cloudflare
the same way.

A row like that is otherwise perfect -- no error, no failed call -- so nothing in
the run pointed at the loss. The run cannot recover what a host never sends, but
it can stop being silent: per model, how many answered calls carried logprobs,
and which hosts answered without them.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from neff import collect, config
from neff.providers import PROVIDERS, OpenRouterProvider
from neff.store import JsonlStore, Observation, Task

BY_KEY = {m.key: m for m in config.PANEL}
MODELS = list(config.PANEL)

DIGITS = [{"token": "62", "logprob": -0.1,
           "top_logprobs": [{"token": "62", "logprob": -0.1},
                            {"token": "63", "logprob": -2.3}]}]


def row(model_key, host=None, logprobs=None, provider="openrouter", answered=True):
    o = Observation(
        obs_id="o", task_id="t", model_key=model_key,
        model_id_returned=BY_KEY[model_key].model_id if answered else "",
        provider=provider, prompt_variant=0,
        forecast=0.6 if answered else None,
        direction="yes" if answered else None,
        confidence=0.5 if answered else None,
    )
    o.upstream_provider = host
    o.logprobs = logprobs
    return o


class Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class TestTheCoverageIsCountedFromTheRows:
    def test_the_recorded_day_is_attributed_to_its_hosts(self):
        """deepseek on 2026-09-12, as collected."""
        rows = ([row("deepseek", "AtlasCloud")] * 12
                + [row("deepseek", "StreamLake")] * 13
                + [row("deepseek", "Google", DIGITS)] * 2)
        assert collect.logprobs_coverage(rows, MODELS) == {
            "deepseek": {"answered": 27, "carried": 2,
                         "hosts_without": {"AtlasCloud": 12, "StreamLake": 13}},
        }

    def test_a_direct_vendor_api_is_named_by_its_provider(self):
        rows = [row("gpt_mid", None, None, provider="openai")]
        assert collect.logprobs_coverage(rows, MODELS)["gpt_mid"]["hosts_without"] == {
            "openai": 1,
        }

    def test_a_model_outside_the_leg_is_not_reported(self):
        """qwen is excluded from 5.4(a) and is never asked."""
        assert collect.logprobs_coverage([row("qwen", "DeepInfra")], MODELS) == {}

    def test_a_call_that_never_came_back_is_not_blamed_on_a_host(self):
        failed = row("deepseek", answered=False)
        failed.error = "failed after 3 attempts: ProviderError: openrouter HTTP 429: x"
        assert collect.logprobs_coverage([failed], MODELS) == {}

    def test_mock_rows_are_left_out(self):
        rows = [row("gpt_mid", None, None, provider="mock")]
        assert collect.logprobs_coverage(rows, MODELS) == {}

    def test_only_the_models_in_this_run_are_considered(self):
        """A run restricted with --models reports on those models alone."""
        rows = [row("deepseek", "AtlasCloud")]
        assert collect.logprobs_coverage(rows, [BY_KEY["gpt_mid"]]) == {}


class TestTheDailyRunSaysSo:
    """End to end through the runner. Two questions to deepseek, each answered
    by a host chosen by the test."""

    @staticmethod
    def payload(host, sends_logprobs):
        choice = {
            "message": {"content": '{"probability": 0.62, "direction": "yes", '
                                   '"confidence": 0.7, "rationale": "r"}'},
            # What AtlasCloud, StreamLake and Cloudflare sent when probed: the
            # key is present and null.
            "logprobs": {"content": DIGITS} if sends_logprobs else None,
        }
        return {"model": "deepseek/deepseek-v3.2", "provider": host,
                "choices": [choice],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    @pytest.fixture
    def run(self, tmp_path, monkeypatch):
        close = datetime.now(timezone.utc) + timedelta(days=30)
        tasks = [Task(task_id=f"t{i}", kind="event", prompt=f"Will {name}?",
                      resolves_after=close.isoformat(), source="kalshi",
                      source_ref=f"TICKER-{i}", outcome_kind="binary",
                      state={"asked_on": "2026-09-09"})
                 for i, name in enumerate(["A", "B"])]
        monkeypatch.setattr(collect, "TASKS_PATH", tmp_path / "tasks.jsonl")
        monkeypatch.setattr(collect, "OBS_PATH", tmp_path / "observations.jsonl")
        monkeypatch.setattr(collect, "LEDGER_PATH", tmp_path / "ledger.jsonl")
        monkeypatch.setattr(collect, "build_daily_tasks", lambda **kw: tasks)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setitem(PROVIDERS, "openrouter", OpenRouterProvider())

        def go(hosts, use_mock=False):
            """`hosts` maps each question to (host, sends_logprobs)."""
            def fake_post(url, headers=None, json=None, timeout=None):
                host, sends = hosts[json["messages"][0]["content"]]
                return Response(self.payload(host, sends))

            monkeypatch.setattr("neff.providers.httpx.post", fake_post)
            return collect.run_day(
                config=config.RunConfig(arm="pilot", tasks_per_day=2,
                                        model_keys=["deepseek"], replicates_per_day=0),
                as_of=date(2026, 9, 9), use_mock=use_mock,
            )

        return go

    def test_a_host_that_sends_none_is_named(self, run, capsys):
        summary = run({"Will A?": ("AtlasCloud", False),
                       "Will B?": ("DigitalOcean", True)})
        out = capsys.readouterr().out
        assert summary["logprobs"] == {
            "deepseek": {"answered": 2, "carried": 1,
                         "hosts_without": {"AtlasCloud": 1}},
        }
        assert "logprobs carried: deepseek 1/2" in out
        assert "!! LOGPROBS MISSING on 1 answered call(s) -- deepseek: AtlasCloud x1" in out

    def test_a_day_where_every_call_carries_them_does_not_cry_wolf(self, run, capsys):
        run({"Will A?": ("DigitalOcean", True), "Will B?": ("Google", True)})
        out = capsys.readouterr().out
        assert "logprobs carried: deepseek 2/2" in out
        assert "LOGPROBS MISSING" not in out

    def test_a_mock_run_is_not_accused(self, run, capsys):
        run({}, use_mock=True)
        assert "LOGPROBS MISSING" not in capsys.readouterr().out

    def test_the_stored_rows_agree_with_the_report(self, run, tmp_path):
        run({"Will A?": ("StreamLake", False), "Will B?": ("DigitalOcean", True)})
        rows = JsonlStore(tmp_path / "observations.jsonl").read_all()
        by_host = {r["upstream_provider"]: r["logprobs"] for r in rows}
        assert by_host["StreamLake"] is None
        assert by_host["DigitalOcean"][0]["t"] == "62"

    def test_the_report_can_never_stop_the_day(self, run, capsys, monkeypatch):
        """It warns and returns. A day halted by a reporting fault can never be
        collected again."""
        def broken(*args, **kwargs):
            raise RuntimeError("report exploded")

        monkeypatch.setattr(collect, "logprobs_coverage", broken)
        summary = run({"Will A?": ("AtlasCloud", False),
                       "Will B?": ("DigitalOcean", True)})
        assert summary["observations"] == 2
        assert summary["usable"] == 2
        assert "logprobs report failed" in capsys.readouterr().out

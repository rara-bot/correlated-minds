"""Three panel members are served by a machine we were not writing down.

PREREGISTRATION.md §10, limitation 4 commits to logging what was actually served:
"Providers may update models mid-panel. We log the served id every call and
report drift; we cannot prevent it." For `qwen`, `llama` and `deepseek` the
served id does not discharge that promise. OpenRouter is an aggregator; it
picks an UPSTREAM HOST per request, every host returns the same
`qwen/qwen-2.5-72b-instruct`, and hosts serve different quantisations of the
same open weights. Probed 2026-09-09: qwen→DeepInfra, llama→Parasail,
deepseek→Venice, and those assignments move between requests.

In a study whose estimand is agreement BETWEEN models, the serving stack is an
uncontrolled variable, and until this field it was invisible. It is not a
hypothetical one: routing to Novita is what cost every qwen observation on
2026-09-01 and 2026-09-07 (deviation 4), and that was diagnosed only because
the 400 body happened to name `provider_name`. A quantisation change degrades
answers without erroring, so it leaves no such body to read.

These tests hold three things: the host is read from the response, it reaches
the stored row -- including the rows that FAILED, which are the ones anyone
debugging will reach for -- and it never appears where it would be a fiction.
"""

import json
from datetime import date

import pytest

from neff import collect, config
from neff.ledger import Ledger
from neff.providers import (
    PROVIDERS,
    AnthropicProvider,
    GoogleProvider,
    MockProvider,
    OpenAICompatProvider,
    OpenRouterProvider,
    ask,
)
from neff.store import JsonlStore, Observation

BY_KEY = {m.key: m for m in config.PANEL}
OPENROUTER_MODELS = [m for m in config.PANEL if m.provider == "openrouter"]

# What OpenRouter actually returned when probed on 2026-09-09, trimmed to the
# keys this code reads. The `provider` field is top level, a bare host name, and
# a sibling of `model` rather than nested inside it.
PROBED = {
    "model": "qwen/qwen-2.5-72b-instruct",
    "provider": "DeepInfra",
    "choices": [{"message": {"content": '{"probability": 0.5, "direction": "no",'
                                        ' "confidence": 0.5, "rationale": "x"}'}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


@pytest.fixture
def responds(monkeypatch):
    """Serve a chosen payload to whatever provider is called, and keep the body."""
    box = {"payload": PROBED}

    def fake_post(url, headers=None, json=None, timeout=None):
        box["url"] = url
        box["sent"] = json
        return FakeResponse(box["payload"])

    monkeypatch.setattr("neff.providers.httpx.post", fake_post)
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                "GOOGLE_API_KEY"):
        monkeypatch.setenv(key, "test-key")
    return box


class TestTheHostIsReadFromTheResponse:
    def test_openrouter_records_the_host_it_routed_to(self, responds):
        done = OpenRouterProvider().complete(BY_KEY["qwen"], "q", 400, 10.0)
        assert done.upstream_provider == "DeepInfra"

    @pytest.mark.parametrize("spec", OPENROUTER_MODELS, ids=lambda s: s.key)
    def test_every_aggregated_panel_member_is_covered(self, responds, spec):
        """Three of the ten route through the aggregator, so this belongs to the
        provider rather than to qwen."""
        assert OpenRouterProvider().complete(spec, "q", 400, 10.0).upstream_provider

    def test_the_rest_of_the_completion_is_unchanged(self, responds):
        """Widening the result must not disturb what was already carried: a
        mis-read token count bills the study's budget wrongly."""
        done = OpenRouterProvider().complete(BY_KEY["qwen"], "q", 400, 10.0)
        assert done.model_id == "qwen/qwen-2.5-72b-instruct"
        assert done.input_tokens == 10
        assert done.output_tokens == 5
        assert '"probability": 0.5' in done.text

    def test_the_registered_request_shape_is_untouched(self, responds):
        """Instrumentation, not design. Nothing that reaches the model moves."""
        spec = BY_KEY["qwen"]
        OpenRouterProvider().complete(spec, "the prompt", 400, 10.0)
        body = responds["sent"]
        assert body["model"] == spec.model_id
        assert body["temperature"] == config.TEMPERATURE
        assert body["messages"] == [{"role": "user", "content": "the prompt"}]
        assert body["max_tokens"] == 400


class TestAWrongHostIsWorseThanNoHost:
    """A gap in the log is a gap. A confounder recorded as though it were
    controlled is a false record, so every doubtful value reads as unstated."""

    def test_a_response_naming_no_host_leaves_it_unset(self, responds):
        responds["payload"] = {k: v for k, v in PROBED.items() if k != "provider"}
        assert OpenRouterProvider().complete(
            BY_KEY["qwen"], "q", 400, 10.0).upstream_provider is None

    def test_our_own_routing_preference_is_not_mistaken_for_a_host(self, responds):
        """`provider` is also the key we SEND the routing filter under
        (`OpenRouterProvider.EXTRA_BODY`). An echo of it is not a host name."""
        responds["payload"] = {**PROBED,
                               "provider": OpenRouterProvider.EXTRA_BODY["provider"]}
        assert OpenRouterProvider().complete(
            BY_KEY["qwen"], "q", 400, 10.0).upstream_provider is None

    def test_an_empty_name_is_unset_rather_than_empty_string(self, responds):
        responds["payload"] = {**PROBED, "provider": "   "}
        assert OpenRouterProvider().complete(
            BY_KEY["qwen"], "q", 400, 10.0).upstream_provider is None


class TestProvidersThatServeTheirOwnModelsLeaveItUnset:
    """There is no upstream to name when the API is the host. Filling this in
    for a direct vendor would invent a distinction the study does not have."""

    def test_openai(self, responds):
        assert OpenAICompatProvider().complete(
            BY_KEY["gpt_mid"], "q", 400, 10.0).upstream_provider is None

    def test_openai_is_unset_even_if_a_provider_key_appears(self, responds):
        """Read by an explicit per-provider opt-in, not by sniffing the body."""
        responds["payload"] = {**PROBED, "provider": "SomethingElse"}
        assert OpenAICompatProvider().complete(
            BY_KEY["gpt_mid"], "q", 400, 10.0).upstream_provider is None

    def test_anthropic(self, responds):
        responds["payload"] = {
            "model": "claude-sonnet-5", "provider": "Anthropic",
            "content": [{"type": "text", "text": "{}"}],
            "usage": {"input_tokens": 3, "output_tokens": 4},
        }
        assert AnthropicProvider().complete(
            BY_KEY["claude_sonnet"], "q", 400, 10.0).upstream_provider is None

    def test_google(self, responds):
        responds["payload"] = {
            "modelVersion": "gemini-3.5-flash",
            "candidates": [{"content": {"parts": [{"text": "{}"}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4},
        }
        spec = next(m for m in config.PANEL if m.provider == "google")
        assert GoogleProvider().complete(spec, "q", 400, 10.0).upstream_provider is None

    def test_mock(self):
        assert MockProvider().complete(
            BY_KEY["qwen"], "q", 400, 10.0).upstream_provider is None


# --------------------------------------------------------------------------
# Reaching the record is the whole point. A value read and dropped is nothing.
# --------------------------------------------------------------------------
@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "ledger.jsonl", cap_usd=100.0,
                  arm_caps=dict(config.ARM_CAPS_USD))


@pytest.fixture
def qwen():
    return BY_KEY["qwen"]


def _ask_qwen(monkeypatch, ledger, qwen, payload):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(payload)

    monkeypatch.setattr("neff.providers.httpx.post", fake_post)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setitem(PROVIDERS, "openrouter", OpenRouterProvider())
    return ask(spec=qwen, task_id="t1", prompt="Q?", ledger=ledger,
               arm=config.PRE_REGISTRATION_ARM, max_tokens=400)


class TestItReachesTheStoredObservation:
    def test_the_observation_carries_the_host(self, monkeypatch, ledger, qwen):
        obs = _ask_qwen(monkeypatch, ledger, qwen, PROBED)
        assert obs.forecast == 0.5
        assert obs.upstream_provider == "DeepInfra"

    def test_it_survives_the_round_trip_through_the_jsonl(
        self, monkeypatch, ledger, qwen, tmp_path
    ):
        """The file is the record. A field held only in memory is not logged."""
        obs = _ask_qwen(monkeypatch, ledger, qwen, PROBED)
        store = JsonlStore(tmp_path / "observations.jsonl")
        store.append(obs)
        assert store.read_all()[0]["upstream_provider"] == "DeepInfra"

    def test_a_failed_observation_still_names_its_host(
        self, monkeypatch, ledger, qwen
    ):
        """THE CASE THIS EXISTS FOR. An unusable row is the one whose serving
        stack someone will go looking for, so the attribution cannot be written
        only on the successes."""
        broken = {**PROBED, "provider": "Novita",
                  "choices": [{"message": {"content": "I cannot answer that."}}]}
        obs = _ask_qwen(monkeypatch, ledger, qwen, broken)
        assert obs.forecast is None
        assert obs.error
        assert obs.upstream_provider == "Novita"

    def test_a_call_that_never_returned_names_no_host(
        self, monkeypatch, ledger, qwen
    ):
        """An HTTP 400 has no host to read -- claiming one would be invention."""
        def fake_post(url, headers=None, json=None, timeout=None):
            return FakeResponse({"error": "nope"}, status_code=400)

        monkeypatch.setattr("neff.providers.httpx.post", fake_post)
        monkeypatch.setattr("neff.providers.time.sleep", lambda s: None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setitem(PROVIDERS, "openrouter", OpenRouterProvider())
        obs = ask(spec=qwen, task_id="t1", prompt="Q?", ledger=ledger,
                  arm=config.PRE_REGISTRATION_ARM, max_tokens=400)
        assert obs.error
        assert obs.upstream_provider is None

    def test_an_unrouted_provider_writes_no_host(self, monkeypatch, ledger):
        obs = ask(spec=BY_KEY["gpt_mid"], task_id="t1", prompt="Q?", ledger=ledger,
                  arm=config.PRE_REGISTRATION_ARM, use_mock=True)
        assert obs.forecast is not None
        assert obs.upstream_provider is None


class TestTheDailyRunRecordsAndReportsIt:
    """End to end through the runner that actually collects the study."""

    @pytest.fixture
    def sandbox(self, tmp_path, monkeypatch):
        from datetime import datetime, timedelta, timezone

        from neff.store import Task

        close = datetime.now(timezone.utc) + timedelta(days=30)
        tasks = [
            Task(task_id=f"t{i}", kind="event", prompt="Will X happen?",
                 resolves_after=close.isoformat(), source="kalshi",
                 source_ref=f"TICKER-{i}", outcome_kind="binary",
                 state={"asked_on": "2026-09-09"})
            for i in range(2)
        ]
        obs = tmp_path / "observations.jsonl"
        monkeypatch.setattr(collect, "TASKS_PATH", tmp_path / "tasks.jsonl")
        monkeypatch.setattr(collect, "OBS_PATH", obs)
        monkeypatch.setattr(collect, "LEDGER_PATH", tmp_path / "ledger.jsonl")
        monkeypatch.setattr(collect, "build_daily_tasks", lambda **kw: tasks)

        def fake_post(url, headers=None, json=None, timeout=None):
            return FakeResponse(PROBED)

        monkeypatch.setattr("neff.providers.httpx.post", fake_post)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setitem(PROVIDERS, "openrouter", OpenRouterProvider())
        return obs

    def _run(self):
        return collect.run_day(
            config=config.RunConfig(arm="pilot", tasks_per_day=2,
                                    model_keys=["qwen"], replicates_per_day=0),
            as_of=date(2026, 9, 9),
        )

    def test_every_collected_row_names_the_host_that_served_it(self, sandbox):
        self._run()
        rows = JsonlStore(sandbox).read_all()
        assert rows, "the run collected nothing"
        assert all(r["upstream_provider"] == "DeepInfra" for r in rows)

    def test_the_day_summary_reports_the_hosts_it_ran_on(self, sandbox):
        """The served id is identical whichever host answers, so the drift line
        beside this one cannot see a day that moved to a different stack."""
        assert self._run()["routing"] == ["qwen -> DeepInfra"]


class TestThePreFlightReceiptCarriesItToo:
    """`neff.verify` writes the dated proof that each pinned id answered a live
    API. Its own docstring calls that receipt the start of the drift series --
    "begins at this file rather than on the first collection day" -- so a
    receipt recording less than a daily row would open the series with a gap."""

    @pytest.fixture
    def receipts(self, tmp_path, monkeypatch):
        from neff import verify

        path = tmp_path / "verification.jsonl"
        monkeypatch.setattr(verify, "VERIFICATION_PATH", path)
        monkeypatch.setattr(verify, "LEDGER_PATH", tmp_path / "ledger.jsonl")
        monkeypatch.setattr(verify, "enabled_panel", lambda: [BY_KEY["qwen"]])

        def fake_post(url, headers=None, json=None, timeout=None):
            return FakeResponse(PROBED)

        monkeypatch.setattr("neff.providers.httpx.post", fake_post)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setitem(PROVIDERS, "openrouter", OpenRouterProvider())
        return verify, path

    def test_the_receipt_names_the_host(self, receipts):
        verify, path = receipts
        verify.check_live_models()
        row = json.loads(path.read_text().splitlines()[0])
        assert row["model_id_returned"] == "qwen/qwen-2.5-72b-instruct"
        assert row["upstream_provider"] == "DeepInfra"

    def test_the_operator_can_see_it_without_reading_the_file(self, receipts):
        """The qwen→DeepInfra probe quoted in deviations 4 and 7 was read off an
        ad-hoc script. It should come from the command that already exists."""
        verify, _ = receipts
        assert "DeepInfra" in dict(
            (name, detail) for _s, name, detail in verify.check_live_models()
        )["qwen"]

    def test_readiness_still_reads_a_receipt_that_predates_the_field(
        self, tmp_path, monkeypatch
    ):
        """`data/verification.jsonl` is append-only too: the receipts written
        before the freeze carry no such key and must still count as verified."""
        from neff import verify

        path = tmp_path / "verification.jsonl"
        monkeypatch.setattr(verify, "VERIFICATION_PATH", path)
        path.write_text(json.dumps({
            "model_key": "qwen", "ok": True, "checked_at": "2026-08-21T01:00:00+00:00",
            "model_id_returned": "qwen/qwen-2.5-72b-instruct",
        }) + "\n")
        got = verify.verified_models()
        assert set(got) == {"qwen"}
        assert got["qwen"].get("upstream_provider") is None


class TestTheChangeIsAdditive:
    """New field on new rows. `data/observations.jsonl` is append-only and 2,390
    rows of it were written before this existed."""

    def test_the_default_is_absent_not_a_placeholder(self):
        """`""` or `"unknown"` would be indistinguishable in analysis from a
        host that genuinely reported itself under that name."""
        assert Observation.upstream_provider is None
        obs = Observation("o", "t", "m", "id", "anthropic", 0, 0.5, "yes", 0.5)
        assert obs.upstream_provider is None

    def test_every_committed_row_still_loads_under_the_new_schema(self):
        """No field was renamed or removed, so every historical row can still be
        read back into an Observation -- including the ones that predate this."""
        rows = JsonlStore(config.OBS_PATH).read_all()
        assert len(rows) > 2000, "the committed record did not load"
        for row in rows:
            Observation(**row)

    def test_rows_written_before_this_field_read_back_as_unstated(self):
        legacy = {k: v for k, v in JsonlStore(config.OBS_PATH).read_all()[0].items()}
        assert "upstream_provider" not in legacy, (
            "the earliest committed row was rewritten -- the record is append-only"
        )
        assert Observation(**legacy).upstream_provider is None

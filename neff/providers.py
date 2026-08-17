"""Multi-provider LLM client for the panel.

Everything here exists to make seven different APIs produce ONE comparable
observation. Design requirements, each driven by a way the study could otherwise
be corrupted:

  - PINNED MODEL IDS, and we log whatever id the API actually served. Providers
    silently upgrade models behind aliases; a swap mid-panel would corrupt a
    longitudinal correlation study in a way that is nearly undetectable after
    the fact.

  - STRUCTURED OUTPUT. We correlate decisions, not prose. A rigid JSON schema
    removes extraction error and stops free-text length differences across
    families from leaking into the measurement.

  - PRE-FLIGHT COSTING. Every call is priced and checked against the ledger
    BEFORE it is issued, so a retry loop cannot drain the budget overnight.

  - NO SILENT FAILURES. A refusal, a timeout, or a malformed response is recorded
    as an Observation with `error` set, never dropped. A dropped call is a hole
    in the panel that looks identical to "the model had nothing to say", and
    those holes would cluster on exactly the busy market days our hypothesis is
    about.

  - IDENTICAL SAMPLING. temperature=0 everywhere. Prompt-variant diversity for
    H3 is manipulated explicitly; it must never leak in through sampling noise.
"""

import json
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

import httpx

from .config import MAX_OUTPUT_TOKENS, TEMPERATURE, ModelSpec
from .ledger import BudgetExceeded, Ledger
from .store import Observation, observation_id

# The schema every model must fill. Kept deliberately small: four fields, no
# nesting. Larger schemas produce more parse failures, and a parse failure is a
# missing observation.
RESPONSE_INSTRUCTIONS = """\
You are producing a calibrated forecast for a research study.

Respond with ONLY a JSON object, no prose before or after, in exactly this form:

{"probability": <number between 0 and 1>,
 "direction": "<yes|no>",
 "confidence": <number between 0 and 1>,
 "rationale": "<one sentence, at most 25 words>"}

- "probability" is your probability that the stated outcome occurs.
- "direction" is "yes" if probability > 0.5, otherwise "no".
- "confidence" is how sure you are of your own probability estimate.
- Do not hedge by answering 0.5 unless you genuinely have no information.
"""


class ProviderError(RuntimeError):
    """Non-retryable provider failure."""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of a response.

    Models wrap JSON in markdown fences, add a preamble, or append a note,
    despite instructions. Being tolerant here converts would-be missing
    observations into usable ones, which directly protects statistical power.
    """
    if not text:
        return None

    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fall back to the first balanced {...} block.
    start = candidate.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(candidate)):
            if candidate[i] == "{":
                depth += 1
            elif candidate[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(candidate[start : i + 1])
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        break
        start = candidate.find("{", start + 1)
    return None


def _coerce_probability(value: Any) -> Optional[float]:
    """Accept 0.72, '0.72', '72%', or 72 and return 0.72."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().rstrip("%")
        try:
            number = float(text)
        except ValueError:
            return None
        if "%" in str(value):
            number /= 100.0
    # A bare "72" almost certainly means 72%.
    if number > 1.0:
        number = number / 100.0 if number <= 100.0 else 1.0
    return max(0.0, min(1.0, number))


class Provider(ABC):
    """One vendor's API."""

    name = "base"

    @abstractmethod
    def complete(
        self, spec: ModelSpec, prompt: str, max_tokens: int, timeout: float
    ) -> Tuple[str, str, int, int]:
        """Return (text, model_id_returned, input_tokens, output_tokens)."""

    @staticmethod
    def _key(*names: str) -> Optional[str]:
        for name in names:
            value = os.environ.get(name)
            if value:
                return value.strip()
        return None


class AnthropicProvider(Provider):
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def complete(self, spec, prompt, max_tokens, timeout):
        key = self._key("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("ANTHROPIC_API_KEY not set")

        response = httpx.post(
            self.URL,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": spec.model_id,
                "max_tokens": max_tokens,
                "temperature": TEMPERATURE,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
        if response.status_code != 200:
            raise ProviderError(f"anthropic HTTP {response.status_code}: {response.text[:300]}")

        payload = response.json()
        text = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        )
        usage = payload.get("usage", {})
        return (
            text,
            payload.get("model", spec.model_id),
            int(usage.get("input_tokens", 0)),
            int(usage.get("output_tokens", 0)),
        )


class OpenAICompatProvider(Provider):
    """OpenAI's chat-completions shape.

    Also serves OpenRouter and most open-weight hosts, which deliberately mirror
    this API. One implementation therefore covers four of our seven families.
    """

    name = "openai"
    URL = "https://api.openai.com/v1/chat/completions"
    KEY_NAMES = ("OPENAI_API_KEY",)

    def complete(self, spec, prompt, max_tokens, timeout):
        key = self._key(*self.KEY_NAMES)
        if not key:
            raise ProviderError(f"{self.KEY_NAMES[0]} not set")

        response = httpx.post(
            self.URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": spec.model_id,
                "max_tokens": max_tokens,
                "temperature": TEMPERATURE,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
        if response.status_code != 200:
            raise ProviderError(f"{self.name} HTTP {response.status_code}: {response.text[:300]}")

        payload = response.json()
        choices = payload.get("choices") or []
        text = choices[0].get("message", {}).get("content", "") if choices else ""
        usage = payload.get("usage", {})
        return (
            text,
            payload.get("model", spec.model_id),
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"
    URL = "https://openrouter.ai/api/v1/chat/completions"
    KEY_NAMES = ("OPENROUTER_API_KEY",)


class GoogleProvider(Provider):
    name = "google"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def complete(self, spec, prompt, max_tokens, timeout):
        key = self._key("GOOGLE_API_KEY", "GEMINI_API_KEY")
        if not key:
            raise ProviderError("GOOGLE_API_KEY not set")

        response = httpx.post(
            self.URL.format(model=spec.model_id),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": TEMPERATURE,
                    "maxOutputTokens": max_tokens,
                },
            },
            timeout=timeout,
        )
        if response.status_code != 200:
            raise ProviderError(f"google HTTP {response.status_code}: {response.text[:300]}")

        payload = response.json()
        candidates = payload.get("candidates") or []
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(part.get("text", "") for part in parts)
        usage = payload.get("usageMetadata", {})
        return (
            text,
            payload.get("modelVersion", spec.model_id),
            int(usage.get("promptTokenCount", 0)),
            int(usage.get("candidatesTokenCount", 0)),
        )


class MockProvider(Provider):
    """Deterministic offline provider.

    Lets the entire pipeline -- task construction, calling, parsing, scoring,
    storage, cost accounting -- be tested end to end with zero spend and zero
    keys. Every model family gets its own reproducible bias so the resulting
    fake panel has realistic, non-degenerate correlation structure to test the
    estimator against.
    """

    name = "mock"

    def complete(self, spec, prompt, max_tokens, timeout):
        import hashlib

        seed = int(
            hashlib.sha256(f"{spec.key}|{prompt}".encode("utf-8")).hexdigest()[:8], 16
        )
        family_bias = (
            int(hashlib.sha256(spec.family.encode()).hexdigest()[:4], 16) % 100
        ) / 500.0
        probability = round(min(0.95, max(0.05, (seed % 1000) / 1000.0 * 0.7 + family_bias)), 3)

        text = json.dumps(
            {
                "probability": probability,
                "direction": "yes" if probability > 0.5 else "no",
                "confidence": round(0.4 + (seed % 50) / 100.0, 2),
                "rationale": f"mock response from {spec.key}",
            }
        )
        return text, f"{spec.model_id}-mock", len(prompt) // 4, 40


PROVIDERS: Dict[str, Provider] = {
    "anthropic": AnthropicProvider(),
    "openai": OpenAICompatProvider(),
    "openrouter": OpenRouterProvider(),
    "google": GoogleProvider(),
    "mock": MockProvider(),
}


def ask(
    spec: ModelSpec,
    task_id: str,
    prompt: str,
    ledger: Ledger,
    arm: str,
    prompt_variant: int = 0,
    max_tokens: int = MAX_OUTPUT_TOKENS,
    timeout: float = 90.0,
    use_mock: bool = False,
    max_retries: int = 2,
) -> Observation:
    """Ask one model one question and return an Observation.

    Never raises for provider trouble -- failures come back as an Observation
    with `error` populated. The panel must record that a model was asked and did
    not usefully answer; that is data, not an absence of data.
    """
    provider_name = "mock" if use_mock else spec.provider
    provider = PROVIDERS.get(provider_name)

    obs = Observation(
        obs_id=observation_id(task_id, spec.key, prompt_variant),
        task_id=task_id,
        model_key=spec.key,
        model_id_returned="",
        provider=provider_name,
        prompt_variant=prompt_variant,
        forecast=None,
        direction=None,
        confidence=None,
    )

    if provider is None:
        obs.error = f"unknown provider {provider_name!r}"
        return obs

    # Pre-flight cost check. Estimate high on output so we never discover the
    # breach after the money is spent.
    estimated = spec.price.estimate(
        input_tokens=len(prompt) // 4 + 200, output_tokens=max_tokens
    )
    try:
        ledger.check(estimated, arm=arm)
    except BudgetExceeded as exc:
        obs.error = f"budget: {exc}"
        return obs

    started = time.time()
    last_error = ""

    for attempt in range(max_retries + 1):
        try:
            text, model_id, input_tokens, output_tokens = provider.complete(
                spec, prompt, max_tokens, timeout
            )
        except (ProviderError, httpx.RequestError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries:
                time.sleep(2.0 * (attempt + 1))
            continue

        obs.model_id_returned = model_id
        obs.input_tokens = input_tokens
        obs.output_tokens = output_tokens
        obs.raw_response = text[:4000]
        obs.latency_ms = int((time.time() - started) * 1000)

        actual = spec.price.estimate(input_tokens, output_tokens)
        try:
            ledger.record(
                model=spec.key,
                arm=arm,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usd=actual,
            )
            obs.usd = actual
        except BudgetExceeded as exc:
            # The call already happened; record the observation but flag it.
            obs.error = f"budget breached on record: {exc}"

        parsed = _extract_json(text)
        if parsed is None:
            obs.error = (obs.error or "") + " | unparseable response"
            return obs

        obs.forecast = _coerce_probability(parsed.get("probability"))
        direction = parsed.get("direction")
        obs.direction = str(direction).strip().lower() if direction is not None else None
        obs.confidence = _coerce_probability(parsed.get("confidence"))
        obs.rationale = str(parsed.get("rationale", ""))[:500]

        if obs.forecast is None:
            obs.error = (obs.error or "") + " | missing probability"
        return obs

    obs.error = f"failed after {max_retries + 1} attempts: {last_error}"
    obs.latency_ms = int((time.time() - started) * 1000)
    return obs

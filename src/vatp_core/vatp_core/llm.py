"""LLM backends behind one tiny interface.

* ``AnthropicBackend`` — Claude via the official SDK, grammar-constrained JSON
  (``output_config.format``), refusal fallbacks enabled.
* ``MockBackend``      — deterministic, offline, keyless test double (see mock_planner.py).
  It exists so CI, unit tests and the benchmark harness run without network/cost and so
  the validator + repair loop can be exercised with *injected, reproducible defects*.
  It is not presented as an LLM result in any metric.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Prompt:
    system: str
    user: str
    # Structured side-channel for the offline mock only; real backends ignore it.
    ctx: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResult:
    data: dict[str, Any]
    latency_s: float
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    stop_reason: str = ""


class LLMError(RuntimeError):
    pass


class LLMBackend(Protocol):
    name: str

    def generate(self, prompt: Prompt, schema: dict[str, Any]) -> LLMResult: ...


class AnthropicBackend:
    """Claude backend. Credentials come from the environment (ANTHROPIC_API_KEY or an `ant auth` profile)."""

    def __init__(self, model: str | None = None, effort: str | None = None,
                 max_tokens: int = 8000, use_fallbacks: bool = True):
        import anthropic  # local import: the core library works without the SDK

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("VATP_MODEL", "claude-opus-5-5")
        self.effort = effort or os.environ.get("VATP_EFFORT", "low")
        self.max_tokens = max_tokens
        self.use_fallbacks = use_fallbacks
        self.name = f"anthropic:{self.model}"

    def generate(self, prompt: Prompt, schema: dict[str, Any]) -> LLMResult:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=prompt.system,
            messages=[{"role": "user", "content": prompt.user}],
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema", "schema": schema}},
        )
        t0 = time.perf_counter()
        try:
            if self.use_fallbacks:  # server-side refusal fallback (beta); no-op unless a refusal happens
                resp = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
            else:
                resp = self.client.messages.create(**kwargs)
        except self._anthropic.APIError as e:
            raise LLMError(f"Anthropic API error: {e}") from e
        dt = time.perf_counter() - t0
        if resp.stop_reason == "refusal":
            raise LLMError(f"model refused the request (stop_details={getattr(resp, 'stop_details', None)})")
        if resp.stop_reason == "max_tokens":
            raise LLMError("response truncated at max_tokens; raise max_tokens or simplify the task")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            raise LLMError("no text block in response")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON from model: {e}") from e
        return LLMResult(data, dt, resp.usage.input_tokens, resp.usage.output_tokens,
                         resp.model, resp.stop_reason)


_GEMINI_SCHEMA_KEYS = {"type", "properties", "required", "items", "enum", "description"}


def gemini_schema(schema: Any) -> Any:
    """Reduce a JSON Schema to the OpenAPI subset Gemini's `responseSchema` accepts
    (drops e.g. `additionalProperties`; validation of extra keys is done by our own validator)."""
    if isinstance(schema, dict):
        out: dict[str, Any] = {}
        for k, v in schema.items():
            if k not in _GEMINI_SCHEMA_KEYS:
                continue
            # property *names* are data (a property may be called "type"); only their schemas are rewritten
            out[k] = {n: gemini_schema(s) for n, s in v.items()} if k == "properties" else gemini_schema(v)
        return out
    if isinstance(schema, list):
        return [gemini_schema(v) for v in schema]
    return schema


class GeminiBackend:
    """Google Gemini through the public REST API (standard library only, no extra dependency).

    Uses JSON-mode with a response schema, temperature 0, and retries on rate limits / transient
    server errors. The API key is sent in a header and never appears in errors or logs."""

    DEFAULT_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, model: str | None = None, max_tokens: int = 8000, temperature: float = 0.0,
                 api_key: str | None = None, base_url: str | None = None, retries: int = 4,
                 timeout: float = 120.0, backoff_s: float = 2.0, effort: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise LLMError("no Gemini API key: set GEMINI_API_KEY")
        self.model = model or os.environ.get("VATP_GEMINI_MODEL", "gemini-2.5-flash")
        self.base_url = (base_url or os.environ.get("VATP_GEMINI_URL") or self.DEFAULT_URL).rstrip("/")
        self.max_tokens, self.temperature = max_tokens, temperature
        self.retries, self.timeout, self.backoff_s = retries, timeout, backoff_s
        self.name = f"gemini:{self.model}"

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        import urllib.error
        import urllib.request
        url = f"{self.base_url}/models/{self.model}:generateContent"
        data = json.dumps(body).encode()
        last = "unknown error"
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, data=data, method="POST", headers={
                "Content-Type": "application/json", "x-goog-api-key": self.api_key})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                try:
                    msg = json.loads(e.read().decode()).get("error", {}).get("message", "")
                except Exception:  # noqa: BLE001 - body may be empty or not JSON
                    msg = ""
                last = f"Gemini HTTP {e.code}: {msg[:300]}".rstrip(": ")
                if e.code not in (429, 500, 502, 503, 504):
                    raise LLMError(last) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = f"Gemini request failed: {getattr(e, 'reason', e)}"
            if attempt < self.retries:
                time.sleep(min(30.0, self.backoff_s * (2 ** attempt)))
        raise LLMError(f"{last} (gave up after {self.retries + 1} attempts)")

    def generate(self, prompt: Prompt, schema: dict[str, Any]) -> LLMResult:
        body = {
            "systemInstruction": {"parts": [{"text": prompt.system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt.user}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": gemini_schema(schema),
                                 "temperature": self.temperature, "maxOutputTokens": self.max_tokens},
        }
        t0 = time.perf_counter()
        resp = self._post(body)
        dt = time.perf_counter() - t0
        block = (resp.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise LLMError(f"prompt blocked by Gemini: {block}")
        cands = resp.get("candidates") or []
        if not cands:
            raise LLMError("Gemini returned no candidates")
        cand = cands[0]
        finish = cand.get("finishReason", "")
        if finish == "MAX_TOKENS":
            raise LLMError("response truncated at max_tokens; raise max_tokens or simplify the task")
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
        if not text:
            raise LLMError(f"no text in Gemini response (finishReason={finish or 'none'})")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON from model: {e}") from e
        u = resp.get("usageMetadata") or {}
        return LLMResult(data, dt, int(u.get("promptTokenCount", 0)),
                         int(u.get("candidatesTokenCount", 0)) + int(u.get("thoughtsTokenCount", 0)),
                         resp.get("modelVersion", self.model), finish)


def make_backend(kind: str = "auto", **kw: Any) -> LLMBackend:
    """kind: 'anthropic' | 'gemini' | 'mock' | 'auto' (anthropic if credentials look available, else mock)."""
    if kind == "mock":
        from .mock_planner import MockBackend
        return MockBackend(**kw)
    if kind == "anthropic":
        return AnthropicBackend(**kw)
    if kind == "gemini":
        return GeminiBackend(**kw)
    if kind == "auto":
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return AnthropicBackend(**kw)
        from .mock_planner import MockBackend
        return MockBackend(**kw)
    raise ValueError(f"unknown backend '{kind}'")

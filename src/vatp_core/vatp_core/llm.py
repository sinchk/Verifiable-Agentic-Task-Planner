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


def make_backend(kind: str = "auto", **kw: Any) -> LLMBackend:
    """kind: 'anthropic' | 'mock' | 'auto' (anthropic if credentials look available, else mock)."""
    if kind == "mock":
        from .mock_planner import MockBackend
        return MockBackend(**kw)
    if kind == "anthropic":
        return AnthropicBackend(**kw)
    if kind == "auto":
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return AnthropicBackend(**kw)
        from .mock_planner import MockBackend
        return MockBackend(**kw)
    raise ValueError(f"unknown backend '{kind}'")

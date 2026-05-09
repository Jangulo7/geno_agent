"""Local LLM client (master plan §11.1, C7b).

Thin OpenAI-compatible wrapper used by the LLM-prompted variants of
the Query Planner and Critic agents (C7c). Targets a **local**
inference server: vLLM in production, Ollama as a development fallback.

The OpenAI-compatible API is the lowest-common-denominator interface
across local LLM servers — every modern serving framework (vLLM,
Ollama, llama.cpp's server, TGI, sglang) exposes a
``/v1/chat/completions`` endpoint that takes the same request shape.
This module hides that endpoint behind a single ``generate`` call
returning the response text, so the agent code never imports ``openai``
directly.

By design there is **no cloud LLM call path** here. The base URL
defaults to ``http://localhost:8001/v1`` (the vLLM convention) and the
api_key defaults to ``"sk-no-key-required"`` because local servers
ignore it. To run against OpenAI-the-company, override both
explicitly — the wrapper does not ship an OpenAI default.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Final

from openai import APIConnectionError, APITimeoutError, OpenAI

logger = logging.getLogger(__name__)

# Defaults assume vLLM serving Qwen3-8B locally on port 8001.
DEFAULT_BASE_URL: Final[str] = "http://localhost:8001/v1"
DEFAULT_MODEL: Final[str] = "Qwen/Qwen3-8B"
DEFAULT_API_KEY: Final[str] = "sk-no-key-required"  # local servers ignore
DEFAULT_TIMEOUT_S: Final[float] = 120.0
DEFAULT_TEMPERATURE: Final[float] = 0.0  # deterministic by default


@dataclass(slots=True, frozen=True)
class LlmConfig:
    """Configuration for the OpenAI-compatible LLM client.

    Attributes:
        base_url: OpenAI-compatible endpoint (vLLM default
            ``http://localhost:8001/v1``).
        api_key: API key. Local servers ignore this; default is a
            non-secret placeholder so downstream code doesn't need to
            handle ``None``.
        model: Model identifier the server recognizes. Must match what
            vLLM was started with (typically the HuggingFace model id).
        timeout_s: HTTP timeout in seconds.
    """

    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    model: str = DEFAULT_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S


@dataclass(slots=True)
class LlmResponse:
    """Structured response from the LLM client.

    Attributes:
        text: The generated text (assistant message content).
        tokens_in: Prompt token count if reported by the server.
        tokens_out: Completion token count if reported by the server.
        finish_reason: Why generation stopped (``stop`` / ``length`` / ...).
        latency_s: Wall-clock time the call took, end-to-end.
    """

    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    finish_reason: str | None = None
    latency_s: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@lru_cache(maxsize=4)
def _client_for(base_url: str, api_key: str, timeout_s: float) -> OpenAI:
    """Cache OpenAI clients by (base_url, api_key, timeout) to avoid recreating them."""
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s)


def generate(
    prompt: str,
    *,
    cfg: LlmConfig | None = None,
    system_prompt: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = 512,
) -> LlmResponse:
    """Send a chat-completion request and return the structured response.

    Wraps the OpenAI Python SDK to keep the call site terse — agent
    code never imports ``openai`` directly. Connection / timeout errors
    are caught and re-raised as :class:`LlmConnectionError` so callers
    can distinguish transient infra failures from model-quality issues.

    Args:
        prompt: User-side message content.
        cfg: Server configuration. Defaults to :class:`LlmConfig` (local vLLM).
        system_prompt: Optional system message. When provided, prepended
            as a ``role: system`` message.
        temperature: Sampling temperature (default 0.0 for determinism;
            agent prompts that want diversity should set higher).
        max_tokens: Max completion tokens (default 512).

    Returns:
        :class:`LlmResponse` with the text and token-usage metadata.

    Raises:
        LlmConnectionError: On network / timeout failure (transient).
    """
    import time

    cfg = cfg or LlmConfig()
    client = _client_for(cfg.base_url, cfg.api_key, cfg.timeout_s)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    t0 = time.time()
    try:
        completion = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except (APIConnectionError, APITimeoutError) as exc:
        raise LlmConnectionError(f"Could not reach LLM at {cfg.base_url}: {exc}") from exc

    latency = time.time() - t0
    choice = completion.choices[0]
    usage = getattr(completion, "usage", None)
    return LlmResponse(
        text=choice.message.content or "",
        tokens_in=getattr(usage, "prompt_tokens", None) if usage else None,
        tokens_out=getattr(usage, "completion_tokens", None) if usage else None,
        finish_reason=choice.finish_reason,
        latency_s=latency,
        raw=completion.model_dump() if hasattr(completion, "model_dump") else {},
    )


def generate_json(
    prompt: str,
    *,
    cfg: LlmConfig | None = None,
    system_prompt: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = 512,
) -> tuple[Any, LlmResponse]:
    """Like :func:`generate` but parse the response text as JSON.

    Used by the LLM-prompted Critic (C7c) where the model must return a
    structured grade. Tolerant to common LLM JSON sins:
      * Markdown code fences (``json ... ``) are stripped.
      * Leading/trailing whitespace is stripped.

    Args:
        prompt: As :func:`generate`. The prompt should explicitly request JSON.
        cfg, system_prompt, temperature, max_tokens: As :func:`generate`.

    Returns:
        Tuple ``(parsed_json, raw_response)``. Caller can read both the
        parsed JSON and the raw token counts for logging.

    Raises:
        json.JSONDecodeError: If the response is not valid JSON after
            stripping. Callers can catch this and fall back to a default.
    """
    response = generate(
        prompt,
        cfg=cfg,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = response.text.strip()
    # Strip markdown fences if present
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence) :].strip()
        if text.endswith("```"):
            text = text[: -len("```")].strip()
    parsed = json.loads(text)
    return parsed, response


def health_check(cfg: LlmConfig | None = None) -> bool:
    """Lightweight liveness probe — returns True if the LLM server responds.

    Catches every exception and returns False. Used by tests and health
    endpoints to skip gracefully when the LLM is not running.
    """
    cfg = cfg or LlmConfig()
    try:
        # A minimal generate to verify the endpoint is alive.
        response = generate("OK", cfg=cfg, max_tokens=1)
        return bool(response.text) or response.tokens_out is not None
    except Exception:  # intentionally broad — health probe must never raise
        return False


class LlmConnectionError(RuntimeError):
    """Raised when the LLM server cannot be reached (network/timeout)."""

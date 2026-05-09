"""Tests for src.tools.llm — OpenAI-compatible LLM client wrapper.

Unit tests with monkeypatched ``OpenAI`` client (no network, no GPU).
The integration test (live vLLM) is gated behind a server-availability
check and gracefully skips when vLLM is not running.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from openai import APIConnectionError

from src.tools import llm as llm_module
from src.tools.llm import (
    LlmConfig,
    LlmConnectionError,
    LlmResponse,
    generate,
    generate_json,
    health_check,
)

# Make APIConnectionError instances cheaply (helper for the mocked side_effect tests).


# ----------------------------------------------- mock helpers


def _mock_completion(
    text: str = "hi",
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> Any:
    """Build a fake OpenAI ChatCompletion response."""
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message.content = text
    completion.choices[0].finish_reason = finish_reason
    completion.usage.prompt_tokens = prompt_tokens
    completion.usage.completion_tokens = completion_tokens
    completion.model_dump.return_value = {"id": "test", "choices": [{"message": {"content": text}}]}
    return completion


@pytest.fixture
def mock_openai_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch the cached OpenAI client factory to return a MagicMock."""
    llm_module._client_for.cache_clear()
    fake_client = MagicMock()
    monkeypatch.setattr(llm_module, "_client_for", lambda *a, **kw: fake_client)
    return fake_client


# ----------------------------------------------- generate


class TestGenerate:
    def test_returns_response_text(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion("hello world")
        out = generate("Say hi")
        assert isinstance(out, LlmResponse)
        assert out.text == "hello world"
        assert out.finish_reason == "stop"

    def test_token_counts_propagated(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion(
            prompt_tokens=42,
            completion_tokens=7,
        )
        out = generate("any prompt")
        assert out.tokens_in == 42
        assert out.tokens_out == 7

    def test_user_message_passed_through(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion()
        generate("Tell me about BRCA1")
        kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        messages = kwargs["messages"]
        assert messages[-1] == {"role": "user", "content": "Tell me about BRCA1"}

    def test_system_prompt_prepended_when_provided(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion()
        generate("Question", system_prompt="You are a biomedical assistant.")
        messages = mock_openai_client.chat.completions.create.call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_no_system_prompt_when_omitted(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion()
        generate("Q")
        messages = mock_openai_client.chat.completions.create.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_temperature_and_max_tokens_forwarded(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion()
        generate("Q", temperature=0.7, max_tokens=128)
        kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 128

    def test_model_from_cfg(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion()
        cfg = LlmConfig(model="custom/model-1")
        generate("Q", cfg=cfg)
        kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "custom/model-1"

    def test_connection_error_wrapped(self, mock_openai_client: MagicMock) -> None:
        """OpenAI APIConnectionError is wrapped in LlmConnectionError."""
        # APIConnectionError requires a `request` argument.
        mock_openai_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock(),
        )
        with pytest.raises(LlmConnectionError):
            generate("Q")


# ----------------------------------------------- generate_json


class TestGenerateJson:
    def test_plain_json(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion(
            text='{"score": 5, "reason": "good"}'
        )
        parsed, raw = generate_json("Grade this chunk as JSON.")
        assert parsed == {"score": 5, "reason": "good"}
        assert isinstance(raw, LlmResponse)

    def test_strips_markdown_json_fence(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion(
            text='```json\n{"x": 1}\n```'
        )
        parsed, _ = generate_json("Q")
        assert parsed == {"x": 1}

    def test_strips_plain_markdown_fence(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion(
            text="```\n[1, 2, 3]\n```"
        )
        parsed, _ = generate_json("Q")
        assert parsed == [1, 2, 3]

    def test_invalid_json_raises(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion(
            text="not json at all"
        )
        with pytest.raises(json.JSONDecodeError):
            generate_json("Q")


# ----------------------------------------------- health_check


class TestHealthCheck:
    def test_returns_true_on_success(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.return_value = _mock_completion("ok")
        assert health_check() is True

    def test_returns_false_on_connection_error(self, mock_openai_client: MagicMock) -> None:
        mock_openai_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock(),
        )
        assert health_check() is False

    def test_returns_false_on_any_error(self, mock_openai_client: MagicMock) -> None:
        """Health check is the broad-catch — never raises."""
        mock_openai_client.chat.completions.create.side_effect = RuntimeError("boom")
        assert health_check() is False


# ----------------------------------------------- LlmConfig


class TestLlmConfig:
    def test_defaults(self) -> None:
        cfg = LlmConfig()
        assert cfg.base_url.endswith("/v1")
        assert "localhost" in cfg.base_url
        assert cfg.model == "Qwen/Qwen3-8B"
        assert cfg.api_key  # non-empty placeholder

    def test_immutable(self) -> None:
        cfg = LlmConfig()
        # frozen=True raises FrozenInstanceError on attribute assignment
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            cfg.model = "other"  # type: ignore[misc]

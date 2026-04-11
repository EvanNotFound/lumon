"""Tests for the native OpenAI Responses provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from nanobot.providers.openai_responses_common import (
    build_prompt_cache_key,
    convert_messages_to_responses,
)
from nanobot.providers.openai_responses_provider import OpenAIResponsesProvider
from nanobot.providers.registry import find_by_name


class _AsyncEventStream:
    def __init__(self, events):
        self._events = iter(events)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def test_convert_messages_to_responses_moves_memory_out_of_instructions() -> None:
    instructions, input_items = convert_messages_to_responses(
        [
            {
                "role": "system",
                "content": "# Identity\n\nhello\n\n---\n\n# Memory\n\nvolatile\n\n---\n\n# Skills\n\nstable",
            },
            {"role": "user", "content": "hello"},
        ]
    )

    assert "# Memory" not in instructions
    assert "# Skills" in instructions
    assert input_items[0]["role"] == "system"
    assert "# Memory" in input_items[0]["content"][0]["text"]
    assert input_items[1]["role"] == "user"


def test_build_prompt_cache_key_changes_with_tool_schema() -> None:
    key_a = build_prompt_cache_key(
        provider_name="openai",
        api_base="https://proxy.example/v1",
        model_name="gpt-5",
        instructions="stable instructions",
        tools=[
            {
                "type": "function",
                "name": "read",
                "description": "Read file",
                "parameters": {"type": "object"},
            }
        ],
    )
    key_b = build_prompt_cache_key(
        provider_name="openai",
        api_base="https://proxy.example/v1",
        model_name="gpt-5",
        instructions="stable instructions",
        tools=[
            {
                "type": "function",
                "name": "write",
                "description": "Write file",
                "parameters": {"type": "object"},
            }
        ],
    )

    assert key_a != key_b


@pytest.mark.asyncio
async def test_responses_provider_uses_stable_cache_key_and_parses_cached_tokens() -> None:
    mock_create = AsyncMock(
        return_value={
            "status": "completed",
            "output_text": "ok",
            "output": [],
            "usage": {
                "input_tokens": 20,
                "output_tokens": 5,
                "total_tokens": 25,
                "input_token_details": {"cached_tokens": 16},
            },
        }
    )
    spec = find_by_name("openai")
    messages_a = [
        {
            "role": "system",
            "content": "# nanobot\n\nYour workspace is at: /tmp/work\n\n---\n\n# Memory\n\nremember this",
        },
        {"role": "user", "content": "hello"},
    ]
    messages_b = [
        {
            "role": "system",
            "content": "# nanobot\n\nYour workspace is at: /tmp/work\n\n---\n\n# Memory\n\nremember this",
        },
        {"role": "user", "content": "something else"},
    ]

    with patch("nanobot.providers.openai_responses_provider.AsyncOpenAI") as mock_client:
        mock_client.return_value.responses.create = mock_create
        provider = OpenAIResponsesProvider(
            api_key="test-key",
            api_base="https://proxy.example/v1",
            default_model="gpt-5",
            prompt_cache_retention="24h",
            spec=spec,
        )
        first = await provider.chat(
            messages=messages_a,
            tools=[
                {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}
            ],
        )
        second = await provider.chat(
            messages=messages_b,
            tools=[
                {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}
            ],
        )

    first_kwargs = mock_create.call_args_list[0].kwargs
    second_kwargs = mock_create.call_args_list[1].kwargs
    assert first_kwargs["prompt_cache_key"] == second_kwargs["prompt_cache_key"]
    assert first_kwargs["prompt_cache_retention"] == "24h"
    assert "# Memory" not in first_kwargs["instructions"]
    assert first_kwargs["input"][0]["role"] == "system"
    assert "# Memory" in first_kwargs["input"][0]["content"][0]["text"]
    assert first.usage["cached_tokens"] == 16
    assert second.usage["cached_tokens"] == 16


@pytest.mark.asyncio
async def test_responses_provider_stream_parses_text_and_tool_calls() -> None:
    spec = find_by_name("openai")
    stream = _AsyncEventStream(
        [
            {"type": "response.output_text.delta", "delta": "hello "},
            {"type": "response.output_text.delta", "delta": "world"},
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call",
                    "call_id": "call_1",
                    "id": "fc_1",
                    "name": "read",
                },
            },
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_1",
                "arguments": '{"path":"README.md"}',
            },
            {
                "type": "response.done",
                "response": {
                    "status": "completed",
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 4,
                        "total_tokens": 16,
                        "input_token_details": {"cached_tokens": 7},
                    },
                },
            },
        ]
    )
    deltas: list[str] = []

    async def _on_delta(delta: str) -> None:
        deltas.append(delta)

    with patch("nanobot.providers.openai_responses_provider.AsyncOpenAI") as mock_client:
        mock_client.return_value.responses.create = AsyncMock(return_value=stream)
        provider = OpenAIResponsesProvider(api_key="test-key", default_model="gpt-5", spec=spec)
        response = await provider.chat_stream(
            messages=[{"role": "system", "content": "# stable"}, {"role": "user", "content": "hi"}],
            tools=[
                {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}
            ],
            on_content_delta=_on_delta,
        )

    assert deltas == ["hello ", "world"]
    assert response.content == "hello world"
    assert response.finish_reason == "tool_calls"
    assert response.usage["cached_tokens"] == 7
    assert response.tool_calls[0].id == "call_1|fc_1"
    assert response.tool_calls[0].name == "read"
    assert response.tool_calls[0].arguments == {"path": "README.md"}


@pytest.mark.asyncio
async def test_responses_provider_flattens_forced_function_tool_choice() -> None:
    spec = find_by_name("openai")

    with patch("nanobot.providers.openai_responses_provider.AsyncOpenAI") as mock_client:
        mock_client.return_value.responses.create = AsyncMock(
            return_value={"status": "completed", "output": [], "output_text": "ok"}
        )
        provider = OpenAIResponsesProvider(api_key="test-key", default_model="gpt-5", spec=spec)
        await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "memory_decision", "parameters": {}}}],
            tool_choice={"type": "function", "function": {"name": "memory_decision"}},
        )

    kwargs = mock_client.return_value.responses.create.await_args.kwargs
    assert kwargs["tool_choice"] == {"type": "function", "name": "memory_decision"}


@pytest.mark.asyncio
async def test_responses_provider_preserves_string_tool_choice() -> None:
    spec = find_by_name("openai")

    with patch("nanobot.providers.openai_responses_provider.AsyncOpenAI") as mock_client:
        mock_client.return_value.responses.create = AsyncMock(
            return_value={"status": "completed", "output": [], "output_text": "ok"}
        )
        provider = OpenAIResponsesProvider(api_key="test-key", default_model="gpt-5", spec=spec)
        await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "read", "parameters": {}}}],
            tool_choice="required",
        )

    kwargs = mock_client.return_value.responses.create.await_args.kwargs
    assert kwargs["tool_choice"] == "required"

"""Native OpenAI Responses provider for OpenAI and compatible proxies."""

from __future__ import annotations

import json
import secrets
import string
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import json_repair
from openai import AsyncOpenAI

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from nanobot.providers.openai_responses_common import (
    build_prompt_cache_key,
    convert_messages_to_responses,
    convert_responses_tool_choice,
    convert_responses_tools,
    map_responses_finish_reason,
    maybe_mapping,
    normalize_openai_usage,
)

if TYPE_CHECKING:
    from nanobot.providers.registry import ProviderSpec

_ALNUM = string.ascii_letters + string.digits


def _short_tool_id() -> str:
    return "".join(secrets.choice(_ALNUM) for _ in range(9))


class OpenAIResponsesProvider(LLMProvider):
    """Use the OpenAI Responses API with standard API-key config."""

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "gpt-5",
        extra_headers: dict[str, str] | None = None,
        prompt_cache_retention: str | None = None,
        spec: ProviderSpec | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        self.prompt_cache_retention = prompt_cache_retention
        self._spec = spec

        effective_base = api_base or (spec.default_api_base if spec else None) or None
        self._client = AsyncOpenAI(
            api_key=api_key or "no-key",
            base_url=effective_base,
            default_headers={
                "x-session-affinity": uuid.uuid4().hex,
                **(extra_headers or {}),
            },
        )

    def _build_kwargs(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
        tool_choice: str | dict[str, Any] | None,
    ) -> dict[str, Any]:
        model_name = model or self.default_model
        instructions, input_items = convert_messages_to_responses(
            self._sanitize_empty_content(messages)
        )
        converted_tools = convert_responses_tools(tools)

        kwargs: dict[str, Any] = {
            "model": model_name,
            "instructions": instructions,
            "input": input_items,
            "max_output_tokens": max(1, max_tokens),
            "temperature": temperature,
            "prompt_cache_key": build_prompt_cache_key(
                provider_name=(self._spec.name if self._spec else "custom"),
                api_base=self.api_base,
                model_name=model_name,
                instructions=instructions,
                tools=converted_tools,
            ),
        }

        if self.prompt_cache_retention:
            kwargs["prompt_cache_retention"] = self.prompt_cache_retention
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}
        if converted_tools:
            kwargs["tools"] = converted_tools
            kwargs["tool_choice"] = convert_responses_tool_choice(tool_choice)
            kwargs["parallel_tool_calls"] = True

        return kwargs

    @staticmethod
    def _extract_output_text(output_items: list[Any]) -> str | None:
        parts: list[str] = []
        for item in output_items:
            item_map = maybe_mapping(item) or {}
            if item_map.get("type") == "message":
                for content in item_map.get("content") or []:
                    content_map = maybe_mapping(content) or {}
                    if content_map.get("type") in {"output_text", "text"} and isinstance(
                        content_map.get("text"), str
                    ):
                        parts.append(content_map["text"])
        return "".join(parts) or None

    @classmethod
    def _parse_response(cls, response: Any) -> LLMResponse:
        response_map = maybe_mapping(response) or {}
        output_items = response_map.get("output") or []
        content = response_map.get("output_text") or getattr(response, "output_text", None)
        if not isinstance(content, str) or not content:
            content = cls._extract_output_text(output_items)

        tool_calls: list[ToolCallRequest] = []
        for item in output_items:
            item_map = maybe_mapping(item) or {}
            if item_map.get("type") != "function_call":
                continue
            args_raw = item_map.get("arguments") or "{}"
            args = json_repair.loads(args_raw) if isinstance(args_raw, str) else args_raw
            call_id = str(item_map.get("call_id") or _short_tool_id())
            item_id = str(item_map.get("id") or "")
            tool_calls.append(
                ToolCallRequest(
                    id=f"{call_id}|{item_id}" if item_id else call_id,
                    name=str(item_map.get("name") or ""),
                    arguments=args if isinstance(args, dict) else {},
                )
            )

        finish_reason = map_responses_finish_reason(
            response_map.get("status") or getattr(response, "status", None)
        )
        if tool_calls:
            finish_reason = "tool_calls"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=normalize_openai_usage(response),
        )

    @staticmethod
    def _handle_error(error: Exception) -> LLMResponse:
        body = getattr(error, "doc", None) or getattr(
            getattr(error, "response", None), "text", None
        )
        raw = body.strip()[:500] if body and body.strip() else str(error)
        lower = raw.lower()
        if any(
            marker in lower
            for marker in ("/responses", "responses api", "unknown url", "not found")
        ):
            raw = f"Responses mode is not supported by this endpoint. {raw}"
        return LLMResponse(content=f"Error: {raw}", finish_reason="error")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        kwargs = self._build_kwargs(
            messages, tools, model, max_tokens, temperature, reasoning_effort, tool_choice
        )
        try:
            response = await self._client.responses.create(**kwargs)
            return self._parse_response(response)
        except Exception as error:
            return self._handle_error(error)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        kwargs = self._build_kwargs(
            messages, tools, model, max_tokens, temperature, reasoning_effort, tool_choice
        )
        kwargs["stream"] = True
        content_parts: list[str] = []
        tool_call_buffers: dict[str, dict[str, Any]] = {}
        usage: dict[str, int] = {}
        finish_reason = "stop"

        try:
            stream = await self._client.responses.create(**kwargs)
            async for event in stream:
                event_map = maybe_mapping(event) or {}
                event_type = str(event_map.get("type") or getattr(event, "type", ""))

                if event_type == "response.output_text.delta":
                    delta_text = str(event_map.get("delta") or getattr(event, "delta", ""))
                    if delta_text:
                        content_parts.append(delta_text)
                        if on_content_delta:
                            await on_content_delta(delta_text)
                    continue

                if event_type == "response.output_item.added":
                    item = event_map.get("item") or getattr(event, "item", None)
                    item_map = maybe_mapping(item) or {}
                    if item_map.get("type") == "function_call":
                        call_id = str(item_map.get("call_id") or "")
                        if call_id:
                            tool_call_buffers[call_id] = {
                                "id": str(item_map.get("id") or ""),
                                "name": str(item_map.get("name") or ""),
                                "arguments": str(item_map.get("arguments") or ""),
                            }
                    continue

                if event_type == "response.function_call_arguments.delta":
                    call_id = str(event_map.get("call_id") or getattr(event, "call_id", ""))
                    if call_id and call_id in tool_call_buffers:
                        tool_call_buffers[call_id]["arguments"] += str(
                            event_map.get("delta") or getattr(event, "delta", "")
                        )
                    continue

                if event_type == "response.function_call_arguments.done":
                    call_id = str(event_map.get("call_id") or getattr(event, "call_id", ""))
                    if call_id and call_id in tool_call_buffers:
                        tool_call_buffers[call_id]["arguments"] = str(
                            event_map.get("arguments") or getattr(event, "arguments", "")
                        )
                    continue

                if event_type == "response.output_item.done":
                    item = event_map.get("item") or getattr(event, "item", None)
                    item_map = maybe_mapping(item) or {}
                    if item_map.get("type") == "function_call":
                        call_id = str(item_map.get("call_id") or "")
                        if call_id and call_id not in tool_call_buffers:
                            tool_call_buffers[call_id] = {
                                "id": str(item_map.get("id") or ""),
                                "name": str(item_map.get("name") or ""),
                                "arguments": str(item_map.get("arguments") or ""),
                            }
                    continue

                if event_type in {"response.done", "response.completed"}:
                    final_response = (
                        event_map.get("response") or getattr(event, "response", None) or event
                    )
                    usage = normalize_openai_usage(final_response) or usage
                    status = None
                    final_map = maybe_mapping(final_response)
                    if final_map is not None:
                        status = final_map.get("status")
                    else:
                        status = getattr(final_response, "status", None)
                    finish_reason = map_responses_finish_reason(status)

            tool_calls: list[ToolCallRequest] = []
            for call_id, buffer in tool_call_buffers.items():
                args_raw = buffer.get("arguments") or "{}"
                try:
                    args = json.loads(args_raw)
                except Exception:
                    args = json_repair.loads(args_raw)
                tool_calls.append(
                    ToolCallRequest(
                        id=f"{call_id}|{buffer.get('id') or ''}".rstrip("|"),
                        name=buffer.get("name") or "",
                        arguments=args if isinstance(args, dict) else {},
                    )
                )
            if tool_calls:
                finish_reason = "tool_calls"

            return LLMResponse(
                content="".join(content_parts) or None,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=usage,
            )
        except Exception as error:
            return self._handle_error(error)

    def get_default_model(self) -> str:
        return self.default_model

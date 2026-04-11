"""Shared helpers for OpenAI Responses-style providers."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse


def maybe_mapping(value: Any) -> dict[str, Any] | None:
    """Try to coerce SDK objects to plain dicts."""
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped
    return None


def extract_text_content(value: Any) -> str | None:
    """Extract concatenated text from Responses-style content blocks."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            item_map = maybe_mapping(item)
            if item_map is not None:
                text = item_map.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
                continue
            if isinstance(item, str):
                parts.append(item)
        return "".join(parts) or None
    return str(value)


def normalize_openai_usage(value: Any) -> dict[str, int]:
    """Normalize OpenAI Chat/Responses usage payloads to a flat dict."""
    usage_obj = None
    value_map = maybe_mapping(value)
    if value_map is not None and "usage" in value_map:
        usage_obj = value_map.get("usage")
    elif hasattr(value, "usage") and getattr(value, "usage") is not None:
        usage_obj = getattr(value, "usage")
    else:
        usage_obj = value

    usage_map = maybe_mapping(usage_obj)
    if usage_map is None and usage_obj is None:
        return {}

    def _nested_int(source: dict[str, Any] | None, *path: str) -> int | None:
        current: Any = source
        for key in path:
            if current is None:
                return None
            current_map = maybe_mapping(current)
            if current_map is not None:
                current = current_map.get(key)
            else:
                current = getattr(current, key, None)
        if current is None:
            return None
        try:
            return int(current)
        except (TypeError, ValueError):
            return None

    prompt_tokens = _nested_int(usage_map, "prompt_tokens")
    if prompt_tokens is None:
        prompt_tokens = _nested_int(usage_map, "input_tokens") or 0
    completion_tokens = _nested_int(usage_map, "completion_tokens")
    if completion_tokens is None:
        completion_tokens = _nested_int(usage_map, "output_tokens") or 0
    total_tokens = _nested_int(usage_map, "total_tokens")
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens

    normalized = {
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": int(total_tokens),
    }

    cached_tokens = _nested_int(usage_map, "prompt_tokens_details", "cached_tokens")
    if cached_tokens is None:
        cached_tokens = _nested_int(usage_map, "input_token_details", "cached_tokens")
    if cached_tokens is not None:
        normalized["cached_tokens"] = int(cached_tokens)

    return normalized


def strip_tool_call_item_id(tool_call_id: Any) -> tuple[str, str | None]:
    """Split a combined call_id|item_id into its parts."""
    if isinstance(tool_call_id, str) and tool_call_id:
        if "|" in tool_call_id:
            call_id, item_id = tool_call_id.split("|", 1)
            return call_id, item_id or None
        return tool_call_id, None
    return "call_0", None


def convert_responses_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Convert OpenAI chat tool schema to Responses function tools."""
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        if tool.get("type") == "function" and tool.get("name"):
            fn = tool
        elif tool.get("type") == "function":
            fn = tool.get("function") or {}
        else:
            fn = tool
        name = fn.get("name")
        if not name:
            continue
        params = fn.get("parameters") or {}
        converted.append(
            {
                "type": "function",
                "name": name,
                "description": fn.get("description") or "",
                "parameters": params if isinstance(params, dict) else {},
            }
        )
    converted.sort(key=lambda item: str(item.get("name") or ""))
    return converted


def convert_responses_tool_choice(tool_choice: str | dict[str, Any] | None) -> str | dict[str, Any]:
    """Convert internal tool_choice values to the Responses API shape."""
    if not isinstance(tool_choice, dict):
        return tool_choice or "auto"

    choice_type = tool_choice.get("type")
    if choice_type != "function":
        return tool_choice

    name = tool_choice.get("name")
    if isinstance(name, str) and name:
        return {"type": "function", "name": name}

    function = tool_choice.get("function")
    if isinstance(function, dict):
        nested_name = function.get("name")
        if isinstance(nested_name, str) and nested_name:
            return {"type": "function", "name": nested_name}

    return tool_choice


def split_system_prompt_for_responses(system_prompt: str) -> tuple[str, list[dict[str, Any]]]:
    """Keep stable prompt sections in instructions and move memory into input."""
    if not system_prompt:
        return "", []

    stable_parts: list[str] = []
    volatile_parts: list[str] = []
    for part in system_prompt.split("\n\n---\n\n"):
        clean = part.strip()
        if not clean:
            continue
        if clean.startswith("# Memory"):
            volatile_parts.append(clean)
            continue
        stable_parts.append(clean)

    input_items = [
        {"role": "system", "content": [{"type": "input_text", "text": part}]}
        for part in volatile_parts
    ]
    return "\n\n---\n\n".join(stable_parts), input_items


def _convert_message_blocks(content: Any, *, text_type: str) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": text_type, "text": content}]
    if isinstance(content, list):
        converted: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                converted.append({"type": text_type, "text": item.get("text", "")})
            elif item_type == "image_url":
                url = (item.get("image_url") or {}).get("url")
                if url:
                    converted.append({"type": "input_image", "image_url": url, "detail": "auto"})
        if converted:
            return converted
    return [{"type": text_type, "text": ""}]


def convert_messages_to_responses(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Convert nanobot chat messages into Responses instructions and input."""
    instructions = ""
    input_items: list[dict[str, Any]] = []

    for idx, msg in enumerate(messages):
        role = str(msg.get("role") or "user")
        content = msg.get("content")

        if role == "system":
            prompt = extract_text_content(content) or ""
            instructions, volatile_items = split_system_prompt_for_responses(prompt)
            input_items.extend(volatile_items)
            continue

        if role == "user":
            input_items.append(
                {
                    "role": "user",
                    "content": _convert_message_blocks(content, text_type="input_text"),
                }
            )
            continue

        if role == "assistant":
            text_blocks = (
                _convert_message_blocks(content, text_type="output_text") if content else []
            )
            if text_blocks:
                input_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": text_blocks,
                        "status": "completed",
                        "id": f"msg_{idx}",
                    }
                )
            for tool_call in msg.get("tool_calls") or []:
                fn = tool_call.get("function") or {}
                call_id, item_id = strip_tool_call_item_id(tool_call.get("id"))
                input_items.append(
                    {
                        "type": "function_call",
                        "id": item_id or f"fc_{idx}",
                        "call_id": call_id or f"call_{idx}",
                        "name": fn.get("name"),
                        "arguments": fn.get("arguments") or "{}",
                    }
                )
            continue

        if role == "tool":
            call_id, _ = strip_tool_call_item_id(msg.get("tool_call_id"))
            output_text = (
                content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            )
            input_items.append(
                {"type": "function_call_output", "call_id": call_id, "output": output_text}
            )
            continue

        input_items.append(
            {"role": role, "content": _convert_message_blocks(content, text_type="input_text")}
        )

    return instructions, input_items


_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")
_WORKSPACE_RE = re.compile(r"^Your workspace is at:\s*(.+)$", re.MULTILINE)


def _model_family(model_name: str) -> str:
    bare = model_name.split("/", 1)[-1]
    return _DATE_SUFFIX_RE.sub("", bare)


def _deployment_scope(api_base: str | None) -> str:
    if not api_base:
        return "default"
    parsed = urlparse(api_base)
    host = parsed.netloc or parsed.path
    path = parsed.path.rstrip("/")
    return f"{host}{path}"


def _workspace_scope(instructions: str) -> str:
    match = _WORKSPACE_RE.search(instructions)
    return match.group(1).strip() if match else ""


def build_prompt_cache_key(
    *,
    provider_name: str,
    api_base: str | None,
    model_name: str,
    instructions: str,
    tools: list[dict[str, Any]] | None,
) -> str:
    """Build a stable prompt cache key from request identity."""
    payload = {
        "provider": provider_name,
        "deployment_scope": _deployment_scope(api_base),
        "workspace_scope": _workspace_scope(instructions),
        "model_family": _model_family(model_name),
        "instructions_sha": hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
        "tools": convert_responses_tools(tools),
    }
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_FINISH_REASON_MAP = {
    "completed": "stop",
    "incomplete": "length",
    "failed": "error",
    "cancelled": "error",
}


def map_responses_finish_reason(status: str | None) -> str:
    """Normalize Responses API status values to LLMResponse finish reasons."""
    return _FINISH_REASON_MAP.get(status or "completed", "stop")

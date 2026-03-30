"""Tests for configurable runtime timezone propagation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.context import ContextBuilder
from nanobot.heartbeat.service import HeartbeatService
from nanobot.providers.base import LLMResponse
from nanobot.utils.helpers import current_time_str


def test_current_time_str_supports_configured_timezone() -> None:
    value = current_time_str("UTC")
    assert value
    assert "(UTC)" in value


def test_current_time_str_falls_back_on_invalid_timezone() -> None:
    value = current_time_str("Mars/Phobos")
    assert value


def test_context_builder_uses_runtime_timezone(monkeypatch, tmp_path) -> None:
    seen: list[str | None] = []

    def _fake_time(tz_name: str | None = None) -> str:
        seen.append(tz_name)
        return "2026-03-30 12:00 (Monday) (mock)"

    monkeypatch.setattr("nanobot.agent.context.current_time_str", _fake_time)

    builder = ContextBuilder(tmp_path, runtime_timezone="Asia/Shanghai")
    messages = builder.build_messages(history=[], current_message="hello")

    assert seen == ["Asia/Shanghai"]
    assert "Current Time: 2026-03-30 12:00 (Monday) (mock)" in messages[-1]["content"]


@pytest.mark.asyncio
async def test_heartbeat_service_uses_runtime_timezone(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "nanobot.utils.helpers.current_time_str",
        lambda tz_name=None: f"mock-time({tz_name})",
    )

    provider = MagicMock()
    provider.chat_with_retry = AsyncMock(return_value=LLMResponse(content="", tool_calls=[]))

    service = HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="openai/gpt-4o-mini",
        runtime_timezone="Asia/Shanghai",
    )

    await service._decide("- [ ] task")

    messages = provider.chat_with_retry.await_args.kwargs["messages"]
    assert "Current Time: mock-time(Asia/Shanghai)" in messages[1]["content"]

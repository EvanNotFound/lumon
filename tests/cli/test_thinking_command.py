"""Tests for /thinking command behavior and reasoning-effort propagation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.agent.tools.spawn import SpawnTool
from nanobot.bus.events import InboundMessage
from nanobot.providers.base import GenerationSettings, LLMResponse
from nanobot.session.manager import Session, SessionManager, set_session_reasoning_effort_override


def _make_workspace() -> MagicMock:
    workspace = MagicMock(spec=Path)
    workspace.__truediv__ = MagicMock(return_value=MagicMock())
    return workspace


def _make_loop(*, session_manager=None):
    """Create a minimal AgentLoop with mocked dependencies."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings()
    workspace = _make_workspace()

    with (
        patch("nanobot.agent.loop.ContextBuilder"),
        patch("nanobot.agent.loop.SessionManager"),
        patch("nanobot.agent.loop.SubagentManager"),
    ):
        loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=workspace,
            session_manager=session_manager,
        )
    return loop, bus, provider


class TestThinkingCommand:
    @pytest.mark.asyncio
    async def test_inspect_uses_default_when_no_override(self):
        loop, _bus, provider = _make_loop()
        provider.generation = GenerationSettings(reasoning_effort="medium")
        session = Session(key="cli:direct")
        loop.sessions.get_or_create.return_value = session

        response = await loop._process_message(
            InboundMessage(channel="cli", sender_id="user", chat_id="direct", content="/thinking")
        )

        assert response is not None
        assert "Thinking level for this chat: medium" in response.content
        assert "Source: default" in response.content

    @pytest.mark.asyncio
    async def test_set_and_clear_override(self):
        loop, _bus, _provider = _make_loop()
        session = Session(key="cli:direct")
        loop.sessions.get_or_create.return_value = session

        set_response = await loop._process_message(
            InboundMessage(
                channel="cli", sender_id="user", chat_id="direct", content="/thinking high"
            )
        )

        assert set_response is not None
        assert session.metadata["reasoning_effort"] == "high"
        assert "Source: chat override" in set_response.content
        loop.sessions.save.assert_called_once_with(session)

        clear_response = await loop._process_message(
            InboundMessage(
                channel="cli", sender_id="user", chat_id="direct", content="/thinking off"
            )
        )

        assert clear_response is not None
        assert "reasoning_effort" not in session.metadata
        assert "Thinking override cleared" in clear_response.content

    @pytest.mark.asyncio
    async def test_rejects_invalid_value(self):
        loop, _bus, _provider = _make_loop()
        session = Session(key="cli:direct")
        loop.sessions.get_or_create.return_value = session

        response = await loop._process_message(
            InboundMessage(
                channel="cli", sender_id="user", chat_id="direct", content="/thinking ultra"
            )
        )

        assert response is not None
        assert "Invalid thinking level: ultra" in response.content
        assert "Supported values: off, low, medium, high" in response.content

    @pytest.mark.asyncio
    async def test_new_preserves_reasoning_override(self):
        loop, _bus, _provider = _make_loop()
        session = Session(key="cli:direct")
        session.messages = [{"role": "user", "content": "hello"}]
        set_session_reasoning_effort_override(session, "high")
        loop.sessions.get_or_create.return_value = session
        loop.memory_consolidator.remember_messages = AsyncMock()

        response = await loop._process_message(
            InboundMessage(channel="cli", sender_id="user", chat_id="direct", content="/new")
        )

        assert response is not None
        assert response.content == "New session started."
        assert session.messages == []
        assert session.metadata["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_help_includes_thinking_command(self):
        loop, _bus, _provider = _make_loop()

        response = await loop._process_message(
            InboundMessage(channel="cli", sender_id="user", chat_id="direct", content="/help")
        )

        assert response is not None
        assert "/thinking" in response.content


class TestThinkingPersistence:
    def test_session_manager_persists_reasoning_override(self, tmp_path):
        manager = SessionManager(tmp_path)
        session = Session(key="telegram:1")
        set_session_reasoning_effort_override(session, "high")
        manager.save(session)

        reloaded = SessionManager(tmp_path).get_or_create("telegram:1")

        assert reloaded.metadata["reasoning_effort"] == "high"

    def test_topic_sessions_keep_distinct_overrides(self, tmp_path):
        manager = SessionManager(tmp_path)
        topic_one = Session(key="telegram:-100:topic:1")
        topic_two = Session(key="telegram:-100:topic:2")
        set_session_reasoning_effort_override(topic_one, "low")
        set_session_reasoning_effort_override(topic_two, "high")
        manager.save(topic_one)
        manager.save(topic_two)

        reloaded = SessionManager(tmp_path)
        assert reloaded.get_or_create("telegram:-100:topic:1").metadata["reasoning_effort"] == "low"
        assert (
            reloaded.get_or_create("telegram:-100:topic:2").metadata["reasoning_effort"] == "high"
        )


class TestReasoningPropagation:
    @pytest.mark.asyncio
    async def test_main_run_uses_session_override(self):
        loop, _bus, provider = _make_loop()
        provider.chat_with_retry = AsyncMock(return_value=LLMResponse(content="ok", tool_calls=[]))
        loop.context.skills.match_message_skills.return_value = []
        loop.context.build_messages.return_value = [{"role": "user", "content": "hello"}]
        loop.context.memory.load_prompt_memory = AsyncMock()
        loop.memory_consolidator.consolidate_session_if_needed = AsyncMock()
        loop.memory_consolidator.process_post_turn_memory = AsyncMock()
        session = Session(key="cli:direct")
        set_session_reasoning_effort_override(session, "high")
        loop.sessions.get_or_create.return_value = session
        loop.sessions.save = MagicMock()

        response = await loop._process_message(
            InboundMessage(channel="cli", sender_id="user", chat_id="direct", content="hello")
        )

        assert response is not None
        assert provider.chat_with_retry.await_args.kwargs["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_spawn_tool_passes_reasoning_context_to_manager(self):
        manager = SimpleNamespace(spawn=AsyncMock(return_value="ok"))
        tool = SpawnTool(manager)
        tool.set_context("telegram", "123", "telegram:123:topic:9", "medium")

        result = await tool.execute("do work", label="job")

        assert result == "ok"
        manager.spawn.assert_awaited_once_with(
            task="do work",
            label="job",
            origin_channel="telegram",
            origin_chat_id="123",
            session_key="telegram:123:topic:9",
            reasoning_effort="medium",
        )

    @pytest.mark.asyncio
    async def test_subagent_run_spec_receives_reasoning_effort(self, tmp_path):
        from nanobot.agent.subagent import SubagentManager
        from nanobot.bus.queue import MessageBus

        provider = MagicMock()
        provider.get_default_model.return_value = "test-model"
        provider.generation = GenerationSettings()
        mgr = SubagentManager(provider=provider, workspace=tmp_path, bus=MessageBus())
        mgr.runner.run = AsyncMock(
            return_value=SimpleNamespace(final_content="done", stop_reason="completed", error=None)
        )
        mgr._announce_result = AsyncMock()

        await mgr._run_subagent(
            "sub-1", "do task", "label", {"channel": "cli", "chat_id": "c1"}, "low"
        )

        spec = mgr.runner.run.await_args.args[0]
        assert spec.reasoning_effort == "low"

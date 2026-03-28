"""Test message tool suppress logic for final replies."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.message import MessageTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.config.schema import ChannelsConfig
from nanobot.providers.base import LLMResponse, ToolCallRequest


def _make_loop(tmp_path: Path, *, channels_config: ChannelsConfig | None = None) -> AgentLoop:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        channels_config=channels_config,
    )


class TestMessageToolSuppressLogic:
    """Final reply suppressed only when message tool sends to the same target."""

    @pytest.mark.asyncio
    async def test_suppress_when_sent_to_same_target(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1",
            name="message",
            arguments={"content": "Hello", "channel": "feishu", "chat_id": "chat123"},
        )
        calls = iter(
            [
                LLMResponse(content="", tool_calls=[tool_call]),
                LLMResponse(content="Done", tool_calls=[]),
            ]
        )
        loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        sent: list[OutboundMessage] = []
        mt = loop.tools.get("message")
        if isinstance(mt, MessageTool):
            mt.set_send_callback(AsyncMock(side_effect=lambda m: sent.append(m)))

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Send")
        result = await loop._process_message(msg)

        assert len(sent) == 1
        assert result is None  # suppressed

    @pytest.mark.asyncio
    async def test_not_suppress_when_sent_to_different_target(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1",
            name="message",
            arguments={
                "content": "Email content",
                "channel": "email",
                "chat_id": "user@example.com",
            },
        )
        calls = iter(
            [
                LLMResponse(content="", tool_calls=[tool_call]),
                LLMResponse(content="I've sent the email.", tool_calls=[]),
            ]
        )
        loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        sent: list[OutboundMessage] = []
        mt = loop.tools.get("message")
        if isinstance(mt, MessageTool):
            mt.set_send_callback(AsyncMock(side_effect=lambda m: sent.append(m)))

        msg = InboundMessage(
            channel="feishu", sender_id="user1", chat_id="chat123", content="Send email"
        )
        result = await loop._process_message(msg)

        assert len(sent) == 1
        assert sent[0].channel == "email"
        assert result is not None  # not suppressed
        assert result.channel == "feishu"

    @pytest.mark.asyncio
    async def test_not_suppress_when_no_message_tool_used(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.provider.chat_with_retry = AsyncMock(
            return_value=LLMResponse(content="Hello!", tool_calls=[])
        )
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Hi")
        result = await loop._process_message(msg)

        assert result is not None
        assert "Hello" in result.content

    async def test_progress_hides_internal_reasoning(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(id="call1", name="read_file", arguments={"path": "foo.txt"})
        calls = iter(
            [
                LLMResponse(
                    content="Visible<think>hidden</think>",
                    tool_calls=[tool_call],
                    reasoning_content="secret reasoning",
                    thinking_blocks=[{"signature": "sig", "thought": "secret thought"}],
                ),
                LLMResponse(content="Done", tool_calls=[]),
            ]
        )
        loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])
        loop.tools.execute = AsyncMock(return_value="ok")

        progress: list[tuple[str, bool]] = []

        async def on_progress(content: str, *, tool_hint: bool = False) -> None:
            progress.append((content, tool_hint))

        final_content, _, _ = await loop._run_agent_loop([], on_progress=on_progress)

        assert final_content == "Done"
        assert progress == [
            ("Visible", False),
            ('read_file("foo.txt")', True),
        ]

    @pytest.mark.asyncio
    async def test_process_message_tags_reasoning_progress(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(id="call1", name="read_file", arguments={"path": "foo.txt"})
        calls = iter(
            [
                LLMResponse(content="Visible<think>hidden</think>", tool_calls=[tool_call]),
                LLMResponse(content="Done", tool_calls=[]),
            ]
        )
        loop.provider.chat_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])
        loop.tools.execute = AsyncMock(return_value="ok")

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Hi")
        result = await loop._process_message(msg)

        reasoning = await loop.bus.consume_outbound()
        tool_hint = await loop.bus.consume_outbound()

        assert result is not None
        assert result.content == "Done"
        assert reasoning.content == "Visible"
        assert reasoning.metadata["_progress"] is True
        assert reasoning.metadata["_progress_kind"] == "reasoning"
        assert reasoning.metadata["_tool_hint"] is False
        assert tool_hint.content == 'read_file("foo.txt")'
        assert tool_hint.metadata["_progress"] is True
        assert tool_hint.metadata["_progress_kind"] == "tool_hint"
        assert tool_hint.metadata["_tool_hint"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "channels_config",
        [
            ChannelsConfig(send_progress=False),
            ChannelsConfig(send_reasoning_steps=False),
        ],
    )
    async def test_dispatch_disables_streaming_when_reasoning_visibility_hidden(
        self,
        tmp_path: Path,
        channels_config: ChannelsConfig,
    ) -> None:
        loop = _make_loop(tmp_path, channels_config=channels_config)
        response = LLMResponse(content="Done", tool_calls=[])
        loop.provider.chat_with_retry = AsyncMock(return_value=response)
        loop.provider.chat_stream_with_retry = AsyncMock(return_value=response)
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(
            channel="telegram",
            sender_id="user1",
            chat_id="chat123",
            content="Hi",
            metadata={"_wants_stream": True},
        )

        await loop._dispatch(msg)

        outbound = await loop.bus.consume_outbound()

        assert outbound.content == "Done"
        assert outbound.metadata.get("_streamed") is None
        loop.provider.chat_with_retry.assert_awaited_once()
        loop.provider.chat_stream_with_retry.assert_not_awaited()
        assert loop.bus.outbound.empty()

    @pytest.mark.asyncio
    async def test_dispatch_keeps_streaming_when_reasoning_visible(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path, channels_config=ChannelsConfig())

        async def _stream_response(*_args, **kwargs):
            await kwargs["on_content_delta"]("Hello")
            return LLMResponse(content="Hello", tool_calls=[])

        loop.provider.chat_with_retry = AsyncMock(
            return_value=LLMResponse(content="fallback", tool_calls=[])
        )
        loop.provider.chat_stream_with_retry = AsyncMock(side_effect=_stream_response)
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(
            channel="telegram",
            sender_id="user1",
            chat_id="chat123",
            content="Hi",
            metadata={"_wants_stream": True},
        )

        await loop._dispatch(msg)

        delta = await loop.bus.consume_outbound()
        stream_end = await loop.bus.consume_outbound()
        final = await loop.bus.consume_outbound()

        assert delta.content == "Hello"
        assert delta.metadata["_stream_delta"] is True
        assert stream_end.metadata["_stream_end"] is True
        assert final.content == "Hello"
        assert final.metadata["_streamed"] is True
        loop.provider.chat_stream_with_retry.assert_awaited_once()
        loop.provider.chat_with_retry.assert_not_awaited()
        assert loop.bus.outbound.empty()


class TestMessageToolTurnTracking:
    def test_sent_in_turn_tracks_same_target(self) -> None:
        tool = MessageTool()
        tool.set_context("feishu", "chat1")
        assert not tool._sent_in_turn
        tool._sent_in_turn = True
        assert tool._sent_in_turn

    def test_start_turn_resets(self) -> None:
        tool = MessageTool()
        tool._sent_in_turn = True
        tool.start_turn()
        assert not tool._sent_in_turn

from unittest.mock import AsyncMock, MagicMock

import pytest

import nanobot.agent.memory as memory_module
from nanobot.agent.loop import AgentLoop
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMResponse, ToolCallRequest


def _make_loop(tmp_path, *, estimated_tokens: int, context_window_tokens: int) -> AgentLoop:
    from nanobot.providers.base import GenerationSettings

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings(max_tokens=0)
    provider.estimate_prompt_tokens.return_value = (estimated_tokens, "test-counter")
    _response = LLMResponse(content="ok", tool_calls=[])
    provider.chat_with_retry = AsyncMock(return_value=_response)
    provider.chat_stream_with_retry = AsyncMock(return_value=_response)

    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        context_window_tokens=context_window_tokens,
    )
    loop.tools.get_definitions = MagicMock(return_value=[])
    loop.memory_consolidator._SAFETY_BUFFER = 0
    return loop


@pytest.mark.asyncio
async def test_prompt_below_threshold_does_not_consolidate(tmp_path) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=100, context_window_tokens=200)
    loop.memory_consolidator.consolidate_messages = AsyncMock(return_value=True)  # type: ignore[method-assign]

    await loop.process_direct("hello", session_key="cli:test")

    loop.memory_consolidator.consolidate_messages.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_above_threshold_triggers_consolidation(tmp_path, monkeypatch) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=1000, context_window_tokens=200)
    loop.memory_consolidator.consolidate_messages = AsyncMock(return_value=True)  # type: ignore[method-assign]
    session = loop.sessions.get_or_create("cli:test")
    session.messages = [
        {"role": "user", "content": "u1", "timestamp": "2026-01-01T00:00:00"},
        {"role": "assistant", "content": "a1", "timestamp": "2026-01-01T00:00:01"},
        {"role": "user", "content": "u2", "timestamp": "2026-01-01T00:00:02"},
    ]
    loop.sessions.save(session)
    monkeypatch.setattr(memory_module, "estimate_message_tokens", lambda _message: 500)

    await loop.process_direct("hello", session_key="cli:test")

    assert loop.memory_consolidator.consolidate_messages.await_count >= 1


@pytest.mark.asyncio
async def test_prompt_above_threshold_archives_until_next_user_boundary(
    tmp_path, monkeypatch
) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=1000, context_window_tokens=200)
    loop.memory_consolidator.consolidate_messages = AsyncMock(return_value=True)  # type: ignore[method-assign]

    session = loop.sessions.get_or_create("cli:test")
    session.messages = [
        {"role": "user", "content": "u1", "timestamp": "2026-01-01T00:00:00"},
        {"role": "assistant", "content": "a1", "timestamp": "2026-01-01T00:00:01"},
        {"role": "user", "content": "u2", "timestamp": "2026-01-01T00:00:02"},
        {"role": "assistant", "content": "a2", "timestamp": "2026-01-01T00:00:03"},
        {"role": "user", "content": "u3", "timestamp": "2026-01-01T00:00:04"},
    ]
    loop.sessions.save(session)

    token_map = {"u1": 120, "a1": 120, "u2": 120, "a2": 120, "u3": 120}
    monkeypatch.setattr(
        memory_module, "estimate_message_tokens", lambda message: token_map[message["content"]]
    )

    await loop.memory_consolidator.consolidate_session_if_needed(session)

    archived_chunk = loop.memory_consolidator.consolidate_messages.await_args.args[0]
    assert [message["content"] for message in archived_chunk] == ["u1", "a1", "u2", "a2"]
    assert session.last_consolidated == 4


@pytest.mark.asyncio
async def test_consolidation_loops_until_target_met(tmp_path, monkeypatch) -> None:
    """Verify consolidate_session_if_needed keeps looping until under threshold."""
    loop = _make_loop(tmp_path, estimated_tokens=0, context_window_tokens=200)
    loop.memory_consolidator.consolidate_messages = AsyncMock(return_value=True)  # type: ignore[method-assign]

    session = loop.sessions.get_or_create("cli:test")
    session.messages = [
        {"role": "user", "content": "u1", "timestamp": "2026-01-01T00:00:00"},
        {"role": "assistant", "content": "a1", "timestamp": "2026-01-01T00:00:01"},
        {"role": "user", "content": "u2", "timestamp": "2026-01-01T00:00:02"},
        {"role": "assistant", "content": "a2", "timestamp": "2026-01-01T00:00:03"},
        {"role": "user", "content": "u3", "timestamp": "2026-01-01T00:00:04"},
        {"role": "assistant", "content": "a3", "timestamp": "2026-01-01T00:00:05"},
        {"role": "user", "content": "u4", "timestamp": "2026-01-01T00:00:06"},
    ]
    loop.sessions.save(session)

    call_count = [0]

    def mock_estimate(_session):
        call_count[0] += 1
        if call_count[0] == 1:
            return (500, "test")
        if call_count[0] == 2:
            return (300, "test")
        return (80, "test")

    loop.memory_consolidator.estimate_session_prompt_tokens = mock_estimate  # type: ignore[method-assign]
    monkeypatch.setattr(memory_module, "estimate_message_tokens", lambda _m: 100)

    await loop.memory_consolidator.consolidate_session_if_needed(session)

    assert loop.memory_consolidator.consolidate_messages.await_count == 2
    assert session.last_consolidated == 6


@pytest.mark.asyncio
async def test_consolidation_continues_below_trigger_until_half_target(
    tmp_path, monkeypatch
) -> None:
    """Once triggered, consolidation should continue until it drops below half threshold."""
    loop = _make_loop(tmp_path, estimated_tokens=0, context_window_tokens=200)
    loop.memory_consolidator.consolidate_messages = AsyncMock(return_value=True)  # type: ignore[method-assign]

    session = loop.sessions.get_or_create("cli:test")
    session.messages = [
        {"role": "user", "content": "u1", "timestamp": "2026-01-01T00:00:00"},
        {"role": "assistant", "content": "a1", "timestamp": "2026-01-01T00:00:01"},
        {"role": "user", "content": "u2", "timestamp": "2026-01-01T00:00:02"},
        {"role": "assistant", "content": "a2", "timestamp": "2026-01-01T00:00:03"},
        {"role": "user", "content": "u3", "timestamp": "2026-01-01T00:00:04"},
        {"role": "assistant", "content": "a3", "timestamp": "2026-01-01T00:00:05"},
        {"role": "user", "content": "u4", "timestamp": "2026-01-01T00:00:06"},
    ]
    loop.sessions.save(session)

    call_count = [0]

    def mock_estimate(_session):
        call_count[0] += 1
        if call_count[0] == 1:
            return (500, "test")
        if call_count[0] == 2:
            return (150, "test")
        return (80, "test")

    loop.memory_consolidator.estimate_session_prompt_tokens = mock_estimate  # type: ignore[method-assign]
    monkeypatch.setattr(memory_module, "estimate_message_tokens", lambda _m: 100)

    await loop.memory_consolidator.consolidate_session_if_needed(session)

    assert loop.memory_consolidator.consolidate_messages.await_count == 2
    assert session.last_consolidated == 6


@pytest.mark.asyncio
async def test_preflight_consolidation_before_llm_call(tmp_path, monkeypatch) -> None:
    """Verify preflight consolidation runs before the LLM call in process_direct."""
    order: list[str] = []

    loop = _make_loop(tmp_path, estimated_tokens=0, context_window_tokens=200)

    async def track_consolidate(messages):
        order.append("consolidate")
        return True

    loop.memory_consolidator.consolidate_messages = track_consolidate  # type: ignore[method-assign]

    async def track_llm(*args, **kwargs):
        order.append("llm")
        return LLMResponse(content="ok", tool_calls=[])

    loop.provider.chat_with_retry = track_llm
    loop.provider.chat_stream_with_retry = track_llm

    session = loop.sessions.get_or_create("cli:test")
    session.messages = [
        {"role": "user", "content": "u1", "timestamp": "2026-01-01T00:00:00"},
        {"role": "assistant", "content": "a1", "timestamp": "2026-01-01T00:00:01"},
        {"role": "user", "content": "u2", "timestamp": "2026-01-01T00:00:02"},
    ]
    loop.sessions.save(session)
    monkeypatch.setattr(memory_module, "estimate_message_tokens", lambda _m: 500)

    call_count = [0]

    def mock_estimate(_session):
        call_count[0] += 1
        return (1000 if call_count[0] <= 1 else 80, "test")

    loop.memory_consolidator.estimate_session_prompt_tokens = mock_estimate  # type: ignore[method-assign]

    await loop.process_direct("hello", session_key="cli:test")

    assert "consolidate" in order
    assert "llm" in order
    assert order.index("consolidate") < order.index("llm")


@pytest.mark.asyncio
async def test_load_prompt_memory_uses_current_message(tmp_path) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=100, context_window_tokens=200)
    loop.context.memory.load_prompt_memory = AsyncMock()  # type: ignore[method-assign]

    scheduled: list[tuple[object, str]] = []

    def capture_background(coro, *, label: str = "background task") -> None:
        scheduled.append((coro, label))

    loop._schedule_background = capture_background  # type: ignore[method-assign]

    session = loop.sessions.get_or_create("cli:test")
    session.messages = [
        {"role": "user", "content": "oldest", "timestamp": "2026-01-01T00:00:00"},
        {"role": "assistant", "content": "keep1", "timestamp": "2026-01-01T00:00:01"},
        {"role": "user", "content": "keep2", "timestamp": "2026-01-01T00:00:02"},
        {"role": "assistant", "content": "keep3", "timestamp": "2026-01-01T00:00:03"},
        {"role": "user", "content": "keep4", "timestamp": "2026-01-01T00:00:04"},
        {"role": "assistant", "content": "keep5", "timestamp": "2026-01-01T00:00:05"},
        {"role": "user", "content": "keep6", "timestamp": "2026-01-01T00:00:06"},
    ]
    loop.sessions.save(session)

    await loop.process_direct("current message", session_key="cli:test")

    loop.context.memory.load_prompt_memory.assert_awaited_once()
    retrieval_query = loop.context.memory.load_prompt_memory.await_args.args[0]
    for value in ("oldest", "keep1", "keep2"):
        assert value not in retrieval_query
    for value in ("keep3", "keep4", "keep5", "keep6", "current message"):
        assert value in retrieval_query

    for coro, _label in scheduled:
        coro.close()


@pytest.mark.asyncio
async def test_process_direct_schedules_post_turn_memory_in_background(tmp_path) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=100, context_window_tokens=200)

    scheduled: list[tuple[object, str]] = []

    def capture_background(coro, *, label: str = "background task") -> None:
        scheduled.append((coro, label))

    loop._schedule_background = capture_background  # type: ignore[method-assign]
    loop.memory_consolidator.decide_turn_memory_action = AsyncMock(return_value="summary")  # type: ignore[method-assign]

    response = await loop.process_direct("my online handle is evannotfound", session_key="cli:test")

    assert response is not None
    loop.memory_consolidator.decide_turn_memory_action.assert_not_awaited()
    assert len(scheduled) == 1
    coro, label = scheduled[0]
    assert label == "post-turn memory"
    coro.close()


@pytest.mark.asyncio
async def test_process_post_turn_memory_orders_judge_remember_then_consolidate(tmp_path) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=100, context_window_tokens=200)
    loop.sessions.save(loop.sessions.get_or_create("cli:test"))
    order: list[str] = []

    async def track_decide(_messages) -> str:
        order.append("judge")
        return "summary"

    async def track_remember(_messages) -> bool:
        order.append("remember")
        return True

    async def track_consolidate(_session) -> None:
        order.append("consolidate")

    loop.memory_consolidator.decide_turn_memory_action = track_decide  # type: ignore[method-assign]
    loop.memory_consolidator.remember_messages = track_remember  # type: ignore[method-assign]
    loop.memory_consolidator._consolidate_session_if_needed_locked = track_consolidate  # type: ignore[method-assign]

    await loop.memory_consolidator.process_post_turn_memory(
        "cli:test",
        [
            {"role": "user", "content": "my online handle is evannotfound"},
            {"role": "assistant", "content": "I'll remember that."},
        ],
    )

    assert order == ["judge", "remember", "consolidate"]


@pytest.mark.asyncio
async def test_process_post_turn_memory_false_skips_remember(tmp_path) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=100, context_window_tokens=200)
    loop.sessions.save(loop.sessions.get_or_create("cli:test"))
    loop.memory_consolidator.decide_turn_memory_action = AsyncMock(return_value="skip")  # type: ignore[method-assign]
    loop.memory_consolidator.remember_messages = AsyncMock(return_value=True)  # type: ignore[method-assign]
    loop.memory_consolidator._consolidate_session_if_needed_locked = AsyncMock()  # type: ignore[method-assign]

    await loop.memory_consolidator.process_post_turn_memory(
        "cli:test",
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
    )

    loop.memory_consolidator.remember_messages.assert_not_awaited()
    loop.memory_consolidator._consolidate_session_if_needed_locked.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_process_post_turn_memory_both_stores_raw_turn(tmp_path) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=100, context_window_tokens=200)
    loop.sessions.save(loop.sessions.get_or_create("cli:test"))
    loop.memory_consolidator.decide_turn_memory_action = AsyncMock(return_value="both")  # type: ignore[method-assign]
    loop.memory_consolidator.remember_messages = AsyncMock(return_value=True)  # type: ignore[method-assign]
    loop.memory_consolidator.store.save_raw_turn = AsyncMock(return_value=True)  # type: ignore[method-assign]
    loop.memory_consolidator._consolidate_session_if_needed_locked = AsyncMock()  # type: ignore[method-assign]

    await loop.memory_consolidator.process_post_turn_memory(
        "cli:test",
        [
            {"role": "user", "content": "my draft essay"},
            {"role": "assistant", "content": "got it"},
        ],
    )

    loop.memory_consolidator.remember_messages.assert_awaited_once()
    loop.memory_consolidator.store.save_raw_turn.assert_awaited_once()  # type: ignore[attr-defined]
    loop.memory_consolidator._consolidate_session_if_needed_locked.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_model_memory_decision_returns_action_from_tool_call(tmp_path) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=100, context_window_tokens=200)
    loop.provider.chat_with_retry = AsyncMock(
        return_value=LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(
                    id="call_1",
                    name="memory_decision",
                    arguments={"action": "summary", "reason": "durable user identity fact"},
                )
            ],
        )
    )

    result = await loop.memory_consolidator.decide_turn_memory_action(
        [
            {"role": "user", "content": "my handle is evannotfound"},
            {"role": "assistant", "content": "I'll remember that."},
        ]
    )

    assert result == "summary"

    messages = loop.provider.chat_with_retry.await_args.kwargs["messages"]
    assert (
        "summary as the default for durable but compressible information" in messages[0]["content"]
    )
    assert "explicit user memory requests" in messages[0]["content"]


@pytest.mark.asyncio
async def test_model_memory_decision_normalizes_legacy_consolidate_to_summary(tmp_path) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=100, context_window_tokens=200)
    loop.provider.chat_with_retry = AsyncMock(
        return_value=LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(
                    id="call_1",
                    name="memory_decision",
                    arguments={"action": "consolidate", "reason": "legacy action name"},
                )
            ],
        )
    )

    result = await loop.memory_consolidator.decide_turn_memory_action(
        [
            {"role": "user", "content": "remember the link is https://example.com"},
            {"role": "assistant", "content": "I'll remember that."},
        ]
    )

    assert result == "summary"


@pytest.mark.asyncio
async def test_model_memory_decision_without_tool_call_defaults_skip(tmp_path) -> None:
    loop = _make_loop(tmp_path, estimated_tokens=100, context_window_tokens=200)
    loop.provider.chat_with_retry = AsyncMock(return_value=LLMResponse(content="no", tool_calls=[]))

    result = await loop.memory_consolidator.decide_turn_memory_action(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
    )

    assert result == "skip"

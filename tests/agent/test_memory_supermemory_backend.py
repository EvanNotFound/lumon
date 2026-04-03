from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from nanobot.agent.memory import MemoryStore
from nanobot.config.schema import MemoryConfig, SupermemoryConfig
from nanobot.providers.base import LLMResponse, ToolCallRequest


def _make_messages(message_count: int = 20) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": f"msg{i}", "timestamp": "2026-01-01 00:00"}
        for i in range(message_count)
    ]


def _make_summary_tool_response(summary_entry: str) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[
            ToolCallRequest(
                id="call_1",
                name="save_supermemory_summary",
                arguments={
                    "summary_entry": summary_entry,
                },
            )
        ],
    )


@pytest.mark.asyncio
async def test_supermemory_backend_persists_summary_only(tmp_path: Path) -> None:
    config = MemoryConfig(
        backend="supermemory",
        supermemory=SupermemoryConfig(api_key="sm_test_key", container_tag="workspace-test"),
    )
    store = MemoryStore(tmp_path, memory_config=config)

    store._backend._supermemory_add_memory = AsyncMock(  # type: ignore[attr-defined]
        return_value={"id": "summary_1", "status": "queued"}
    )

    provider = AsyncMock()
    provider.chat_with_retry = AsyncMock(
        return_value=_make_summary_tool_response("[2026-01-01 10:00] Discussed launch checklist.")
    )

    result = await store.consolidate(_make_messages(), provider, "test-model")

    assert result is True

    store._backend._supermemory_add_memory.assert_awaited_once()  # type: ignore[attr-defined]
    call = store._backend._supermemory_add_memory.await_args  # type: ignore[attr-defined]
    assert call.kwargs.get("custom_id") is None
    assert call.kwargs["metadata"]["kind"] == "summary_turn"

    with pytest.raises(RuntimeError):
        _ = store.memory_file
    with pytest.raises(RuntimeError):
        _ = store.history_file


@pytest.mark.asyncio
async def test_supermemory_backend_persists_raw_turn_document(tmp_path: Path) -> None:
    config = MemoryConfig(
        backend="supermemory",
        supermemory=SupermemoryConfig(api_key="sm_test_key", container_tag="workspace-test"),
    )
    store = MemoryStore(tmp_path, memory_config=config)
    store._backend._supermemory_add_memory = AsyncMock(  # type: ignore[attr-defined]
        return_value={"id": "raw_1", "status": "queued"}
    )

    result = await store.save_raw_turn(
        [
            {"role": "user", "content": "essay"},
            {"role": "assistant", "content": "reviewed"},
        ]
    )

    assert result is True
    store._backend._supermemory_add_memory.assert_awaited_once()  # type: ignore[attr-defined]
    call = store._backend._supermemory_add_memory.await_args  # type: ignore[attr-defined]
    assert call.kwargs["metadata"]["kind"] == "raw_turn"
    assert "[TURN] 2 messages" in call.kwargs["content"]

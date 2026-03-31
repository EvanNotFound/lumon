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


def _make_tool_response(history_entry: str, memory_update: str) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[
            ToolCallRequest(
                id="call_1",
                name="save_memory",
                arguments={
                    "history_entry": history_entry,
                    "memory_update": memory_update,
                },
            )
        ],
    )


@pytest.mark.asyncio
async def test_supermemory_backend_persists_snapshot_and_history(tmp_path: Path) -> None:
    config = MemoryConfig(
        backend="supermemory",
        supermemory=SupermemoryConfig(api_key="sm_test_key", container_tag="workspace-test"),
    )
    store = MemoryStore(tmp_path, memory_config=config)

    store._backend._supermemory_list_memories = AsyncMock(return_value=[])  # type: ignore[attr-defined]
    store._backend._supermemory_add_memory = AsyncMock(  # type: ignore[attr-defined]
        side_effect=[
            {"id": "snapshot_1", "status": "queued"},
            {"id": "history_1", "status": "queued"},
        ]
    )

    provider = AsyncMock()
    provider.chat_with_retry = AsyncMock(
        return_value=_make_tool_response(
            history_entry="[2026-01-01 10:00] Discussed launch checklist.",
            memory_update="# Memory\nLaunch owner: Alice",
        )
    )

    result = await store.consolidate(_make_messages(), provider, "test-model")

    assert result is True
    assert store.read_long_term() == "# Memory\nLaunch owner: Alice"
    assert not store.history_file.exists()
    assert not (tmp_path / "memory").exists()

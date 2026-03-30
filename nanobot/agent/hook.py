"""Lifecycle hooks for shared agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nanobot.providers.base import LLMResponse, ToolCallRequest


@dataclass(slots=True)
class AgentHookContext:
    """Mutable per-iteration context exposed to hooks."""

    iteration: int
    messages: list[dict[str, Any]]
    response: LLMResponse | None = None
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tool_results: list[Any] = field(default_factory=list)
    tool_events: list[dict[str, str]] = field(default_factory=list)
    final_content: str | None = None
    error: str | None = None
    stop_reason: str = "completed"


class AgentHook:
    """Extension points around one agent execution loop."""

    def wants_streaming(self) -> bool:
        """Return whether the provider should stream content deltas."""
        return False

    async def before_iteration(self, context: AgentHookContext) -> None:
        """Called before each provider request."""

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        """Called after tool calls are produced and before execution."""

    async def on_stream(self, context: AgentHookContext, delta: str) -> None:
        """Called for each streamed text delta."""

    async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None:
        """Called when a streaming segment ends."""

    async def after_iteration(self, context: AgentHookContext) -> None:
        """Called at the end of each loop iteration."""

    def finalize_content(self, context: AgentHookContext, content: str | None) -> str | None:
        """Transform final assistant content before persisting/returning."""
        return content

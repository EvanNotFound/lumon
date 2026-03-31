"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import AsyncExitStack, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.hook import AgentHook, AgentHookContext
from nanobot.agent.memory import MemoryConsolidator
from nanobot.agent.runner import AgentRunner, AgentRunSpec
from nanobot.agent.skills import BUILTIN_SKILLS_DIR
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.command import CommandContext, CommandRouter, register_builtin_commands
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session, SessionManager
from nanobot.utils.helpers import should_allow_live_streaming, trim_history_for_budget

if TYPE_CHECKING:
    from nanobot.config.schema import (
        ChannelsConfig,
        ExecToolConfig,
        InputLimitsConfig,
        MemoryConfig,
        WebSearchConfig,
    )
    from nanobot.cron.service import CronService


@dataclass
class MCPServerStatus:
    """Runtime health/status snapshot for one configured MCP server."""

    name: str
    state: str = "uninitialized"
    transport: str = "unknown"
    registered_tools: list[str] = field(default_factory=list)
    available_tools: list[str] = field(default_factory=list)
    error: str | None = None
    checked_at: float | None = None
    session: Any | None = None


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 16_000
    _MEMORY_RETRIEVAL_HISTORY_LIMIT = 6
    _MEMORY_RETRIEVAL_MAX_CHARS = 400

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        context_window_tokens: int = 65_536,
        context_budget_tokens: int = 0,
        web_search_config: WebSearchConfig | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        input_limits: InputLimitsConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
        runtime_timezone: str | None = None,
        memory_config: MemoryConfig | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig, InputLimitsConfig, WebSearchConfig

        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.context_window_tokens = context_window_tokens
        self.context_budget_tokens = (
            max(context_budget_tokens, 500) if context_budget_tokens > 0 else 0
        )
        self.web_search_config = web_search_config or WebSearchConfig()
        self.web_proxy = web_proxy
        self.exec_config = exec_config or ExecToolConfig()
        self.input_limits = input_limits or InputLimitsConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self.runtime_timezone = runtime_timezone
        self._start_time = time.time()
        self._last_usage: dict[str, int] = {}

        self.context = ContextBuilder(
            workspace,
            input_limits=self.input_limits,
            runtime_timezone=self.runtime_timezone,
            memory_config=memory_config,
        )
        self.runner = AgentRunner(provider)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            web_search_config=self.web_search_config,
            web_proxy=web_proxy,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
            runtime_timezone=self.runtime_timezone,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_lock = asyncio.Lock()
        self._mcp_connected = False
        self._mcp_connecting = False
        self._mcp_status: dict[str, MCPServerStatus] = {}
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._background_tasks: list[asyncio.Task] = []
        self._session_locks: dict[str, asyncio.Lock] = {}
        # NANOBOT_MAX_CONCURRENT_REQUESTS: <=0 means unlimited; default 3.
        _max = int(os.environ.get("NANOBOT_MAX_CONCURRENT_REQUESTS", "3"))
        self._concurrency_gate: asyncio.Semaphore | None = (
            asyncio.Semaphore(_max) if _max > 0 else None
        )
        self.memory_consolidator = MemoryConsolidator(
            workspace=workspace,
            provider=provider,
            model=self.model,
            sessions=self.sessions,
            context_window_tokens=context_window_tokens,
            build_messages=self.context.build_messages,
            get_tool_definitions=self.tools.get_definitions,
            max_completion_tokens=provider.generation.max_tokens,
            memory_config=memory_config,
        )
        self._register_default_tools()
        self.commands = CommandRouter()
        register_builtin_commands(self.commands)
        self._seed_mcp_status()

    @staticmethod
    def _infer_mcp_transport(cfg: Any) -> str:
        """Infer MCP transport from config hints."""
        if cfg.type:
            return cfg.type
        if cfg.command:
            return "stdio"
        if cfg.url:
            return "sse" if cfg.url.rstrip("/").endswith("/sse") else "streamableHttp"
        return "unknown"

    def _seed_mcp_status(self) -> None:
        """Seed status entries for all configured MCP servers."""
        self._mcp_status = {
            name: MCPServerStatus(name=name, transport=self._infer_mcp_transport(cfg))
            for name, cfg in self._mcp_servers.items()
        }

    def _mcp_tools_for_server(self, server_name: str) -> list[str]:
        """List currently registered wrapped tool names for one MCP server."""
        prefix = f"mcp_{server_name}_"
        return sorted(name for name in self.tools.tool_names if name.startswith(prefix))

    def _unregister_all_mcp_tools(self) -> None:
        """Remove all currently registered MCP-wrapped tools."""
        for name in [
            tool_name for tool_name in self.tools.tool_names if tool_name.startswith("mcp_")
        ]:
            self.tools.unregister(name)

    def _set_all_mcp_failed(self, error: str) -> None:
        """Mark every configured server as failed with the same error message."""
        checked_at = time.time()
        if not self._mcp_status and self._mcp_servers:
            self._seed_mcp_status()
        for status in self._mcp_status.values():
            status.state = "failed"
            status.error = error
            status.checked_at = checked_at
            status.session = None
            status.available_tools = []
            status.registered_tools = []

    def _apply_mcp_connect_results(self, results: dict[str, Any]) -> None:
        """Update in-memory MCP status from connect results."""
        checked_at = time.time()
        for name, cfg in self._mcp_servers.items():
            status = self._mcp_status.get(name) or MCPServerStatus(
                name=name,
                transport=self._infer_mcp_transport(cfg),
            )
            result = results.get(name)
            if result is None:
                status.state = "failed"
                status.error = "No status returned from MCP connector"
                status.checked_at = checked_at
                status.session = None
                status.available_tools = []
                status.registered_tools = self._mcp_tools_for_server(name)
                self._mcp_status[name] = status
                continue

            status.transport = result.transport or status.transport
            status.error = result.error
            status.available_tools = sorted(result.available_tools)
            status.registered_tools = sorted(result.registered_tools)
            status.checked_at = checked_at
            if result.connected:
                status.state = "connected"
                status.session = result.session
            else:
                status.state = "failed"
                status.session = None

            self._mcp_status[name] = status

    def get_mcp_status_snapshot(self) -> list[dict[str, Any]]:
        """Return MCP status for all configured servers, sorted by name."""
        if not self._mcp_status and self._mcp_servers:
            self._seed_mcp_status()
        return [
            {
                "name": status.name,
                "state": status.state,
                "transport": status.transport,
                "registered_tools": list(status.registered_tools),
                "available_tools": list(status.available_tools),
                "error": status.error,
                "checked_at": status.checked_at,
            }
            for status in sorted(self._mcp_status.values(), key=lambda item: item.name)
        ]

    async def refresh_mcp_status(self, reconnect: bool = False) -> list[dict[str, Any]]:
        """Refresh MCP connection health, optionally forcing reconnect for all servers."""
        await self._connect_mcp(force_refresh=reconnect)
        return self.get_mcp_status_snapshot()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        extra_read = [BUILTIN_SKILLS_DIR] if allowed_dir else None
        self.tools.register(
            ReadFileTool(
                workspace=self.workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read
            )
        )
        for cls in (WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        if self.exec_config.enable:
            self.tools.register(
                ExecTool(
                    working_dir=str(self.workspace),
                    timeout=self.exec_config.timeout,
                    restrict_to_workspace=self.restrict_to_workspace,
                    path_append=self.exec_config.path_append,
                )
            )
        self.tools.register(WebSearchTool(config=self.web_search_config, proxy=self.web_proxy))
        self.tools.register(WebFetchTool(proxy=self.web_proxy))
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    async def _connect_mcp(self, force_refresh: bool = False) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connecting or not self._mcp_servers:
            return

        async with self._mcp_lock:
            if self._mcp_connecting or not self._mcp_servers:
                return
            if self._mcp_connected and not force_refresh:
                return

            self._mcp_connecting = True
            from nanobot.agent.tools.mcp import connect_mcp_servers

            try:
                if force_refresh:
                    self._unregister_all_mcp_tools()
                    if self._mcp_stack:
                        try:
                            await self._mcp_stack.aclose()
                        except (RuntimeError, BaseExceptionGroup):
                            pass
                        self._mcp_stack = None

                if self._mcp_stack is None:
                    self._mcp_stack = AsyncExitStack()
                    await self._mcp_stack.__aenter__()

                results = await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
                self._apply_mcp_connect_results(results)
                # Mark initialized after one connect attempt to avoid reconnecting every message.
                self._mcp_connected = True
            except BaseException as e:
                logger.error("Failed to connect MCP servers (will retry on /mcp): {}", e)
                if self._mcp_stack:
                    try:
                        await self._mcp_stack.aclose()
                    except (RuntimeError, BaseExceptionGroup):
                        pass
                    self._mcp_stack = None
                self._unregister_all_mcp_tools()
                self._set_all_mcp_failed(f"{type(e).__name__}: {e}")
                self._mcp_connected = True
            finally:
                self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "spawn", "cron"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        from nanobot.utils.helpers import strip_think

        return strip_think(text) or None

    def _tool_hint(self, tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        workspace_str = str(self.workspace)

        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}

            val = None
            if isinstance(args, dict):
                # Iterate through all string values to find the first meaningful one
                for v in args.values():
                    if isinstance(v, str):
                        val = v
                        break

            if not isinstance(val, str):
                return tc.name

            if self.restrict_to_workspace:
                import os

                # If it looks like an absolute path, normalize it to resolve '..' and '.'
                if os.path.isabs(val):
                    val = os.path.normpath(val)
                # Replace workspace path with empty string to hide it
                if workspace_str in val:
                    val = val.replace(workspace_str, "").lstrip("\\/")

            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'

        return ", ".join(_fmt(tc) for tc in tool_calls)

    def _trim_history_for_budget(
        self,
        messages: list[dict],
        turn_start_index: int,
        iteration: int,
    ) -> list[dict]:
        """Thin wrapper: delegates to trim_history_for_budget helper."""
        return trim_history_for_budget(
            messages,
            turn_start_index,
            iteration,
            self.context_budget_tokens,
            Session._find_legal_start,
        )

    @classmethod
    def _flatten_memory_retrieval_content(cls, content: Any) -> str:
        """Convert message content into compact text for memory retrieval."""
        if isinstance(content, str):
            compact = " ".join(content.split())
            return compact[: cls._MEMORY_RETRIEVAL_MAX_CHARS]

        if not isinstance(content, list):
            return ""

        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif block.get("type") == "image_url":
                parts.append("[image]")

        compact = " ".join(" ".join(parts).split())
        return compact[: cls._MEMORY_RETRIEVAL_MAX_CHARS]

    @classmethod
    def _build_memory_retrieval_query(
        cls, history: list[dict[str, Any]], current_message: str
    ) -> str:
        """Build a retrieval query from recent conversational context plus the current turn."""
        lines: list[str] = []
        recent = [message for message in history if message.get("role") in {"user", "assistant"}][
            -cls._MEMORY_RETRIEVAL_HISTORY_LIMIT :
        ]

        for message in recent:
            text = cls._flatten_memory_retrieval_content(message.get("content"))
            if not text:
                continue
            lines.append(f"{str(message.get('role', 'user')).upper()}: {text}")

        current = " ".join((current_message or "").split())
        if current:
            lines.append(f"USER: {current[: cls._MEMORY_RETRIEVAL_MAX_CHARS]}")

        return "\n".join(lines)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        *,
        channel: str = "cli",
        chat_id: str = "direct",
        message_id: str | None = None,
        disabled_tools: set[str] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop.

        *on_stream*: called with each content delta during streaming.
        *on_stream_end(resuming)*: called when a streaming session finishes.
        ``resuming=True`` means tool calls follow (spinner should restart);
        ``resuming=False`` means this is the final response.
        """
        messages = initial_messages
        turn_start_index = len(initial_messages) - 1
        blocked_tools = {name for name in (disabled_tools or set()) if name}

        class _ScopedTools:
            """Filter tool definitions and gate disabled tools at execution."""

            def __init__(self, registry: ToolRegistry, blocked: set[str]):
                self._registry = registry
                self._blocked = blocked

            def get_definitions(self) -> list[dict[str, Any]]:
                tool_defs = self._registry.get_definitions()
                if not self._blocked:
                    return tool_defs
                return [
                    td
                    for td in tool_defs
                    if ((td.get("function") or {}).get("name") not in self._blocked)
                ]

            async def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
                if tool_name in self._blocked:
                    return f"Error: Tool '{tool_name}' is disabled in this context"
                return await self._registry.execute(tool_name, arguments)

        class _LoopHook(AgentHook):
            def __init__(
                self,
                loop: AgentLoop,
                turn_start: int,
                stream_cb: Callable[[str], Awaitable[None]] | None,
                stream_end_cb: Callable[..., Awaitable[None]] | None,
            ):
                self._loop = loop
                self._turn_start = turn_start
                self._raw_stream = stream_cb
                self._stream_end = stream_end_cb
                self._stream_buf = ""

            def wants_streaming(self) -> bool:
                return self._raw_stream is not None

            async def before_iteration(self, context: AgentHookContext) -> None:
                context.messages = self._loop._trim_history_for_budget(
                    context.messages,
                    self._turn_start,
                    context.iteration + 1,
                )

            async def before_execute_tools(self, context: AgentHookContext) -> None:
                if on_progress and context.response:
                    if not self.wants_streaming():
                        thought = self._loop._strip_think(context.response.content)
                        if thought:
                            await on_progress(thought)
                    tool_hint = self._loop._strip_think(self._loop._tool_hint(context.tool_calls))
                    if tool_hint:
                        await on_progress(tool_hint, tool_hint=True)

                for tool_call in context.tool_calls:
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])

                # Re-bind tool context right before execution so that
                # concurrent sessions don't clobber each other's routing.
                self._loop._set_tool_context(channel, chat_id, message_id)

            async def on_stream(self, context: AgentHookContext, delta: str) -> None:
                if not self._raw_stream:
                    return
                from nanobot.utils.helpers import strip_think

                prev_clean = strip_think(self._stream_buf)
                self._stream_buf += delta
                new_clean = strip_think(self._stream_buf)
                incremental = new_clean[len(prev_clean) :]
                if incremental:
                    await self._raw_stream(incremental)

            async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None:
                if self._raw_stream and self._stream_end:
                    await self._stream_end(resuming=resuming)
                self._stream_buf = ""

            async def after_iteration(self, context: AgentHookContext) -> None:
                self._loop._last_usage = dict(context.usage)

            def finalize_content(
                self,
                context: AgentHookContext,
                content: str | None,
            ) -> str | None:
                return self._loop._strip_think(content)

        result = await self.runner.run(
            AgentRunSpec(
                initial_messages=messages,
                tools=_ScopedTools(self.tools, blocked_tools),
                model=self.model,
                max_iterations=self.max_iterations,
                hook=_LoopHook(self, turn_start_index, on_stream, on_stream_end),
                concurrent_tools=True,
            )
        )
        self._last_usage = dict(result.usage)

        if result.stop_reason == "error":
            logger.error("LLM returned error: {}", (result.error or "")[:200])
        elif result.stop_reason == "max_iterations":
            logger.warning("Max iterations ({}) reached", self.max_iterations)

        return result.final_content, result.tools_used, result.messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                # Preserve real task cancellation so shutdown can complete cleanly.
                # Only ignore non-task CancelledError signals that may leak from integrations.
                if not self._running or asyncio.current_task().cancelling():
                    raise
                continue
            except Exception as e:
                logger.warning("Error consuming inbound message: {}, continuing...", e)
                continue

            raw = msg.content.strip()
            if self.commands.is_priority(raw):
                ctx = CommandContext(msg=msg, session=None, key=msg.session_key, raw=raw, loop=self)
                result = await self.commands.dispatch_priority(ctx)
                if result:
                    await self.bus.publish_outbound(result)
                continue
            task = asyncio.create_task(self._dispatch(msg))
            self._active_tasks.setdefault(msg.session_key, []).append(task)
            task.add_done_callback(
                lambda t, k=msg.session_key: (
                    self._active_tasks.get(k, []) and self._active_tasks[k].remove(t)
                    if t in self._active_tasks.get(k, [])
                    else None
                )
            )

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message: per-session serial, cross-session concurrent."""
        lock = self._session_locks.setdefault(msg.session_key, asyncio.Lock())
        gate = self._concurrency_gate or nullcontext()
        async with lock, gate:
            try:
                stream_callback: Callable[[str], Awaitable[None]] | None = None
                stream_end_callback: Callable[..., Awaitable[None]] | None = None
                if msg.metadata.get("_wants_stream") and should_allow_live_streaming(
                    self.channels_config
                ):

                    async def _stream_callback(delta: str) -> None:
                        await self.bus.publish_outbound(
                            OutboundMessage(
                                channel=msg.channel,
                                chat_id=msg.chat_id,
                                content=delta,
                                metadata={"_stream_delta": True},
                            )
                        )

                    async def _stream_end_callback(*, resuming: bool = False) -> None:
                        await self.bus.publish_outbound(
                            OutboundMessage(
                                channel=msg.channel,
                                chat_id=msg.chat_id,
                                content="",
                                metadata={"_stream_end": True, "_resuming": resuming},
                            )
                        )

                    stream_callback = _stream_callback
                    stream_end_callback = _stream_end_callback

                response = await self._process_message(
                    msg,
                    on_stream=stream_callback,
                    on_stream_end=stream_end_callback,
                )
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="",
                            metadata=msg.metadata or {},
                        )
                    )
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Sorry, I encountered an error.",
                    )
                )

    async def close_mcp(self) -> None:
        """Drain pending background archives, then close MCP connections."""
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
        self._unregister_all_mcp_tools()
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None
        self._mcp_connected = False
        for status in self._mcp_status.values():
            status.state = "uninitialized"
            status.session = None
            status.available_tools = []
            status.registered_tools = []

    def _schedule_background(
        self,
        coro: Awaitable[Any],
        *,
        label: str = "background task",
    ) -> None:
        """Schedule a coroutine as a tracked background task (drained on shutdown)."""
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)

        def _done(done: asyncio.Task) -> None:
            try:
                self._background_tasks.remove(done)
            except ValueError:
                pass

            try:
                exc = done.exception()
            except asyncio.CancelledError:
                return

            if exc is not None:
                logger.opt(exception=exc).error("{} failed", label)

        task.add_done_callback(_done)

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        disabled_tools: set[str] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (
                msg.chat_id.split(":", 1) if ":" in msg.chat_id else ("cli", msg.chat_id)
            )
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            await self.memory_consolidator.consolidate_session_if_needed(session)
            history = session.get_history(max_messages=0)
            retrieval_query = self._build_memory_retrieval_query(history, msg.content)
            await self.context.memory.load_prompt_memory(retrieval_query)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            current_role = "assistant" if msg.sender_id == "subagent" else "user"
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content,
                channel=channel,
                chat_id=chat_id,
                current_role=current_role,
            )
            final_content, _, all_msgs = await self._run_agent_loop(
                messages,
                channel=channel,
                chat_id=chat_id,
                message_id=msg.metadata.get("message_id"),
                disabled_tools=disabled_tools,
            )
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            self._schedule_background(
                self.memory_consolidator.consolidate_session_if_needed(session),
                label="system post-turn consolidation",
            )
            return OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=final_content or "Background task completed.",
            )

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        raw = msg.content.strip()
        ctx = CommandContext(msg=msg, session=session, key=key, raw=raw, loop=self)
        if result := await self.commands.dispatch(ctx):
            return result

        await self.memory_consolidator.consolidate_session_if_needed(session)
        history = session.get_history(max_messages=0)
        retrieval_query = self._build_memory_retrieval_query(history, msg.content)
        await self.context.memory.load_prompt_memory(retrieval_query)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            meta["_progress_kind"] = "tool_hint" if tool_hint else "reasoning"
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata=meta,
                )
            )

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages,
            on_progress=on_progress or _bus_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
            channel=msg.channel,
            chat_id=msg.chat_id,
            message_id=msg.metadata.get("message_id"),
            disabled_tools=disabled_tools,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)

        post_turn_messages: list[dict[str, object]] = []
        if final_content:
            post_turn_messages = [
                {"role": "user", "content": msg.content},
                {"role": "assistant", "content": final_content},
            ]

        self._schedule_background(
            self.memory_consolidator.process_post_turn_memory(key, post_turn_messages),
            label="post-turn memory",
        )

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)

        meta = dict(msg.metadata or {})
        if on_stream is not None:
            meta["_streamed"] = True
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=meta,
        )

    @staticmethod
    def _image_placeholder(block: dict[str, Any]) -> dict[str, str]:
        """Convert an inline image block into a compact text placeholder."""
        path = (block.get("_meta") or {}).get("path", "")
        return {"type": "text", "text": f"[image: {path}]" if path else "[image]"}

    def _sanitize_persisted_blocks(
        self,
        content: list[dict[str, Any]],
        *,
        truncate_text: bool = False,
        drop_runtime: bool = False,
    ) -> list[dict[str, Any]]:
        """Strip volatile multimodal payloads before writing session history."""
        filtered: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                filtered.append(block)
                continue

            if (
                drop_runtime
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
                and block["text"].startswith(ContextBuilder._RUNTIME_CONTEXT_TAG)
            ):
                continue

            if block.get("type") == "image_url" and block.get("image_url", {}).get(
                "url", ""
            ).startswith("data:image/"):
                filtered.append(self._image_placeholder(block))
                continue

            if block.get("type") == "text" and isinstance(block.get("text"), str):
                text = block["text"]
                if truncate_text and len(text) > self._TOOL_RESULT_MAX_CHARS:
                    text = text[: self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
                filtered.append({**block, "text": text})
                continue

            filtered.append(block)

        return filtered

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime

        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages — they poison session context
            if role == "tool":
                if isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
                    entry["content"] = content[: self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
                elif isinstance(content, list):
                    filtered = self._sanitize_persisted_blocks(content, truncate_text=True)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            elif role == "user":
                if isinstance(content, str) and content.startswith(
                    ContextBuilder._RUNTIME_CONTEXT_TAG
                ):
                    # Strip the runtime-context prefix, keep only the user text.
                    parts = content.split("\n\n", 1)
                    if len(parts) > 1 and parts[1].strip():
                        entry["content"] = parts[1]
                    else:
                        continue
                if isinstance(content, list):
                    filtered = self._sanitize_persisted_blocks(content, drop_runtime=True)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        disabled_tools: set[str] | None = None,
    ) -> OutboundMessage | None:
        """Process a message directly and return the outbound payload."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        return await self._process_message(
            msg,
            session_key=session_key,
            on_progress=on_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
            disabled_tools=disabled_tools,
        )

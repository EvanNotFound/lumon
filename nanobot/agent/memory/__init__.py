"""Memory system for persistent agent memory."""

from __future__ import annotations

import asyncio
import json
import weakref
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from nanobot.config.schema import MemoryConfig
from nanobot.utils.helpers import estimate_message_tokens, estimate_prompt_tokens_chain

from .local import LocalMemoryBackend
from .supermemory import SupermemoryMemoryBackend

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.session.manager import Session, SessionManager


_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "A paragraph summarizing key events/decisions/topics. "
                        "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search.",
                    },
                    "memory_update": {
                        "type": "string",
                        "description": "Full updated long-term memory as markdown. Include all existing "
                        "facts plus new ones. Return unchanged if nothing new.",
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]

_MEMORY_DECISION_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "memory_decision",
            "description": "Decide whether a completed exchange should be persisted immediately as durable memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "should_persist": {
                        "type": "boolean",
                        "description": "true when the exchange contains durable information worth persisting immediately; false for transient or low-value exchanges.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Short explanation of the decision.",
                    },
                },
                "required": ["should_persist"],
            },
        },
    }
]

_MEMORY_DECISION_SYSTEM_PROMPT = """You are a durable-memory gate for an assistant.

Call the memory_decision tool to decide whether the completed exchange should be persisted immediately.

Persist exchanges that contain durable information such as:
- stable user identity facts, aliases, handles, or preferences
- lasting communication or behavior rules
- recurring mappings or personalized instructions
- long-lived project context or relationships likely to matter later
- durable workflow facts that change how the assistant should operate in future runs
- corrections to stale assumptions that would otherwise cause repeated mistakes
- instruction or procedure updates that should influence future behavior

Do not persist exchanges that are mainly:
- one-off chatter or acknowledgements
- transient task details or temporary troubleshooting
- routine back-and-forth with no durable takeaway
- low-value wording noise that does not affect future behavior

Examples:
- Persist: "The old missing EMAIL_HEARTBEAT.md note is fixed; treat it as resolved."
- Persist: "Use this repo naming rule for future PR titles."
- Skip: "I reran the command and got a timeout once."
- Skip: "Thanks"""


def _ensure_text(value: Any) -> str:
    """Normalize tool-call payload values to text for file storage."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _normalize_save_memory_args(args: Any) -> dict[str, Any] | None:
    """Normalize provider tool-call arguments to the expected dict shape."""
    if isinstance(args, str):
        args = json.loads(args)
    if isinstance(args, list):
        return args[0] if args and isinstance(args[0], dict) else None
    return args if isinstance(args, dict) else None


_TOOL_CHOICE_ERROR_MARKERS = (
    "tool_choice",
    "toolchoice",
    "does not support",
    'should be ["none", "auto"]',
)


def _is_tool_choice_unsupported(content: str | None) -> bool:
    """Detect provider errors caused by forced tool_choice being unsupported."""
    text = (content or "").lower()
    return any(marker in text for marker in _TOOL_CHOICE_ERROR_MARKERS)


class MemoryStore:
    """Persistent memory with selectable backend (local files or Supermemory)."""

    _MAX_FAILURES_BEFORE_RAW_ARCHIVE = 3

    def __init__(self, workspace: Path, memory_config: MemoryConfig | None = None):
        self.workspace = workspace
        self.config = memory_config or MemoryConfig()
        if self.config.backend == "supermemory":
            self._backend = SupermemoryMemoryBackend(workspace, self.config)
        else:
            self._backend = LocalMemoryBackend(workspace)
        self._consecutive_failures = 0

    @property
    def backend(self) -> str:
        return self.config.backend

    @property
    def memory_file(self) -> Path:
        return self._backend.memory_file

    @property
    def history_file(self) -> Path:
        return self._backend.history_file

    def is_supermemory(self) -> bool:
        return self._backend.is_supermemory()

    def read_long_term(self) -> str:
        return self._backend.read_long_term()

    def write_long_term(self, content: str) -> None:
        self._backend.write_long_term(content)

    def append_history(self, entry: str) -> None:
        self._backend.append_history(entry)

    def get_memory_context(self) -> str:
        return self._backend.get_memory_context()

    async def load_prompt_memory(self, query: str | None = None) -> None:
        """Best-effort preload for prompt-time memory context."""
        await self._backend.load_prompt_memory(query)

    async def save_consolidation(self, history_entry: str, memory_update: str) -> bool:
        return await self._backend.save_consolidation(history_entry, memory_update)

    @staticmethod
    def _format_messages(messages: list[dict]) -> str:
        lines = []
        for message in messages:
            if not message.get("content"):
                continue
            tools = (
                f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
            )
            lines.append(
                f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
            )
        return "\n".join(lines)

    async def consolidate(
        self,
        messages: list[dict],
        provider: LLMProvider,
        model: str,
    ) -> bool:
        """Consolidate the provided message chunk into the configured backend."""
        if not messages:
            return True

        await self.load_prompt_memory()
        current_memory = self.read_long_term()
        prompt = f"""Process this conversation and call the save_memory tool with your consolidation.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{self._format_messages(messages)}"""

        chat_messages = [
            {
                "role": "system",
                "content": "You are a memory consolidation agent. Call the save_memory tool with your consolidation of the conversation.",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            forced = {"type": "function", "function": {"name": "save_memory"}}
            response = await provider.chat_with_retry(
                messages=chat_messages,
                tools=_SAVE_MEMORY_TOOL,
                model=model,
                tool_choice=forced,
            )

            if response.finish_reason == "error" and _is_tool_choice_unsupported(response.content):
                logger.warning("Forced tool_choice unsupported, retrying with auto")
                response = await provider.chat_with_retry(
                    messages=chat_messages,
                    tools=_SAVE_MEMORY_TOOL,
                    model=model,
                    tool_choice="auto",
                )

            if not response.has_tool_calls:
                logger.warning(
                    "Memory consolidation: LLM did not call save_memory "
                    "(finish_reason={}, content_len={}, content_preview={})",
                    response.finish_reason,
                    len(response.content or ""),
                    (response.content or "")[:200],
                )
                return await self._fail_or_raw_archive(messages)

            args = _normalize_save_memory_args(response.tool_calls[0].arguments)
            if args is None:
                logger.warning("Memory consolidation: unexpected save_memory arguments")
                return await self._fail_or_raw_archive(messages)

            if "history_entry" not in args or "memory_update" not in args:
                logger.warning("Memory consolidation: save_memory payload missing required fields")
                return await self._fail_or_raw_archive(messages)

            entry = args["history_entry"]
            update = args["memory_update"]

            if entry is None or update is None:
                logger.warning(
                    "Memory consolidation: save_memory payload contains null required fields"
                )
                return await self._fail_or_raw_archive(messages)

            entry = _ensure_text(entry).strip()
            if not entry:
                logger.warning("Memory consolidation: history_entry is empty after normalization")
                return await self._fail_or_raw_archive(messages)

            update = _ensure_text(update)
            if not await self.save_consolidation(entry, update):
                logger.warning(
                    "Memory consolidation: persistence failed for backend={}", self.backend
                )
                return await self._fail_or_raw_archive(messages)

            self._consecutive_failures = 0
            logger.info("Memory consolidation done for {} messages", len(messages))
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return await self._fail_or_raw_archive(messages)

    async def _fail_or_raw_archive(self, messages: list[dict]) -> bool:
        """Increment failure count; after threshold, raw-archive messages and return True."""
        self._consecutive_failures += 1
        if self._consecutive_failures < self._MAX_FAILURES_BEFORE_RAW_ARCHIVE:
            return False
        await self._raw_archive(messages)
        self._consecutive_failures = 0
        return True

    async def _raw_archive(self, messages: list[dict]) -> None:
        """Fallback: dump raw messages without LLM summarization."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"[{ts}] [RAW] {len(messages)} messages\n{self._format_messages(messages)}"
        await self._backend.raw_archive(entry)
        logger.warning("Memory consolidation degraded: raw-archived {} messages", len(messages))


class MemoryConsolidator:
    """Owns consolidation policy, locking, and session offset updates."""

    _MAX_CONSOLIDATION_ROUNDS = 5
    _SAFETY_BUFFER = 1024  # extra headroom for tokenizer estimation drift

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        sessions: SessionManager,
        context_window_tokens: int,
        build_messages: Callable[..., list[dict[str, Any]]],
        get_tool_definitions: Callable[[], list[dict[str, Any]]],
        max_completion_tokens: int = 4096,
        memory_config: MemoryConfig | None = None,
    ):
        self.store = MemoryStore(workspace, memory_config=memory_config)
        self.provider = provider
        self.model = model
        self.sessions = sessions
        self.context_window_tokens = context_window_tokens
        self.max_completion_tokens = max_completion_tokens
        self._build_messages = build_messages
        self._get_tool_definitions = get_tool_definitions
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """Return the shared consolidation lock for one session."""
        return self._locks.setdefault(session_key, asyncio.Lock())

    async def consolidate_messages(self, messages: list[dict[str, object]]) -> bool:
        """Archive a selected message chunk into persistent memory."""
        return await self.store.consolidate(messages, self.provider, self.model)

    def pick_consolidation_boundary(
        self,
        session: Session,
        tokens_to_remove: int,
    ) -> tuple[int, int] | None:
        """Pick a user-turn boundary that removes enough old prompt tokens."""
        start = session.last_consolidated
        if start >= len(session.messages) or tokens_to_remove <= 0:
            return None

        removed_tokens = 0
        last_boundary: tuple[int, int] | None = None
        for idx in range(start, len(session.messages)):
            message = session.messages[idx]
            if idx > start and message.get("role") == "user":
                last_boundary = (idx, removed_tokens)
                if removed_tokens >= tokens_to_remove:
                    return last_boundary
            removed_tokens += estimate_message_tokens(message)

        return last_boundary

    def estimate_session_prompt_tokens(self, session: Session) -> tuple[int, str]:
        """Estimate current prompt size for the normal session history view."""
        history = session.get_history(max_messages=0)
        channel, chat_id = session.key.split(":", 1) if ":" in session.key else (None, None)
        probe_messages = self._build_messages(
            history=history,
            current_message="[token-probe]",
            channel=channel,
            chat_id=chat_id,
        )
        return estimate_prompt_tokens_chain(
            self.provider,
            self.model,
            probe_messages,
            self._get_tool_definitions(),
        )

    async def remember_messages(self, messages: list[dict[str, object]]) -> bool:
        """Remember messages with guaranteed persistence (retries until raw-dump fallback)."""
        if not messages:
            return True
        max_attempts = self.store._MAX_FAILURES_BEFORE_RAW_ARCHIVE
        for attempt in range(max_attempts):
            if await self.consolidate_messages(messages):
                logger.info(
                    "Memory persistence: success on attempt {}/{} for {} messages",
                    attempt + 1,
                    max_attempts,
                    len(messages),
                )
                return True
        logger.warning(
            "Memory persistence: consolidated via fallback after {} attempts for {} messages",
            max_attempts,
            len(messages),
        )
        return True

    async def should_remember_turn(self, messages: list[dict[str, object]]) -> bool:
        """Use the model to judge whether a completed exchange deserves immediate persistence."""
        if not messages:
            return False

        prompt = f"""Review this completed exchange and call the memory_decision tool.

## Exchange
{self.store._format_messages(messages)}"""

        try:
            forced = {"type": "function", "function": {"name": "memory_decision"}}
            response = await self.provider.chat_with_retry(
                messages=[
                    {"role": "system", "content": _MEMORY_DECISION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                tools=_MEMORY_DECISION_TOOL,
                model=self.model,
                tool_choice=forced,
                max_tokens=256,
                temperature=0.0,
            )

            if response.finish_reason == "error" and _is_tool_choice_unsupported(response.content):
                logger.warning(
                    "Forced tool_choice unsupported for memory_decision, retrying with auto"
                )
                response = await self.provider.chat_with_retry(
                    messages=[
                        {"role": "system", "content": _MEMORY_DECISION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    tools=_MEMORY_DECISION_TOOL,
                    model=self.model,
                    tool_choice="auto",
                    max_tokens=256,
                    temperature=0.0,
                )

            if not response.has_tool_calls:
                logger.warning(
                    "Memory decision: LLM did not call memory_decision (finish_reason={}, content_preview={})",
                    response.finish_reason,
                    (response.content or "")[:200],
                )
                return False

            args = _normalize_save_memory_args(response.tool_calls[0].arguments)
            if args is None or "should_persist" not in args:
                logger.warning("Memory decision: unexpected memory_decision arguments")
                return False

            should_persist = bool(args.get("should_persist"))
            logger.info(
                "Memory decision: should_persist={}, reason={}",
                should_persist,
                _ensure_text(args.get("reason", ""))[:200],
            )
            return should_persist
        except Exception:
            logger.exception("Memory decision failed")
            return False

    async def process_post_turn_memory(
        self,
        session_key: str,
        messages: list[dict[str, object]],
    ) -> None:
        """Remember a completed turn and then consolidate the session under one lock."""
        lock = self.get_lock(session_key)
        async with lock:
            if messages:
                should_persist = await self.should_remember_turn(messages)
                if should_persist:
                    await self.remember_messages(messages)
                else:
                    logger.debug(
                        "Memory post-turn: skipped immediate persistence for session {}",
                        session_key,
                    )
            session = self.sessions.get_or_create(session_key)
            await self._consolidate_session_if_needed_locked(session)

    async def consolidate_session_if_needed(self, session: Session) -> None:
        """Loop: archive old messages until prompt fits within safe budget.

        The budget reserves space for completion tokens and a safety buffer
        so the LLM request never exceeds the context window.
        """
        if not session.messages or self.context_window_tokens <= 0:
            return

        lock = self.get_lock(session.key)
        async with lock:
            await self._consolidate_session_if_needed_locked(session)

    async def _consolidate_session_if_needed_locked(self, session: Session) -> None:
        """Run token-based session consolidation while assuming the session lock is held."""
        budget = self.context_window_tokens - self.max_completion_tokens - self._SAFETY_BUFFER
        target = budget // 2
        estimated, source = self.estimate_session_prompt_tokens(session)
        if estimated <= 0:
            return
        if estimated < budget:
            logger.debug(
                "Token consolidation idle {}: {}/{} via {}",
                session.key,
                estimated,
                self.context_window_tokens,
                source,
            )
            return

        for round_num in range(self._MAX_CONSOLIDATION_ROUNDS):
            if estimated <= target:
                return

            boundary = self.pick_consolidation_boundary(session, max(1, estimated - target))
            if boundary is None:
                logger.debug(
                    "Token consolidation: no safe boundary for {} (round {})",
                    session.key,
                    round_num,
                )
                return

            end_idx = boundary[0]
            chunk = session.messages[session.last_consolidated : end_idx]
            if not chunk:
                return

            logger.info(
                "Token consolidation round {} for {}: {}/{} via {}, chunk={} msgs",
                round_num,
                session.key,
                estimated,
                self.context_window_tokens,
                source,
                len(chunk),
            )
            if not await self.consolidate_messages(chunk):
                return
            session.last_consolidated = end_idx
            self.sessions.save(session)

            estimated, source = self.estimate_session_prompt_tokens(session)
            if estimated <= 0:
                return


__all__ = [
    "MemoryStore",
    "MemoryConsolidator",
    "_SAVE_MEMORY_TOOL",
    "_ensure_text",
    "_normalize_save_memory_args",
    "_is_tool_choice_unsupported",
    "estimate_message_tokens",
]

"""Memory system for persistent agent memory."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import weakref
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from nanobot.config.schema import MemoryConfig
from nanobot.utils.helpers import ensure_dir, estimate_message_tokens, estimate_prompt_tokens_chain

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
    return any(m in text for m in _TOOL_CHOICE_ERROR_MARKERS)


class MemoryStore:
    """Persistent memory with selectable backend (local files or Supermemory)."""

    _MAX_FAILURES_BEFORE_RAW_ARCHIVE = 3

    def __init__(self, workspace: Path, memory_config: MemoryConfig | None = None):
        self.workspace = workspace
        self.config = memory_config or MemoryConfig()
        self.memory_dir = workspace / "memory"
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"
        self._consecutive_failures = 0
        self._remote_long_term = ""
        self._snapshot_id: str | None = None
        self._snapshot_hydrated = False
        self._retrieved_context = ""

    @property
    def backend(self) -> str:
        return self.config.backend

    def is_supermemory(self) -> bool:
        return self.backend == "supermemory"

    def read_long_term(self) -> str:
        if self.is_supermemory():
            return self._remote_long_term
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        if self.is_supermemory():
            self._remote_long_term = content
            return
        ensure_dir(self.memory_dir)
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        if self.is_supermemory():
            return
        ensure_dir(self.memory_dir)
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        long_term = self.read_long_term()
        parts: list[str] = []
        if long_term:
            parts.append(f"## Long-term Memory\n{long_term}")
        if self._retrieved_context:
            parts.append(f"## Retrieved Memory\n{self._retrieved_context}")
        return "\n\n".join(parts)

    async def prepare_prompt_memory(self, query: str | None = None) -> None:
        """Best-effort preload for prompt-time memory context."""
        self._retrieved_context = ""
        await self._hydrate_snapshot_from_supermemory()
        if self.is_supermemory() and query:
            self._retrieved_context = await self._build_retrieved_context(query)

    def _container_tag(self) -> str:
        tag = self.config.supermemory.container_tag.strip()
        if tag:
            return tag
        workspace_key = str(self.workspace.expanduser().resolve())
        digest = hashlib.sha1(workspace_key.encode("utf-8")).hexdigest()[:16]
        return f"nanobot-workspace-{digest}"

    def _build_supermemory_client(self) -> Any | None:
        api_key = self.config.supermemory.api_key.strip()
        if not api_key:
            logger.warning("Supermemory backend configured without api_key")
            return None

        try:
            from supermemory import AsyncSupermemory  # type: ignore[import-not-found]
        except ImportError:
            logger.error(
                "Supermemory package is missing from the nanobot runtime. "
                "Reinstall or upgrade nanobot so core dependencies are present."
            )
            return None

        base_url = self.config.supermemory.base_url.strip().rstrip("/")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url

        try:
            return AsyncSupermemory(**kwargs)
        except TypeError:
            # Older SDKs may not accept base_url.
            kwargs.pop("base_url", None)
            return AsyncSupermemory(**kwargs)

    @staticmethod
    async def _await_if_needed(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    @staticmethod
    def _object_to_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        for method_name in ("model_dump", "dict", "to_dict"):
            method = getattr(value, method_name, None)
            if callable(method):
                try:
                    dumped = method()
                except Exception:
                    continue
                if isinstance(dumped, dict):
                    return dumped
        data = getattr(value, "__dict__", None)
        if isinstance(data, dict):
            return data
        return {}

    @classmethod
    def _extract_memories(cls, response: Any) -> list[dict[str, Any]]:
        payload = cls._object_to_dict(response)
        for key in ("memories", "documents", "results", "items"):
            memories = payload.get(key)
            if isinstance(memories, list):
                return [cls._object_to_dict(item) for item in memories]
        if isinstance(response, list):
            return [cls._object_to_dict(item) for item in response]
        return []

    @classmethod
    def _extract_item_text(cls, item: dict[str, Any]) -> str:
        for key in ("content", "text", "memory", "summary"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        nested = item.get("document")
        if isinstance(nested, dict):
            value = nested.get("content")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    async def _with_supermemory_client(
        self,
        operation_name: str,
        operation: Callable[[Any], Awaitable[Any] | Any],
    ) -> Any | None:
        client = self._build_supermemory_client()
        if client is None:
            return None

        try:
            if callable(getattr(client, "__aenter__", None)) and callable(
                getattr(client, "__aexit__", None)
            ):
                async with client as managed_client:
                    return await self._await_if_needed(operation(managed_client))

            return await self._await_if_needed(operation(client))
        except Exception:
            logger.exception("Supermemory SDK call failed: {}", operation_name)
            return None
        finally:
            close = getattr(client, "aclose", None)
            if callable(close):
                try:
                    await self._await_if_needed(close())
                except Exception:
                    logger.debug("Ignoring supermemory client close error")

    async def _supermemory_list_memories(self, *, limit: int = 50) -> list[dict[str, Any]] | None:
        tag = self._container_tag()

        async def _run(client: Any) -> Any:
            documents = getattr(client, "documents", None)
            list_fn = getattr(documents, "list", None)
            if not callable(list_fn):
                logger.warning("Supermemory SDK does not expose documents.list")
                return None

            try:
                return await self._await_if_needed(
                    list_fn(
                        container_tags=[tag],
                        include_content=True,
                        limit=limit,
                        sort="updatedAt",
                        order="desc",
                    )
                )
            except TypeError:
                return await self._await_if_needed(
                    list_fn(
                        container_tags=[tag],
                        limit=limit,
                        sort="updatedAt",
                        order="desc",
                    )
                )

        result = await self._with_supermemory_client("documents.list", _run)
        if result is None:
            return None
        return self._extract_memories(result)

    async def _supermemory_get_memory(self, memory_id: str) -> dict[str, Any] | None:
        async def _run(client: Any) -> Any:
            documents = getattr(client, "documents", None)
            get_fn = getattr(documents, "get", None)
            if not callable(get_fn):
                logger.warning("Supermemory SDK does not expose documents.get")
                return None

            return await self._await_if_needed(get_fn(memory_id))

        result = await self._with_supermemory_client("documents.get", _run)
        if result is None:
            return None
        return self._object_to_dict(result)

    async def _supermemory_add_memory(
        self,
        *,
        content: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        tag = self._container_tag()

        async def _run(client: Any) -> Any:
            add_fn = getattr(client, "add", None)
            if not callable(add_fn):
                logger.warning("Supermemory SDK does not expose add")
                return None

            try:
                return await self._await_if_needed(
                    add_fn(content=content, container_tag=tag, metadata=metadata)
                )
            except TypeError:
                try:
                    return await self._await_if_needed(
                        add_fn(content=content, container_tags=[tag], metadata=metadata)
                    )
                except TypeError:
                    return await self._await_if_needed(add_fn(content=content, container_tag=tag))

        result = await self._with_supermemory_client("add", _run)
        if result is None:
            return None
        return self._object_to_dict(result)

    async def _supermemory_update_memory(
        self,
        memory_id: str,
        *,
        content: str,
        metadata: dict[str, Any],
    ) -> bool:
        tag = self._container_tag()

        async def _run(client: Any) -> Any:
            documents = getattr(client, "documents", None)
            update_fn = getattr(documents, "update", None)
            if not callable(update_fn):
                logger.warning("Supermemory SDK does not expose documents.update")
                return None

            try:
                return await self._await_if_needed(
                    update_fn(memory_id, content=content, container_tag=tag, metadata=metadata)
                )
            except TypeError:
                try:
                    return await self._await_if_needed(
                        update_fn(
                            memory_id, content=content, container_tags=[tag], metadata=metadata
                        )
                    )
                except TypeError:
                    return await self._await_if_needed(update_fn(memory_id, content=content))

        result = await self._with_supermemory_client("documents.update", _run)
        return result is not None

    async def _supermemory_search_memories(
        self, query: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        tag = self._container_tag()

        async def _run(client: Any) -> Any:
            search = getattr(client, "search", None)
            search_memories = getattr(search, "memories", None)
            if not callable(search_memories):
                logger.warning("Supermemory SDK does not expose search.memories")
                return None

            try:
                return await self._await_if_needed(
                    search_memories(
                        q=query,
                        container_tag=tag,
                        limit=limit,
                        rewrite_query=True,
                    )
                )
            except TypeError:
                try:
                    return await self._await_if_needed(
                        search_memories(
                            q=query,
                            container_tag=tag,
                            limit=limit,
                        )
                    )
                except TypeError:
                    return await self._await_if_needed(
                        search_memories(
                            q=query,
                            container_tags=[tag],
                            limit=limit,
                        )
                    )

        result = await self._with_supermemory_client("search.memories", _run)
        if result is None:
            return []
        return self._extract_memories(result)

    async def _build_retrieved_context(self, query: str) -> str:
        matches = await self._supermemory_search_memories(query, limit=5)
        lines: list[str] = []
        for idx, item in enumerate(matches, start=1):
            text = self._extract_item_text(item)
            if not text:
                continue
            compact = " ".join(text.split())
            if len(compact) > 300:
                compact = compact[:300].rstrip() + "..."
            lines.append(f"{idx}. {compact}")
        return "\n".join(lines)

    async def _hydrate_snapshot_from_supermemory(self) -> None:
        if not self.is_supermemory() or self._snapshot_hydrated:
            return

        self._snapshot_hydrated = True
        if self.read_long_term():
            return

        if self._snapshot_id:
            snapshot = await self._supermemory_get_memory(self._snapshot_id)
            if snapshot is not None:
                content = snapshot.get("content")
                if isinstance(content, str) and content.strip():
                    self.write_long_term(content)
                    return

        memories = await self._supermemory_list_memories(limit=50)
        if memories is None:
            return

        for memory in memories:
            metadata = memory.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("kind") != "snapshot":
                continue

            content = memory.get("content")
            if isinstance(content, str) and content.strip():
                self.write_long_term(content)
            doc_id = memory.get("id")
            if isinstance(doc_id, str) and doc_id:
                self._snapshot_id = doc_id
            return

    async def _supermemory_add_history(self, entry: str, *, raw: bool = False) -> bool:
        payload = {
            "kind": "history",
            "raw": raw,
            "source": "nanobot",
            "workspace": self._container_tag(),
        }
        result = await self._supermemory_add_memory(content=entry, metadata=payload)
        return result is not None

    async def _supermemory_upsert_snapshot(self, content: str) -> bool:
        metadata = {
            "kind": "snapshot",
            "source": "nanobot",
            "workspace": self._container_tag(),
        }
        if self._snapshot_id:
            if await self._supermemory_update_memory(
                self._snapshot_id,
                content=content,
                metadata=metadata,
            ):
                return True
            logger.warning("Supermemory snapshot update failed; retrying as create")

        created = await self._supermemory_add_memory(content=content, metadata=metadata)
        if created is None:
            return False

        doc_id = created.get("id") if isinstance(created, dict) else None
        if isinstance(doc_id, str) and doc_id:
            self._snapshot_id = doc_id
        return True

    async def persist_consolidation(self, history_entry: str, memory_update: str) -> bool:
        current_memory = self.read_long_term()
        if not self.is_supermemory():
            self.append_history(history_entry)
            if memory_update != current_memory:
                self.write_long_term(memory_update)
            return True

        if memory_update != current_memory:
            if not await self._supermemory_upsert_snapshot(memory_update):
                return False
            self.write_long_term(memory_update)
        if not await self._supermemory_add_history(history_entry):
            return False
        return True

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

        await self._hydrate_snapshot_from_supermemory()
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
            if not await self.persist_consolidation(entry, update):
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
        if self.is_supermemory():
            if not await self._supermemory_add_history(entry, raw=True):
                logger.warning(
                    "Memory consolidation degraded: failed raw archive for {} messages",
                    len(messages),
                )
                return
        else:
            self.append_history(entry)
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

    async def archive_messages(self, messages: list[dict[str, object]]) -> bool:
        """Archive messages with guaranteed persistence (retries until raw-dump fallback)."""
        if not messages:
            return True
        for _ in range(self.store._MAX_FAILURES_BEFORE_RAW_ARCHIVE):
            if await self.consolidate_messages(messages):
                return True
        return True

    async def maybe_consolidate_by_tokens(self, session: Session) -> None:
        """Loop: archive old messages until prompt fits within safe budget.

        The budget reserves space for completion tokens and a safety buffer
        so the LLM request never exceeds the context window.
        """
        if not session.messages or self.context_window_tokens <= 0:
            return

        lock = self.get_lock(session.key)
        async with lock:
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

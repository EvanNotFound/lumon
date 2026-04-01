"""Supermemory-backed memory implementation."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from nanobot.config.schema import MemoryConfig


class SupermemoryMemoryBackend:
    """Stores memory in Supermemory and builds retrieved prompt context."""

    def __init__(self, workspace: Path, config: MemoryConfig):
        self.workspace = workspace
        self.config = config
        self.memory_dir = workspace / "memory"
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"
        self._remote_long_term = ""
        self._snapshot_id: str | None = None
        self._snapshot_hydrated = False
        self._retrieved_context = ""

    def is_supermemory(self) -> bool:
        return True

    def read_long_term(self) -> str:
        return self._remote_long_term

    def write_long_term(self, content: str) -> None:
        self._remote_long_term = content

    def append_history(self, entry: str) -> None:
        del entry

    def get_memory_context(self) -> str:
        parts: list[str] = []
        if self._remote_long_term:
            parts.append(f"## Long-term Memory\n{self._remote_long_term}")
        if self._retrieved_context:
            parts.append(f"## Retrieved Memory\n{self._retrieved_context}")
        return "\n\n".join(parts)

    async def load_prompt_memory(self, query: str | None = None) -> None:
        self._retrieved_context = ""
        await self._hydrate_snapshot_from_supermemory()
        if query:
            self._retrieved_context = await self._build_retrieved_context(query)

    def _container_tag(self) -> str:
        tag = self.config.supermemory.container_tag.strip()
        if tag:
            return tag
        workspace_key = str(self.workspace.expanduser().resolve())
        digest = hashlib.sha1(workspace_key.encode("utf-8")).hexdigest()[:16]
        return f"nanobot-workspace-{digest}"

    def _snapshot_custom_id(self) -> str:
        digest = hashlib.sha1(self._container_tag().encode("utf-8")).hexdigest()[:20]
        return f"nanobot-snapshot-{digest}"

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

            return await self._await_if_needed(
                list_fn(
                    container_tags=[tag],
                    include_content=True,
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
        custom_id: str | None = None,
    ) -> dict[str, Any] | None:
        tag = self._container_tag()

        async def _run(client: Any) -> Any:
            add_fn = getattr(client, "add", None)
            if not callable(add_fn):
                logger.warning("Supermemory SDK does not expose add")
                return None

            kwargs: dict[str, Any] = {
                "content": content,
                "container_tag": tag,
                "metadata": metadata,
            }
            if custom_id:
                kwargs["custom_id"] = custom_id
            return await self._await_if_needed(add_fn(**kwargs))

        result = await self._with_supermemory_client("add", _run)
        if result is None:
            return None
        return self._object_to_dict(result)

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

            return await self._await_if_needed(
                search_memories(
                    q=query,
                    container_tag=tag,
                    limit=limit,
                    rewrite_query=True,
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
            metadata = item.get("metadata")
            if isinstance(metadata, dict) and metadata.get("kind") == "snapshot":
                continue
            text = self._extract_item_text(item)
            if not text:
                continue
            compact = " ".join(text.split())
            if len(compact) > 300:
                compact = compact[:300].rstrip() + "..."
            lines.append(f"{idx}. {compact}")
        return "\n".join(lines)

    async def _hydrate_snapshot_from_supermemory(self) -> None:
        if self._snapshot_hydrated:
            return

        self._snapshot_hydrated = True
        if self._remote_long_term:
            return

        if self._snapshot_id:
            snapshot = await self._supermemory_get_memory(self._snapshot_id)
            if snapshot is not None:
                content = snapshot.get("content")
                if isinstance(content, str) and content.strip():
                    self._remote_long_term = content
                    return

        memories = await self._supermemory_list_memories(limit=50)
        if memories is None:
            return

        snapshot_custom_id = self._snapshot_custom_id()
        fallback_snapshot: dict[str, Any] | None = None

        for memory in memories:
            metadata = memory.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("kind") != "snapshot":
                continue

            memory_custom_id = memory.get("customId") or memory.get("custom_id")
            if (
                memory_custom_id == snapshot_custom_id
                or metadata.get("snapshot_key") == snapshot_custom_id
            ):
                fallback_snapshot = memory
                break

            if fallback_snapshot is None:
                fallback_snapshot = memory

        if fallback_snapshot is None:
            return

        content = fallback_snapshot.get("content")
        if isinstance(content, str) and content.strip():
            self._remote_long_term = content
        doc_id = fallback_snapshot.get("id")
        if isinstance(doc_id, str) and doc_id:
            self._snapshot_id = doc_id

    async def _supermemory_add_history(self, entry: str, *, raw: bool = False) -> bool:
        payload = {
            "kind": "history",
            "raw": raw,
            "source": "nanobot",
            "workspace": self._container_tag(),
        }
        result = await self._supermemory_add_memory(content=entry, metadata=payload)
        return result is not None

    async def save_raw_turn(self, entry: str) -> bool:
        payload = {
            "kind": "raw_turn",
            "source": "nanobot",
            "workspace": self._container_tag(),
        }
        result = await self._supermemory_add_memory(content=entry, metadata=payload)
        return result is not None

    async def _supermemory_upsert_snapshot(self, content: str) -> bool:
        snapshot_custom_id = self._snapshot_custom_id()
        metadata = {
            "kind": "snapshot",
            "source": "nanobot",
            "workspace": self._container_tag(),
            "snapshot_key": snapshot_custom_id,
        }
        created = await self._supermemory_add_memory(
            content=content,
            metadata=metadata,
        )
        if created is None:
            return False

        doc_id = created.get("id") if isinstance(created, dict) else None
        if isinstance(doc_id, str) and doc_id:
            self._snapshot_id = doc_id
        logger.debug(
            "Supermemory snapshot appended: id={}, workspace={}",
            self._snapshot_id or "?",
            self._container_tag(),
        )
        return True

    async def save_consolidation(self, history_entry: str, memory_update: str) -> bool:
        current_memory = self.read_long_term()
        if memory_update != current_memory:
            if not await self._supermemory_upsert_snapshot(memory_update):
                return False
            self._remote_long_term = memory_update
        if not await self._supermemory_add_history(history_entry):
            return False
        logger.debug(
            "Supermemory consolidation persisted for workspace={} (snapshot_changed={})",
            self._container_tag(),
            memory_update != current_memory,
        )
        return True

    async def raw_archive(self, entry: str) -> None:
        if not await self._supermemory_add_history(entry, raw=True):
            logger.warning(
                "Memory consolidation degraded: failed raw archive for workspace={}",
                self._container_tag(),
            )

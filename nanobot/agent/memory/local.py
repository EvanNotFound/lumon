"""Local markdown-backed memory implementation."""

from __future__ import annotations

from pathlib import Path

from nanobot.utils.helpers import ensure_dir


class LocalMemoryBackend:
    """Stores memory in workspace markdown files."""

    def __init__(self, workspace: Path):
        self.memory_dir = workspace / "memory"
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"

    def is_supermemory(self) -> bool:
        return False

    def read_long_term(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        ensure_dir(self.memory_dir)
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        ensure_dir(self.memory_dir)
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    async def prepare_prompt_memory(self, query: str | None = None) -> None:
        del query

    async def persist_consolidation(self, history_entry: str, memory_update: str) -> bool:
        current_memory = self.read_long_term()
        self.append_history(history_entry)
        if memory_update != current_memory:
            self.write_long_term(memory_update)
        return True

    async def raw_archive(self, entry: str) -> None:
        self.append_history(entry)

## Context

nanobot already supports `reasoning_effort` as a provider generation setting, and multiple providers already translate that value into provider-specific thinking controls. Today that setting only comes from config defaults, which makes it static and process-wide. The requested change is cross-cutting because it touches shared slash-command handling, Telegram command discovery, session persistence, agent execution, and user-visible status/help output.

Telegram is the motivating channel, but command execution already flows through the shared command router. The clean design is therefore to keep Telegram-specific work limited to command registration and command-menu exposure, while implementing the behavior in the shared command layer so the runtime model remains coherent.

## Goals / Non-Goals

**Goals:**
- Let a user inspect and change the model thinking level for the current chat at runtime.
- Keep the override scoped to the current chat or Telegram topic session instead of mutating global bot state.
- Persist the override in existing session storage so it survives `/new` and process restarts.
- Apply the effective thinking level consistently to main chat runs and subagents spawned from that chat.
- Make the active setting visible in `/thinking`, `/status`, `/help`, and Telegram's command menu.

**Non-Goals:**
- Introduce a generic chat settings framework for every possible runtime option.
- Change the configured global default in `config.json` from chat commands.
- Add new provider-side thinking values beyond the existing `low`, `medium`, `high`, or default fallback behavior.
- Change unrelated background memory/consolidation flows unless they already inherit normal chat-run settings.

## Decisions

### 1. Store the override in `Session.metadata["reasoning_effort"]`

The per-chat override will live directly in session metadata as a single flat key, instead of mutating `provider.generation` or introducing a nested runtime-settings subsystem.

Rationale:
- Session metadata already persists with the chat session on disk.
- Session keys already capture Telegram private chats and forum topics correctly.
- A flat key is the smallest design that fits the current scope.

Alternatives considered:
- Mutate `provider.generation.reasoning_effort`. Rejected because it creates process-global state and leaks one chat's preference into other chats.
- Create a new runtime settings registry. Rejected because it adds abstraction without solving a current complexity problem.

### 2. Treat `/thinking off` as “clear the override”

The command will support `/thinking`, `/thinking low`, `/thinking medium`, `/thinking high`, and `/thinking off`. The `off` form will remove the session override so the chat falls back to the configured default, including the case where the default is unset.

Rationale:
- Providers already expect `reasoning_effort` values of `low`, `medium`, `high`, or `None`.
- Clearing the override keeps stored state aligned with the actual runtime model.
- It distinguishes “this chat is overriding” from “this chat is using the default”.

Alternatives considered:
- Store the literal string `off`. Rejected because it is not a provider input and complicates resolution logic.

### 3. Resolve an effective thinking level per run

Agent execution will compute an effective `reasoning_effort` for the current session by preferring the session override and otherwise using the configured provider generation default. The resolved value should be passed explicitly into agent runs rather than relying on ambient global state.

Rationale:
- Explicit run-time resolution keeps behavior deterministic and local to a session.
- It avoids hidden coupling between chat commands and provider defaults.
- It gives subagent launches a clear value to inherit from the originating chat session.

Alternatives considered:
- Continue relying only on provider defaults. Rejected because it cannot represent chat-scoped overrides.

### 4. Keep command semantics shared, but Telegram discovery explicit

The actual `/thinking` behavior should be implemented in shared built-in commands. Telegram-specific work should only add the command to the channel's command menu and forward it the same way other slash commands are forwarded.

Rationale:
- Command routing is already centralized.
- Telegram should not become the only place where command semantics exist.
- This preserves the option to expose the same command in other channels later without redesigning core behavior.

Alternatives considered:
- Handle `/thinking` entirely inside `telegram.py`. Rejected because it would split command semantics across layers and bypass shared help/status behavior.

### 5. Surface the active state in status and help output

`/thinking` should report the effective level and whether it comes from a chat override or the default. `/status` should include the same information so the mode is not hidden state. `/help` and Telegram's command menu should advertise the command.

Rationale:
- Hidden per-chat state is hard to reason about in long-running conversations.
- A visible status line reduces confusion after `/new` because the override intentionally persists.

Alternatives considered:
- Only acknowledge state changes at set time. Rejected because users can later forget what mode a chat is in.

## Risks / Trade-offs

- [A persistent chat override may surprise users after `/new`] -> Make `/thinking` and `/status` show the active source clearly and document that `/new` resets history, not chat preferences.
- [Subagents could diverge from the parent chat's mode] -> Pass the resolved thinking level explicitly when spawning or running subagent work for that chat.
- [Future chat-level controls could accumulate ad hoc metadata keys] -> Keep this change minimal now and revisit a broader settings structure only when multiple controls justify it.
- [Providers differ in how they interpret thinking effort] -> Restrict command values to the existing normalized set and continue using the current provider adapters.

## Migration Plan

1. Add the new shared `/thinking` command and Telegram command-menu entry.
2. Persist the chat override in session metadata and resolve the effective value in the agent execution path.
3. Update status/help surfaces to show the active thinking level and source.
4. Add tests for command handling, persistence across `/new` and reload, Telegram forwarding/menu exposure, and effective per-run propagation.
5. Roll back by removing the command and ignoring the stored metadata key; existing sessions can safely retain unused metadata.

## Open Questions

- Should non-Telegram channels that already use the shared slash-command layer expose `/thinking` immediately, or should this change keep formal discovery/menu updates Telegram-only for now?
- Should `/status` show the raw effective provider value only, or a more user-facing phrase such as “default” versus `low`/`medium`/`high`?

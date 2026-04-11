## Why

Nanobot already supports provider-level `reasoning_effort`, but chat users cannot adjust it during an active conversation. Telegram users need a simple way to change the model's thinking level per chat without editing config files or affecting other chats.

## What Changes

- Add a chat-scoped slash command for inspecting and changing the active thinking level at runtime.
- Persist the chat's thinking-level override in session metadata so it survives `/new` and process restarts.
- Resolve the effective thinking level per run by preferring the chat override and falling back to the configured default.
- Surface the active thinking level in status/help output and expose the new command in Telegram's command menu.

## Capabilities

### New Capabilities
- `chat-thinking-level`: Defines how a chat can inspect, set, clear, persist, and apply a per-chat model thinking-level override through slash commands.

### Modified Capabilities

None.

## Impact

- Affected code: `nanobot/command/builtin.py`, `nanobot/command/router.py`, `nanobot/agent/loop.py`, `nanobot/session/manager.py`, `nanobot/channels/telegram.py`, `nanobot/utils/helpers.py`, and related tests.
- Affected systems: chat command handling, Telegram command registration, session persistence, per-run agent configuration, and status/help rendering.
- External considerations: provider requests must continue using only supported reasoning-effort values (`low`, `medium`, `high`, or default fallback behavior).

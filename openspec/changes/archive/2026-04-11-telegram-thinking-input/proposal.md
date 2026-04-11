## Why

The current `/thinking` command works for typed arguments, but its no-argument behavior still falls back to plain text. On Telegram, changing a chat setting is a better fit for inline keyboards, where users can inspect and change options directly below the relevant message without adding extra chat noise.

## What Changes

- Add Telegram-specific interactive behavior for `/thinking` with no arguments so the bot shows an inline keyboard for selecting the chat's thinking level.
- Keep typed `/thinking low|medium|high|off` behavior intact while making the no-argument path more ergonomic on Telegram.
- Add callback-query handling for the inline keyboard so button presses update the existing bot message and apply the selected thinking level without sending command text into the chat.
- Preserve the existing chat-scoped `reasoning_effort` session override model and status/help visibility while extending Telegram's input UX.

## Capabilities

### New Capabilities
- `telegram-thinking-input`: Defines Telegram-specific inline-keyboard interaction for inspecting and changing a chat's thinking level when `/thinking` is invoked without arguments.

### Modified Capabilities

None.

## Impact

- Affected code: `nanobot/channels/telegram.py`, `nanobot/command/builtin.py`, Telegram-facing tests, and any command/output surfaces needed to render interactive thinking selection.
- Affected systems: Telegram command handling, callback query routing, chat-scoped thinking-level interaction UX, and bot message editing behavior.
- External considerations: implementation should follow Telegram inline-keyboard and callback-query behavior, including answering callback queries and editing the existing message instead of posting unnecessary follow-up messages.

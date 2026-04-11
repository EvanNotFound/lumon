## Context

`telegram-thinking-level` established chat-scoped thinking-level control and currently models `/thinking` as a shared slash command that returns text output when invoked without arguments. That works functionally, but it underuses Telegram's interaction model for settings-like flows. Telegram inline keyboards are designed specifically for this case: the bot can present options directly below its own message, button presses arrive as callback queries instead of user chat messages, and the bot can update the same message in place.

The current Telegram channel already owns Telegram-specific delivery details such as command registration, message sending, reply threading, and edit/update behavior. There is no existing callback-query routing or inline-keyboard abstraction in the channel. The clean design is therefore to preserve shared command semantics while letting the shared `/thinking` command request a Telegram-specific interactive surface through outbound metadata that only the Telegram adapter interprets.

The relevant Telegram documentation constrains the design in a few important ways:
- Inline keyboards use `InlineKeyboardMarkup` and `InlineKeyboardButton` with `callback_data` values.
- Callback buttons produce callback queries instead of sending chat messages.
- Callback queries must be answered to stop the Telegram client loading indicator.
- The bot should use message editing (`edit_message_text` and/or `edit_message_reply_markup`) to update the existing settings message.
- `callback_data` is limited to a small payload, so the callback encoding should stay compact and self-validating.

## Goals / Non-Goals

**Goals:**
- Make `/thinking` with no arguments open a Telegram inline-keyboard picker instead of only replying with plain text.
- Reuse the existing chat-scoped `reasoning_effort` model and typed command behavior.
- Keep Telegram-specific interaction logic in the Telegram channel layer while preserving shared command ownership of thinking-level state and messaging semantics.
- Ensure button presses update the existing Telegram message and apply the selection without creating extra chat noise.
- Handle callback-query acknowledgements and invalid/stale callback payloads safely.

**Non-Goals:**
- Replace typed `/thinking low|medium|high|off` input.
- Add inline-keyboard interaction for non-Telegram channels.
- Introduce a generic cross-channel interactive UI framework beyond what this Telegram flow needs.
- Change the underlying meaning of chat-scoped thinking-level persistence, status, or subagent inheritance.

## Decisions

### 1. Keep `/thinking` logic shared and request Telegram interactivity through outbound metadata

The shared `/thinking` handler should remain the place that decides what the current state is and what thinking-level actions are available. For the Telegram no-argument path, it should return an `OutboundMessage` that includes normal text plus Telegram-specific metadata describing the inline keyboard to render.

Rationale:
- Shared command code already owns chat-scoped thinking-level semantics.
- Telegram-specific rendering belongs in the channel adapter, not in the command router.
- Metadata-based rendering lets the same command continue working in plain-text channels.

Alternatives considered:
- Move `/thinking` entirely into `telegram.py`. Rejected because it duplicates command semantics and drifts from the shared command system.
- Build keyboards directly inside the shared command layer. Rejected because that leaks Telegram transport types into shared product logic.

### 2. Add explicit callback-query handling in the Telegram channel with compact callback payloads

The Telegram channel should register a `CallbackQueryHandler` for a narrow callback namespace dedicated to thinking-level selection. Callback payloads should be compact, such as a fixed prefix plus the requested level/action, and validated defensively before applying any state change.

Rationale:
- Telegram callback queries are the native event type for inline keyboard buttons.
- A small, namespaced callback format stays within Telegram limits and avoids accidental collisions with future features.
- Explicit validation is important because Telegram warns that callback data should not be blindly trusted.

Alternatives considered:
- Encode full session state in callback payloads. Rejected because it is unnecessary and wastes callback-data budget.
- Re-dispatch button presses as fake chat messages. Rejected because callback queries and message edits already provide a cleaner interaction model.

### 3. Edit the same Telegram message after every selection

The initial `/thinking` response should send one bot message containing the current state and inline keyboard. When the user presses a button, the bot should answer the callback query and edit that same message to reflect the updated active state, keeping the keyboard available unless the flow is explicitly dismissed.

Rationale:
- This matches Telegram's recommended inline-keyboard UX for settings and toggles.
- Editing the same message avoids cluttering the chat with repeated status responses.
- Keeping the keyboard attached allows fast repeated adjustments.

Alternatives considered:
- Send a fresh confirmation message after each selection. Rejected because it adds unnecessary chat noise.
- Remove the keyboard after one selection. Rejected because users often adjust settings iteratively.

### 4. Preserve typed `/thinking` commands and non-Telegram no-arg behavior

Typed `/thinking low|medium|high|off` should remain the canonical cross-channel way to set or clear the thinking level. The new Telegram behavior should only affect the no-argument path and should degrade to existing text output on channels that do not support Telegram inline keyboards.

Rationale:
- This keeps the feature additive and low-risk.
- Shared command behavior remains predictable across channels.
- Operators and tests already rely on typed command flows.

Alternatives considered:
- Make `/thinking` keyboard-only. Rejected because it would regress CLI and non-Telegram usability.

### 5. Reuse existing session helpers for state changes triggered by callbacks

Callback handlers should ultimately use the same reasoning-effort helper logic that typed commands use to read, set, clear, and describe the session override. The callback path should not create a parallel state-management path.

Rationale:
- One state path reduces drift between typed commands and button presses.
- Existing persistence and per-run resolution behavior remains unchanged.

Alternatives considered:
- Apply session metadata changes directly inside Telegram-specific callback code. Rejected because it duplicates business rules and response formatting concerns.

## Risks / Trade-offs

- [Telegram callback handling adds channel-specific complexity] -> Keep the callback namespace narrow and confine transport details to `telegram.py`.
- [Interactive messages can become stale after restart or message deletion] -> Answer callback queries and show a graceful stale/expired response when the original context can no longer be applied.
- [Keyboard state may become inconsistent with out-of-band typed changes] -> Recompute displayed state from the session on every callback-driven edit instead of relying on button labels alone.
- [Metadata-driven rendering could tempt broader ad hoc channel payloads] -> Keep the metadata format tightly scoped to thinking-level interaction and document it in tests/design.

## Migration Plan

1. Extend the shared `/thinking` no-argument path so it can describe a Telegram inline-keyboard response without changing typed command behavior.
2. Add Telegram inline-keyboard rendering and callback-query handling for the thinking-level callback namespace.
3. Reuse existing session reasoning-effort helpers to apply button-driven changes and refresh the edited message state.
4. Add Telegram-focused tests for keyboard rendering, callback handling, message editing, stale callbacks, and coexistence with typed `/thinking` commands.
5. Roll back by removing the Telegram-specific metadata/callback handling while leaving the typed `/thinking` command path intact.

## Open Questions

- Should the inline keyboard include a dedicated close/dismiss button, or should it remain permanently available beneath the latest thinking-status message?
- Should the keyboard visually mark the active state with emoji/checkmarks, or is text-only labeling sufficient for the first iteration?
- Should `/thinking` with no args on Telegram always send a fresh picker message, or should future work try to reuse/edit a prior picker if one exists?

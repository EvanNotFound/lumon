## 1. Shared command output for interactive Telegram thinking selection

- [x] 1.1 Extend the shared `/thinking` no-argument path to emit Telegram-specific response metadata for an inline keyboard while keeping text-only behavior for non-Telegram channels.
- [x] 1.2 Reuse existing session reasoning-effort helpers so both typed commands and future Telegram button presses share the same read/set/clear/describe logic.
- [x] 1.3 Define and document a compact callback-data namespace for Telegram thinking-picker actions (`low`, `medium`, `high`, `off`, and any optional dismiss action).

## 2. Telegram inline keyboard and callback-query handling

- [x] 2.1 Add Telegram channel rendering for thinking-picker metadata using `InlineKeyboardMarkup` and `InlineKeyboardButton`.
- [x] 2.2 Register a Telegram `CallbackQueryHandler` for the thinking-picker callback namespace.
- [x] 2.3 Implement callback handling that answers the callback query, validates callback data, applies the selected thinking-level change, and edits the existing bot message in place.
- [x] 2.4 Add graceful handling for invalid or stale callback queries without mutating session state.

## 3. Message state and UX consistency

- [x] 3.1 Ensure the Telegram thinking picker always displays the currently active thinking level derived from the session state.
- [x] 3.2 Preserve typed `/thinking low|medium|high|off` behavior alongside the Telegram no-argument inline picker.
- [x] 3.3 Confirm Telegram no-argument `/thinking` avoids unnecessary follow-up messages when users change values via buttons.

## 4. Verification

- [x] 4.1 Add command-level tests for Telegram no-argument `/thinking` metadata output versus non-Telegram text-only output.
- [x] 4.2 Add Telegram channel tests for inline-keyboard rendering, callback-query answering, and in-place message editing after selection.
- [x] 4.3 Add tests for invalid/stale callback handling and session-state correctness after button-driven changes.
- [x] 4.4 Update existing thinking-level and Telegram discovery tests as needed to cover the new interaction flow.

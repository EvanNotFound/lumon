## 1. Command and session state plumbing

- [x] 1.1 Add shared helpers to read, set, clear, and describe a session's `reasoning_effort` override using `Session.metadata`.
- [x] 1.2 Implement the shared `/thinking` command flow for inspect, set (`low|medium|high`), clear (`off`), and invalid-usage responses.
- [x] 1.3 Register `/thinking` in the built-in command router and add it to shared help text.

## 2. Per-run thinking-level resolution

- [x] 2.1 Resolve an effective thinking level for each chat run by preferring the session override over the configured default.
- [x] 2.2 Pass the effective thinking level explicitly into main agent runs instead of relying only on provider global defaults.
- [x] 2.3 Ensure subagent work spawned from a chat inherits the same effective thinking level.

## 3. User-visible Telegram surfaces

- [x] 3.1 Add `/thinking` to Telegram's registered bot command menu and forward it through the existing unified command path.
- [x] 3.2 Extend status rendering so `/status` shows the active thinking level and whether it comes from a chat override or the default.
- [x] 3.3 Confirm `/new` preserves the chat override while clearing conversation history.

## 4. Verification

- [x] 4.1 Add command-level tests for `/thinking` inspect, set, clear, and invalid input behavior.
- [x] 4.2 Add session-persistence tests covering `/new`, session save/load, and Telegram topic-scoped isolation.
- [x] 4.3 Add agent/runtime tests proving the effective thinking level is passed to main runs and inherited by subagents.
- [x] 4.4 Update Telegram/help/status tests for command discovery and visible state reporting.

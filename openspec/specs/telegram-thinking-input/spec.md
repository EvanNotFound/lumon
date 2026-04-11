## ADDED Requirements

### Requirement: Telegram `/thinking` without arguments opens an inline keyboard picker
The system SHALL treat `/thinking` with no arguments as an interactive Telegram settings flow that presents the current thinking-level state and an inline keyboard of available actions.

#### Scenario: Telegram no-arg command renders keyboard
- **WHEN** a user sends `/thinking` in Telegram without arguments
- **THEN** nanobot SHALL send a Telegram bot message describing the current effective thinking level for that chat
- **AND** that message SHALL include an inline keyboard with actions for `low`, `medium`, `high`, and `off`

#### Scenario: Active state is visible in picker message
- **WHEN** nanobot renders the Telegram thinking picker
- **THEN** the message and/or keyboard labels SHALL indicate the chat's currently active thinking level
- **AND** the rendered state SHALL be derived from the current session state rather than assumed from prior button presses

### Requirement: Typed thinking commands remain supported
The system SHALL preserve typed `/thinking low|medium|high|off` behavior even after Telegram inline input is introduced.

#### Scenario: Typed set command still works in Telegram
- **WHEN** a Telegram user sends `/thinking high`
- **THEN** nanobot SHALL apply the `high` thinking-level override for that chat without requiring inline button interaction

#### Scenario: Non-Telegram no-arg behavior remains text-based
- **WHEN** a user sends `/thinking` without arguments on a non-Telegram channel
- **THEN** nanobot SHALL continue returning a non-interactive text response describing the active thinking level

### Requirement: Telegram callback buttons change thinking level without sending extra user messages
The system SHALL handle Telegram thinking-picker buttons through callback queries instead of chat messages and apply the selected thinking-level change to the current chat session.

#### Scenario: Selecting a level from callback data
- **WHEN** a user presses a Telegram thinking-picker button for `low`, `medium`, or `high`
- **THEN** nanobot SHALL treat the button press as a callback query for the originating chat session
- **AND** nanobot SHALL persist the selected thinking-level override for that chat

#### Scenario: Clearing override from callback data
- **WHEN** a user presses the Telegram thinking-picker button for `off`
- **THEN** nanobot SHALL clear the chat's thinking-level override
- **AND** the chat SHALL fall back to the configured default thinking behavior

### Requirement: Telegram callback interactions update the existing bot message
The system SHALL answer Telegram callback queries and update the relevant bot message in place so repeated settings changes do not add unnecessary chat noise.

#### Scenario: Callback query is acknowledged
- **WHEN** nanobot receives a callback query from the Telegram thinking picker
- **THEN** nanobot SHALL answer the callback query so the Telegram client stops showing its loading indicator

#### Scenario: Existing bot message is edited after selection
- **WHEN** nanobot successfully processes a Telegram thinking-picker callback query
- **THEN** nanobot SHALL edit the original bot message to reflect the newly active thinking level
- **AND** nanobot SHALL avoid posting an additional confirmation message to the chat for that selection

### Requirement: Telegram callback handling is validated and resilient
The system SHALL validate Telegram thinking-picker callback data and fail gracefully when the callback can no longer be applied.

#### Scenario: Invalid callback data is rejected safely
- **WHEN** nanobot receives Telegram callback data outside the supported thinking-picker namespace or values
- **THEN** nanobot SHALL reject the callback without mutating chat thinking-level state

#### Scenario: Stale callback is handled gracefully
- **WHEN** nanobot receives a Telegram thinking-picker callback that cannot be applied because the original context is no longer valid
- **THEN** nanobot SHALL answer the callback query
- **AND** nanobot SHALL return a graceful Telegram-visible failure response instead of crashing

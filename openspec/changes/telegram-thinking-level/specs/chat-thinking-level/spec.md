## ADDED Requirements

### Requirement: Chats can inspect and change the active thinking level
The system SHALL provide a slash command that lets a chat inspect the current effective thinking level and set a chat-scoped override using only supported values.

#### Scenario: Inspect current thinking level
- **WHEN** a user sends `/thinking` in a chat
- **THEN** nanobot SHALL reply with the chat's current effective thinking level
- **AND** the reply SHALL indicate whether the value comes from a chat override or the configured default

#### Scenario: Set chat override to a supported value
- **WHEN** a user sends `/thinking low`, `/thinking medium`, or `/thinking high`
- **THEN** nanobot SHALL store that value as the current chat's thinking-level override
- **AND** nanobot SHALL confirm the newly active thinking level in the reply

#### Scenario: Reject unsupported thinking value
- **WHEN** a user sends `/thinking` with an unsupported argument
- **THEN** nanobot SHALL reject the request with an explicit usage message listing the supported values

### Requirement: Chats can clear the override without changing the global default
The system SHALL let a chat remove its thinking-level override and return to the configured default behavior without mutating process-wide provider defaults.

#### Scenario: Clear chat override
- **WHEN** a user sends `/thinking off`
- **THEN** nanobot SHALL remove the thinking-level override for that chat
- **AND** subsequent runs for that chat SHALL use the configured default thinking level

#### Scenario: Clearing override preserves default-off behavior
- **WHEN** a chat clears its override and the configured default thinking level is unset
- **THEN** nanobot SHALL run future turns for that chat without a reasoning-effort override

### Requirement: Chat overrides persist with the chat session
The system SHALL persist the chat's thinking-level override in session state so the setting survives chat resets and reloads for the same chat session key.

#### Scenario: Override survives new conversation reset
- **WHEN** a chat has an active thinking-level override and the user sends `/new`
- **THEN** nanobot SHALL clear conversation history for that session
- **AND** nanobot SHALL preserve the chat's thinking-level override

#### Scenario: Override survives session reload
- **WHEN** nanobot reloads a previously saved session for the same chat session key
- **THEN** the saved thinking-level override SHALL be restored from session metadata

#### Scenario: Telegram topics keep separate overrides
- **WHEN** two Telegram topic sessions within the same group set different thinking levels
- **THEN** nanobot SHALL preserve and apply the override independently for each topic-scoped session key

### Requirement: Agent runs use the effective chat thinking level
The system SHALL resolve an effective thinking level for each chat run by preferring the chat override over the configured default and pass that value into agent execution for that chat.

#### Scenario: Main chat run uses chat override
- **WHEN** a chat with an active thinking-level override triggers a normal assistant turn
- **THEN** nanobot SHALL pass that override as the run's reasoning-effort value

#### Scenario: Main chat run falls back to default
- **WHEN** a chat has no thinking-level override and triggers a normal assistant turn
- **THEN** nanobot SHALL use the configured default reasoning-effort value for that run

#### Scenario: Subagent work inherits effective thinking level
- **WHEN** nanobot spawns subagent work on behalf of a chat
- **THEN** the subagent run SHALL use the same effective thinking level resolved for the originating chat

### Requirement: Telegram users can discover the active command and state
The system SHALL expose the thinking-level control through the existing user-facing command surfaces relevant to Telegram usage.

#### Scenario: Help output includes thinking command
- **WHEN** a user requests `/help`
- **THEN** the command list SHALL include `/thinking` with a description of its purpose

#### Scenario: Status output shows active thinking level
- **WHEN** a user requests `/status`
- **THEN** the status output SHALL show the chat's active thinking level
- **AND** the status output SHALL indicate whether the value comes from a chat override or the configured default

#### Scenario: Telegram command menu includes thinking command
- **WHEN** Telegram registers the bot's available commands
- **THEN** the Telegram command menu SHALL include `/thinking`

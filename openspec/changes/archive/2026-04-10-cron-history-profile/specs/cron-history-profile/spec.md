## ADDED Requirements

### Requirement: Cron jobs support explicit history profiles
The system SHALL support a persisted history profile for each cron job to control how much prior transcript is retained across recurring executions.

#### Scenario: New cron job defaults to compact history retention
- **WHEN** an operator creates a new cron job without explicitly selecting a history profile
- **THEN** Nanobot SHALL persist the job with the `compact` history profile

#### Scenario: Cron listing exposes the selected profile
- **WHEN** an operator lists scheduled jobs
- **THEN** Nanobot SHALL include each job's effective history profile in the listed job details

#### Scenario: Legacy cron job remains compatible when no profile is stored
- **WHEN** Nanobot loads an existing cron job from storage that does not contain a history profile field
- **THEN** Nanobot SHALL treat that job's effective history profile as `normal`

### Requirement: Stateless cron jobs do not reuse prior transcript history
The system SHALL prevent stateless cron jobs from reusing prior session transcript history between runs.

#### Scenario: Stateless profile clears existing cron transcript before execution
- **WHEN** a cron job with the `stateless` profile is about to execute and its `cron:<job.id>` session already contains prior messages
- **THEN** Nanobot SHALL clear the prior session transcript before building the new run's prompt

### Requirement: Rolling-history cron jobs retain only bounded recent transcript
The system SHALL bound prior transcript reuse for non-stateless cron jobs according to their selected history profile before each execution.

#### Scenario: Compact profile keeps only a recent legal suffix
- **WHEN** a cron job with the `compact` profile is about to execute and its prior `cron:<job.id>` transcript exceeds the compact retention window
- **THEN** Nanobot SHALL retain only the most recent compact-sized legal suffix before building the new run's prompt

#### Scenario: Normal profile keeps a larger recent legal suffix
- **WHEN** a cron job with the `normal` profile is about to execute and its prior `cron:<job.id>` transcript exceeds the normal retention window
- **THEN** Nanobot SHALL retain only the most recent normal-sized legal suffix before building the new run's prompt

#### Scenario: Retained history preserves tool-call legality
- **WHEN** Nanobot trims a cron session for a rolling-history profile
- **THEN** the retained transcript SHALL begin at a legal assistant/user/tool boundary and SHALL NOT start with orphaned tool results

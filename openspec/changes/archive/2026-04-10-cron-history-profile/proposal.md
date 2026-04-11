## Why

Recurring cron jobs currently reuse a per-job session that can grow indefinitely, which makes scheduled runs increasingly expensive in prompt tokens and harder to keep focused. Nanobot needs an explicit cron-level history policy so recurring jobs can retain only the amount of context appropriate for their purpose instead of waiting for late global consolidation.

## What Changes

- Add a cron job profile that controls how much prior transcript is kept between recurring runs.
- Define profile-driven retention behavior for scheduled jobs, including a fully stateless mode and bounded rolling-history modes.
- Persist the selected profile in cron job storage and expose it through cron job creation, listing, and runtime execution.
- Apply cron profile retention before each cron-triggered agent run so prompt size stays bounded for recurring jobs.

## Capabilities

### New Capabilities
- `cron-history-profile`: Per-cron-job history retention profiles for stateless and bounded recurring execution.

### Modified Capabilities

## Impact

- Affected code: `nanobot/cron/types.py`, `nanobot/cron/service.py`, `nanobot/agent/tools/cron.py`, `nanobot/cli/commands.py`, and cron/session integration in `nanobot/agent/loop.py`.
- Affected systems: cron job persistence, cron tool UX, scheduled agent execution, and session retention behavior for `cron:<job.id>` sessions.
- User-visible behavior: recurring cron jobs will keep context according to their configured profile rather than always accumulating full session history.

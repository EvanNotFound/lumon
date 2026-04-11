## Context

Cron jobs already execute through per-job sessions keyed as `cron:<job.id>`, so recurring runs naturally accumulate conversation history over time. That persistence is useful for a small class of assistant-like scheduled workflows, but it is a poor default for reminders, monitors, and recurring reports because the prompt keeps growing until the general session consolidation logic finally intervenes near the global context ceiling.

The existing codebase already has two useful retention primitives: cron jobs have a stable persisted data model, and sessions can be cleared or reduced to a recent legal suffix without breaking tool-call boundaries. This change needs to connect those pieces with an explicit cron-facing policy that keeps recurring jobs bounded before each run.

## Goals / Non-Goals

**Goals:**
- Add a first-class cron history profile that expresses retention intent at the job level.
- Keep recurring cron runs bounded before each execution instead of waiting for late token-based consolidation.
- Preserve legal assistant/tool message boundaries when retaining partial history.
- Expose the selected profile through cron creation, persistence, and listing so behavior is understandable and durable.
- Improve default behavior for newly created recurring cron jobs without silently breaking existing stored jobs.

**Non-Goals:**
- Introducing arbitrary per-job token tuning or a full cron settings matrix in the first version.
- Changing non-cron session retention behavior for chat, system, or direct agent sessions.
- Reworking the existing global memory consolidation pipeline.
- Adding cron job editing beyond the existing add/list/remove workflow.

## Decisions

### Decision: Represent retention with a cron profile enum
Cron jobs will gain a dedicated profile field with three supported values: `stateless`, `compact`, and `normal`.

- `stateless` means prior cron transcript is discarded before the run.
- `compact` means only a small recent legal suffix is kept.
- `normal` means a larger recent legal suffix is kept for assistant-like recurring jobs.

This keeps the user-facing model intention-based instead of exposing low-level message or token knobs. It also avoids overloading `payload.kind`, which describes what a job executes rather than how much history it should retain.

**Alternatives considered:**
- **Raw `max_messages` on each job**: simple internally, but poor UX and easy to mis-tune.
- **Raw `max_tokens` on each job**: better aligned to cost, but harder to explain and unnecessary for a first pass.
- **Reuse `payload.kind`**: too coarse and semantically unrelated to history retention.

### Decision: Store the profile on the cron job and persist it through the existing jobs store
The profile will live in the persisted cron job model so that scheduling behavior is stable across process restarts and visible in job listings. New jobs created through the cron tool will write an explicit profile value into the store.

For backward compatibility, legacy jobs loaded from disk without a stored profile will be interpreted as `normal` so pre-existing recurring jobs keep their current broad-history behavior until the operator recreates or updates them.

**Alternatives considered:**
- **Keep profile transient at execution time only**: not durable and hard to reason about.
- **Default legacy jobs to `compact`**: would reduce cost, but changes stored-job behavior silently.

### Decision: Apply profile retention immediately before each cron-triggered run
Before calling `agent.process_direct(...)` for a cron job, Nanobot will load that job's session and enforce the profile:

- `stateless` clears the session history.
- `compact` retains a profile-defined recent legal suffix.
- `normal` retains a larger profile-defined recent legal suffix.

This hooks into the cron execution path at the point where the job-specific session key is already known and keeps the retention rule local to cron behavior. The implementation should use the session manager's legal-suffix logic so retained history never starts with orphaned tool results.

**Alternatives considered:**
- **Rely only on existing token-based consolidation**: too late for recurring cron cost control.
- **Trim inside the generic agent loop for all sessions**: broader blast radius than needed.

### Decision: Start with message-count-backed presets, keeping profile as the public contract
The initial implementation can map profiles to fixed message-count retention using existing session APIs. This is the lowest-risk way to bound recurring history while preserving legal message boundaries.

The profile remains the stable external contract, which leaves room to evolve the internal mapping to token budgets later without changing the cron UX.

**Alternatives considered:**
- **Token-based trimming from day one**: more precise, but requires extra policy plumbing and estimation at cron runtime.
- **Stateless-only support**: solves only one class of jobs and does not help recurring assistant/report workflows.

## Risks / Trade-offs

- **[Compact profile may drop context a job relied on]** → Keep `normal` available for assistant-like jobs and preserve legacy jobs as `normal` when no profile is stored.
- **[Message-count presets are a rough proxy for token cost]** → Hide the implementation detail behind profiles so a later token-based mapping can improve precision without changing the user-facing model.
- **[Operators may not understand which profile to choose]** → Expose profile clearly in cron tool help/list output and keep the profile set small.
- **[Stateless runs may still use durable memory and therefore are not "blank slates"]** → Document stateless as "no prior transcript" rather than "no memory of any kind."

## Migration Plan

1. Extend the cron job model and JSON store format with an optional persisted profile field.
2. Treat missing profile values on load as `normal` for compatibility with existing jobs.
3. Set newly created cron jobs to `compact` unless the creator explicitly chooses another profile.
4. Apply profile retention to `cron:<job.id>` sessions immediately before cron-triggered execution.
5. Surface the chosen profile in cron listings so operators can inspect behavior after rollout.

Rollback is straightforward: ignore the stored profile field and resume the prior cron execution path. Existing job store data remains readable because the additional field is additive.

## Open Questions

- Should one-time `at` jobs also default to `compact`, or should they be explicitly `stateless` for clarity even though they auto-delete after execution?
- Do we want a future cron-job update/edit command so operators can change profiles without recreating jobs?
- Should cron profile names appear in user-facing cron skill documentation as simple descriptions (for example, reminder/report/assistant guidance) in addition to the raw enum values?

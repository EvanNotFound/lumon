## 1. Cron profile model and persistence

- [x] 1.1 Add a cron history profile field/type to the cron job model with supported values for `stateless`, `compact`, and `normal`
- [x] 1.2 Update cron job store load/save logic to persist the profile and treat missing stored values as legacy `normal`
- [x] 1.3 Define the internal retention mapping for each profile using bounded legal-suffix session retention primitives

## 2. Cron creation and visibility

- [x] 2.1 Extend cron job creation paths to accept an optional profile and default new jobs to `compact`
- [x] 2.2 Update cron list output to show each job's effective history profile
- [x] 2.3 Refresh cron-facing help/skill text so the available profiles and their intent are discoverable

## 3. Cron execution retention

- [x] 3.1 Apply the selected cron profile to the `cron:<job.id>` session immediately before cron-triggered execution starts
- [x] 3.2 Implement stateless execution by clearing prior cron transcript history before prompt construction
- [x] 3.3 Implement compact and normal execution by retaining only the configured recent legal suffix before prompt construction

## 4. Verification

- [x] 4.1 Add tests for cron job persistence, defaulting, and legacy profile fallback behavior
- [x] 4.2 Add tests for cron execution retention behavior for stateless, compact, and normal profiles
- [x] 4.3 Run the relevant cron and session test coverage and fix any regressions

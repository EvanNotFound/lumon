## Context

Nanobot currently uses a two-stage memory pipeline for the Supermemory backend. After each completed exchange, the memory decision model selects `skip`, `consolidate`, or `both`. For `consolidate`, Nanobot asks its LLM to emit one summary record, then sends that text to Supermemory, which performs its own memory extraction. This keeps ingestion costs low, but it can lose exact values and user-requested durable facts because the first-stage summary is optimized for brevity rather than downstream extraction.

The change needs to improve recall without turning Supermemory into a raw transcript archive. The existing `skip` / `summary` / `both` policy is already a good cost-control primitive, and Supermemory supports metadata, `custom_id`, and `entityContext`, which can help guide extraction without changing the overall architecture.

## Goals / Non-Goals

**Goals:**
- Keep summary-first ingestion as the default for Supermemory to control token cost.
- Make Supermemory summary records more extraction-friendly, especially for exact literals and explicit user memory requests.
- Preserve the existing `skip` / `summary` / `both` decision model while tightening the guidance for when `both` is warranted.
- Add configuration or payload support needed to steer Supermemory extraction context per workspace/container.
- Improve retrieval quality without changing the local memory backend behavior.

**Non-Goals:**
- Replacing Supermemory with a different memory backend.
- Ingesting every conversation turn as raw text by default.
- Adding a new primary persistence mode beyond `skip`, `summary`, and `both`.
- Reworking unrelated session token-consolidation behavior outside the Supermemory path.

## Decisions

### 1. Keep summary-first ingestion as the default
Nanobot will continue to send concise summary records for most durable exchanges. This keeps ingestion volume and token spend predictable while still letting Supermemory perform its own extraction.

**Alternatives considered:**
- **Store raw conversation directly by default:** rejected because it increases ingestion cost and sends too much filler/noise to Supermemory.
- **Summary-only with no raw fallback:** rejected because some exchanges need literal preservation.

### 2. Redesign Supermemory summaries as extraction-oriented records
The summary prompt and tool contract should produce records optimized for Supermemory's extractor instead of generic human-friendly summaries. Records should preserve exact literals such as URLs, handles, IDs, repo names, and short mappings, and should clearly mark explicit user memory requests.

**Alternatives considered:**
- **Keep the current free-form concise summary:** rejected because it over-compresses important literals.
- **Move all structure into metadata only:** rejected because Supermemory extracts memory from the ingested text itself, so the content must carry the durable facts.

### 3. Keep `skip` / `summary` / `both`, but tighten the `both` boundary
The existing decision model remains the right shape. `summary` stays the default for durable but compressible exchanges; `both` is reserved for exchanges where exact wording or long-form source text materially improves future recall, such as explicit memory requests with dense content, long notes, or exact reference material.

**Alternatives considered:**
- **Add a new raw-only mode:** rejected because it adds complexity without improving the main cost/fidelity trade-off.
- **Collapse `both` into `summary`:** rejected because high-fidelity fallback is still useful in some cases.

### 4. Add explicit extraction-context support for Supermemory
Nanobot should support passing Supermemory extraction guidance through configuration and ingestion payloads where appropriate, especially via `entityContext`. This allows the workspace to bias Supermemory toward durable assistant memory patterns without hardcoding organization-specific rules in the codebase.

**Alternatives considered:**
- **Rely only on Supermemory organizational context managed outside Nanobot:** insufficient because workspace-specific extraction guidance can still improve behavior.
- **Hardcode extraction policy in prompts only:** rejected because the downstream extractor also benefits from first-class context.

### 5. Preserve compatibility in stored metadata and retrieval flow
Existing metadata kinds such as `summary_turn`, `raw_turn`, and `raw_archive` should continue to work so retrieval filters and current persisted data remain usable. Improvements should layer on top of the current storage categories rather than invalidate them.

**Alternatives considered:**
- **Rename or replace existing kinds wholesale:** rejected because it adds migration complexity without a clear benefit.

## Risks / Trade-offs

- **Over-structuring summaries could reduce semantic richness** → Keep the record format concise and natural enough for semantic search while still preserving exact literals.
- **A broader `both` policy could increase Supermemory ingestion cost** → Keep `summary` as the default and make `both` conditional on fidelity-sensitive exchanges.
- **Entity-context support could be misconfigured or become too opinionated** → Make it optional and document clear defaults.
- **Prompt changes may improve some memories while regressing others** → Cover representative cases with focused tests around explicit remembers, links, and ordinary durable facts.

## Migration Plan

The change can ship without a data migration because it only affects future Supermemory ingestions. Existing stored memories remain queryable under the same metadata kinds. Rollback is straightforward: revert prompt/config changes and continue using the prior summary shape.

## Open Questions

- Should explicit user memory requests always trigger `both`, or only when the content contains high-fidelity details such as long notes or exact references?
- Should `entityContext` be configured globally in Nanobot config, per workspace, or both?

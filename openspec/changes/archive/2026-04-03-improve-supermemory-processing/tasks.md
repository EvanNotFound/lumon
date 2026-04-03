## 1. Supermemory configuration and payload support

- [x] 1.1 Extend Supermemory memory configuration to support optional extraction-context settings needed during ingestion
- [x] 1.2 Update the Supermemory backend add-memory path to include configured extraction context without changing current default behavior
- [x] 1.3 Preserve existing metadata kind handling so current `summary_turn`, `raw_turn`, and `raw_archive` retrieval filters remain compatible

## 2. Extraction-oriented summary generation

- [x] 2.1 Update the Supermemory consolidation prompt and tool guidance so summary records are optimized for downstream extraction rather than generic recap text
- [x] 2.2 Ensure generated Supermemory summary records preserve exact literals such as URLs, handles, IDs, repo names, and short mappings
- [x] 2.3 Make explicit user memory requests visible in summary text so downstream extraction can retain them as durable facts

## 3. Memory decision policy refinement

- [x] 3.1 Revise the post-turn memory decision guidance to keep `summary` as the default durable path and reserve `both` for fidelity-sensitive exchanges
- [x] 3.2 Ensure explicit memory requests with dense or exact reference material can trigger `both` while lower-value exchanges still resolve to `skip`
- [x] 3.3 Verify Supermemory post-turn persistence continues to flow through the existing `skip` / `summary` / `both` model without adding new modes

## 4. Validation and regression coverage

- [x] 4.1 Add or update tests for extraction-oriented Supermemory summaries, including explicit remember requests and exact literal preservation
- [x] 4.2 Add or update tests for configured versus unconfigured Supermemory extraction context during ingestion
- [x] 4.3 Add or update tests for memory-decision outcomes covering `skip`, `summary`, and `both` under the revised guidance

## ADDED Requirements

### Requirement: Supermemory summaries shall be extraction-oriented
When Nanobot persists a durable memory to the Supermemory backend using the summary path, it SHALL generate a summary record optimized for downstream memory extraction rather than a generic conversational recap.

#### Scenario: Summary record preserves durable facts
- **WHEN** a completed exchange is classified for summary persistence
- **THEN** Nanobot generates a concise durable record that emphasizes reusable facts, instructions, preferences, or project context likely to matter in future retrieval

#### Scenario: Summary record preserves exact literals
- **WHEN** the exchange contains exact values such as URLs, handles, IDs, repo names, or short key-value mappings
- **THEN** the generated Supermemory summary preserves those values verbatim in the ingested text

### Requirement: Memory decision policy shall remain skip-summary-both
Nanobot SHALL continue to use a three-way decision policy for post-turn Supermemory persistence: `skip`, `summary`, and `both`.

#### Scenario: Skip omits persistence for low-value exchanges
- **WHEN** a completed exchange has no durable future value
- **THEN** Nanobot selects `skip` and does not persist a summary or raw turn for that exchange

#### Scenario: Summary is the default for durable exchanges
- **WHEN** a completed exchange contains durable but compressible information
- **THEN** Nanobot selects `summary` and persists a Supermemory summary record without requiring raw-turn storage

#### Scenario: Both preserves summary and source text for fidelity-sensitive exchanges
- **WHEN** a completed exchange contains durable information whose exact wording or full source text is likely useful later
- **THEN** Nanobot selects `both` and persists both an extraction-oriented summary record and a raw-turn fallback

### Requirement: Explicit memory requests shall receive stronger preservation
Nanobot SHALL treat explicit user requests to remember information as high-priority durable memory candidates during Supermemory processing.

#### Scenario: Explicit remember request is preserved in summary text
- **WHEN** the user explicitly asks Nanobot to remember, save, or not forget information
- **THEN** the resulting Supermemory summary makes that durable memory intent clear in the ingested text and preserves the requested fact values

#### Scenario: Exact reference material can trigger both
- **WHEN** an explicit memory request includes dense reference material or exact text that would be risky to compress away
- **THEN** Nanobot may classify the exchange as `both` so the summary and raw turn are both retained

### Requirement: Supermemory extraction context shall be configurable
Nanobot SHALL support passing optional Supermemory extraction guidance so workspace-specific durable memory patterns can be reinforced during ingestion.

#### Scenario: Configured entity context is attached during ingestion
- **WHEN** Supermemory extraction context is configured for the active workspace or container
- **THEN** Nanobot includes that context in Supermemory ingestion requests for new persisted memories

#### Scenario: Unconfigured entity context preserves current behavior
- **WHEN** no Supermemory extraction context is configured
- **THEN** Nanobot continues ingesting memories without requiring additional context configuration

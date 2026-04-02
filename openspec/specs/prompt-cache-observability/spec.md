## ADDED Requirements

### Requirement: Operators can configure OpenAI prompt cache retention
The system SHALL support configuring prompt cache retention for Responses-based OpenAI requests, including support for `24h` retention.

#### Scenario: Responses request includes configured retention
- **WHEN** a provider configuration enables prompt cache retention for Responses mode
- **THEN** nanobot SHALL include the configured retention value in the outbound Responses request

#### Scenario: OpenAI retention supports 24h mode
- **WHEN** the operator selects `24h` prompt cache retention for a Responses-capable OpenAI deployment
- **THEN** nanobot SHALL send `24h` as the prompt cache retention policy

### Requirement: Prompt cache keys remain stable across similar requests
The system SHALL derive `prompt_cache_key` from stable request identity instead of the full dynamic conversation payload.

#### Scenario: Similar requests reuse the same cache key
- **WHEN** two Responses requests share the same provider identity, model family, and effective tool schema while only the live conversation content changes
- **THEN** nanobot SHALL generate the same prompt cache key for both requests

#### Scenario: Materially different request identities change the cache key
- **WHEN** a Responses request changes provider scope, model family, or effective tool schema
- **THEN** nanobot SHALL generate a different prompt cache key

### Requirement: Prompt cache usage is preserved in provider usage data
The system SHALL preserve prompt-cache usage details returned by the Responses API, including cached prompt tokens.

#### Scenario: Cached prompt tokens are parsed from provider response
- **WHEN** a Responses API result includes cached token details in its usage payload
- **THEN** nanobot SHALL retain the cached token count in normalized provider usage data

#### Scenario: Missing cache fields do not break usage parsing
- **WHEN** a Responses API result omits prompt-cache usage details
- **THEN** nanobot SHALL still return normalized usage data without failing the request

### Requirement: Runtime status can report prompt cache effectiveness
The system SHALL expose prompt-cache usage metrics to runtime reporting so operators can evaluate whether prompt caching is working.

#### Scenario: Status output includes cached token information
- **WHEN** nanobot has prompt-cache usage data from the most recent Responses call
- **THEN** runtime status reporting SHALL include cached-token information alongside other token usage details

#### Scenario: Status output remains valid without cache hits
- **WHEN** the most recent Responses call reports zero cached tokens or no cache details
- **THEN** runtime status reporting SHALL remain available and SHALL represent the cache result as zero or unavailable rather than failing

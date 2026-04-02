## ADDED Requirements

### Requirement: OpenAI provider can use Responses API with custom base URLs
The system SHALL support an OpenAI Responses API execution path for the `openai` provider while preserving the configured `api_key`, `api_base`, and extra headers used for direct OpenAI and proxy-backed OpenAI deployments.

#### Scenario: OpenAI provider uses configured proxy endpoint
- **WHEN** the operator configures the `openai` provider to use Responses mode and sets a custom `api_base`
- **THEN** nanobot SHALL send Responses API requests to that configured base URL with the same OpenAI credentials and headers already defined for the provider

#### Scenario: OpenAI provider uses default endpoint when no custom base is set
- **WHEN** the operator configures the `openai` provider to use Responses mode without overriding `api_base`
- **THEN** nanobot SHALL send Responses API requests using the provider's default OpenAI endpoint behavior

### Requirement: Custom providers opt into Responses compatibility explicitly
The system SHALL require explicit configuration before using the Responses API for the `custom` provider.

#### Scenario: Custom provider remains on compat mode by default
- **WHEN** the operator configures a `custom` provider without enabling Responses mode
- **THEN** nanobot SHALL continue using the non-Responses OpenAI-compatible request path

#### Scenario: Custom provider can opt into Responses mode
- **WHEN** the operator explicitly enables Responses mode for a `custom` provider
- **THEN** nanobot SHALL use the Responses API request path for that provider configuration

### Requirement: Responses mode failures are explicit
The system MUST fail clearly when a provider is configured for Responses mode and the endpoint does not support the Responses API.

#### Scenario: Endpoint rejects Responses requests
- **WHEN** a Responses-configured provider receives an API error indicating the endpoint does not support `/v1/responses` or the required request shape
- **THEN** nanobot SHALL return an explicit error describing that the endpoint rejected Responses mode

#### Scenario: Responses mode does not silently downgrade
- **WHEN** a Responses-configured provider encounters a compatibility error from the endpoint
- **THEN** nanobot SHALL NOT silently retry the request through Chat Completions mode

### Requirement: Responses requests separate stable instructions from volatile input
The system SHALL construct Responses requests so that stable assistant instructions are separated from per-turn input content, improving prompt cache reuse for OpenAI-compatible Responses endpoints.

#### Scenario: Stable instruction content is emitted separately
- **WHEN** nanobot constructs a Responses request for a normal chat turn
- **THEN** the request SHALL place stable identity and workspace guidance into the instruction layer instead of merging all prompt content into a single chat-completions-style message list

#### Scenario: Volatile content remains later in the request
- **WHEN** nanobot includes retrieved memory, prior conversation turns, or the current user turn in a Responses request
- **THEN** that volatile content SHALL be placed in the input layer after the stable instruction content

### Requirement: Tool definitions remain deterministic for Responses requests
The system SHALL emit deterministic tool definitions for Responses-based provider calls so repeated requests with the same toolset can share stable prefixes.

#### Scenario: Same toolset yields stable tool definitions
- **WHEN** two Responses requests are made with the same enabled tools and unchanged tool schemas
- **THEN** nanobot SHALL emit equivalent tool definitions in a deterministic order across both requests

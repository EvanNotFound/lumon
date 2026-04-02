## 1. Provider and config routing

- [x] 1.1 Add provider/config settings to distinguish Chat Completions vs Responses mode and prompt cache retention for OpenAI-style providers.
- [x] 1.2 Update provider selection so `provider: openai` can route to a dedicated Responses implementation while preserving configured `api_key`, `api_base`, and `extra_headers`.
- [x] 1.3 Add explicit opt-in routing for `custom` providers so Responses mode is only used when configured.

## 2. Responses provider implementation

- [x] 2.1 Add a dedicated OpenAI Responses provider that builds `instructions`, `input`, and tool definitions from nanobot's existing message flow.
- [x] 2.2 Implement Responses-mode error handling that reports endpoint incompatibility clearly and does not silently fall back to Chat Completions.
- [x] 2.3 Ensure Responses requests preserve deterministic tool definition ordering across repeated calls with the same toolset.

## 3. Prompt caching behavior and observability

- [x] 3.1 Implement stable `prompt_cache_key` generation based on request identity rather than full conversation payloads.
- [x] 3.2 Add support for sending configured `prompt_cache_retention`, including `24h`, on Responses requests.
- [x] 3.3 Parse cached-token usage details from Responses results and carry them through normalized provider usage data.
- [x] 3.4 Update runtime status/reporting output to include cached-token information when available.

## 4. Prompt construction and validation

- [x] 4.1 Refactor OpenAI Responses prompt construction so stable instruction content is separated from volatile input content.
- [x] 4.2 Decide and implement the initial cache-key fingerprint dimensions for model family, tool schema, and deployment/workspace scope.
- [x] 4.3 Add or update tests covering provider routing, custom-base Responses requests, explicit custom opt-in, cache-key stability, usage parsing, and status output.
- [x] 4.4 Run the relevant test suite and targeted verification for OpenAI/Responses provider behavior.

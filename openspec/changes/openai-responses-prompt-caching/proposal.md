## Why

nanobot's direct OpenAI path still uses Chat Completions and Anthropic-style prompt-caching abstractions, so it cannot take advantage of OpenAI's Responses API features or measure cache effectiveness accurately. Supporting OpenAI prompt caching now matters because the project already targets long, tool-heavy prompts where better prefix reuse can reduce latency and cost, especially for OpenAI deployments behind custom proxy base URLs.

## What Changes

- Add a native OpenAI Responses API path for the `openai` provider while preserving support for custom `api_base` endpoints that implement OpenAI-compatible Responses semantics.
- Add an opt-in Responses mode for compatible custom providers instead of assuming every OpenAI-compatible endpoint supports `/v1/responses`.
- Add OpenAI prompt caching controls, including stable `prompt_cache_key` handling and configurable retention with support for `24h` retention.
- Expose prompt-cache usage details, including cached prompt tokens, so nanobot can report whether caching is actually working.
- Reorganize prompt/request construction for OpenAI Responses calls so stable instructions and tool definitions are more cache-friendly than volatile per-turn context.

## Capabilities

### New Capabilities
- `openai-responses-provider`: Use the OpenAI Responses API for OpenAI-backed requests, including custom OpenAI proxy base URLs and opt-in compatibility for custom providers.
- `prompt-cache-observability`: Configure prompt cache behavior and surface cached-token usage so operators can evaluate prompt caching hit rate.

### Modified Capabilities
- None.

## Impact

- Affected code: provider selection and config, OpenAI provider implementations, prompt/request assembly, usage parsing, status/reporting output, and provider tests.
- Affected APIs: OpenAI-facing requests move from Chat Completions to Responses for supported configurations; custom providers gain an explicit compatibility mode rather than implicit behavior.
- Dependencies/systems: OpenAI Python SDK Responses support, OpenAI-compatible proxies that expose `/v1/responses`, and OpenSpec capability specs for the new provider and observability behavior.

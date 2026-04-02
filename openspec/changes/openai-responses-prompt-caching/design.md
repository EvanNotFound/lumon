## Context

nanobot currently routes direct OpenAI traffic through `OpenAICompatProvider`, which builds Chat Completions requests and reuses a prompt-caching abstraction shaped around content-block `cache_control`. That works for Anthropic-style caching and some gateways, but it does not model OpenAI's Responses API, `prompt_cache_key`, `prompt_cache_retention`, or cached-token usage reporting. The change is cross-cutting because it touches provider selection, provider implementations, prompt assembly, usage parsing, config surface, and tests.

The current OpenAI deployment model also allows `provider: openai` with a custom `api_base`, which is how proxy-based OpenAI deployments are configured today. The design therefore needs to preserve OpenAI semantics while avoiding assumptions that every OpenAI-compatible endpoint fully supports `/v1/responses`.

## Goals / Non-Goals

**Goals:**
- Add a native OpenAI Responses path that works with the existing `openai` provider and custom OpenAI proxy base URLs.
- Let `custom` opt into Responses mode explicitly, instead of treating all OpenAI-compatible endpoints as Responses-compatible.
- Support OpenAI prompt caching controls, especially stable `prompt_cache_key` generation and `24h` retention.
- Surface cached-token usage so operators can observe prompt caching hit rate.
- Improve cache hit rate by keeping stable instructions and tool definitions ahead of volatile per-turn context.

**Non-Goals:**
- Rework every OpenAI-compatible gateway or third-party provider to use Responses in this change.
- Introduce silent fallback from Responses to Chat Completions when an endpoint rejects `/v1/responses`.
- Redesign nanobot's entire conversation or memory model beyond what is needed to improve prompt-cache behavior.
- Change Anthropic prompt caching behavior.

## Decisions

### 1. Add a dedicated OpenAI Responses provider instead of branching inside `OpenAICompatProvider`

nanobot should introduce a separate provider implementation for Responses-based OpenAI calls rather than adding large conditional branches to `OpenAICompatProvider`.

Rationale:
- Responses changes request and response shapes, streaming events, tool-call representation, and usage parsing.
- Keeping Chat Completions and Responses separate preserves simpler provider logic and cleaner tests.
- The existing `openai_codex` provider already demonstrates that Responses-style behavior is materially different from the generic compat path.

Alternatives considered:
- Extend `OpenAICompatProvider` with a `responses_mode` branch. Rejected because it would couple two APIs with different parsing and streaming semantics into one increasingly complex class.

### 2. Preserve current transport configuration and separate it from API mode

The new Responses provider should reuse the same OpenAI transport inputs already used today: `api_key`, `api_base`, and `extra_headers`. API mode should be modeled as an explicit capability/config choice rather than inferred from the endpoint alone.

Rationale:
- Users already run `provider: openai` with a custom proxy base URL.
- OpenAI semantics and transport endpoint should remain independent: OpenAI behavior can be routed through a proxy.
- Explicit API mode makes compatibility honest for `custom`, where `/v1/chat/completions` support does not guarantee `/v1/responses` support.

Alternatives considered:
- Treat `openai` and `custom` as identical and auto-upgrade both to Responses. Rejected because many compatible endpoints only partially implement OpenAI APIs.
- Infer Responses support from `api_base`. Rejected because it is brittle and hides operational failures.

### 3. Fail fast instead of silently falling back to Chat Completions

If a provider is configured for Responses mode and the endpoint does not support it, nanobot should return a clear error indicating that the endpoint rejected the Responses API and suggesting Chat Completions mode where appropriate.

Rationale:
- Silent fallback makes cache behavior ambiguous and undermines operator trust.
- This change is explicitly about Responses capabilities and prompt caching, so hidden downgrades would make validation difficult.

Alternatives considered:
- Automatic fallback to Chat Completions. Rejected because it hides whether the intended architecture is actually in use.

### 4. Generate stable prompt cache keys from stable request identity, not full conversation payloads

`prompt_cache_key` should be derived from stable request identity, such as provider family, model family, workspace or deployment scope, and a deterministic tool-schema fingerprint. It should not hash the full message history or the current user turn.

Rationale:
- Hashing the full request causes the key to change every turn, which weakens routing affinity even when large prompt prefixes are identical.
- OpenAI uses the key to improve routing for similar prefixes, so the key should represent a stable bucket rather than per-request content.

Alternatives considered:
- Reuse the current Codex-style full-message hash. Rejected because it is too volatile for multi-turn cache reuse.
- Use a global shared key for all traffic. Rejected because it risks hot-key contention and loses useful separation across deployments or toolsets.

### 5. Re-layer OpenAI prompt construction around stable instructions first

For Responses calls, nanobot should separate stable instructions from volatile input. Stable identity, workspace bootstrap, and stable skill guidance should live in `instructions`; conversation history, retrieved memory, and the current user turn should remain in `input`, with the most volatile content last. Tool definitions must be emitted in deterministic order.

Rationale:
- OpenAI prompt caching rewards exact prefix stability, especially near the first routed prefix.
- The current system prompt inserts volatile memory before some otherwise reusable material, reducing the reusable cached prefix.

Alternatives considered:
- Keep the current merged system prompt and only add cache parameters. Rejected because it would technically enable caching but leave significant hit-rate gains untapped.

### 6. Treat cached-token usage as a first-class metric

Usage parsing should preserve `cached_tokens` and related prompt-token details from Responses results, and agent/runtime status reporting should expose those fields so operators can verify that caching is working.

Rationale:
- Without cache metrics, this change cannot be validated in practice.
- Cached-token visibility is the feedback loop needed to tune prompt shape and cache-key granularity.

Alternatives considered:
- Keep raw usage internal to provider logs only. Rejected because nanobot already surfaces token usage to operators, and this feature needs visible outcomes.

## Risks / Trade-offs

- [Responses support varies across OpenAI-compatible endpoints] -> Require explicit opt-in for `custom` and fail clearly when an endpoint rejects Responses calls.
- [Prompt re-layering could change model behavior slightly] -> Preserve instruction content as much as possible and validate behavior with provider-focused tests.
- [Cache-key granularity may be too broad or too narrow] -> Start with a stable but scoped key and expose cache metrics so tuning can be data-driven.
- [A separate provider adds maintenance surface] -> Keep the provider boundary narrow and share normalization/helpers where request semantics truly overlap.

## Migration Plan

1. Add the new Responses-capable provider implementation and provider/config routing needed to select it.
2. Preserve existing OpenAI credentials, base URL, and headers so current proxy-based deployments only need an API-mode/config change.
3. Add cached-token parsing and status/reporting support before switching defaults so behavior can be measured.
4. Update tests for provider selection, request construction, usage parsing, and cache-key stability.
5. Roll back by switching affected configurations back to Chat Completions mode if a proxy or endpoint does not support Responses correctly.

## Open Questions

- Should `provider: openai` default to Responses mode immediately, or should the change ship with explicit opt-in first?
- Which exact dimensions should be included in the stable `prompt_cache_key` fingerprint: workspace path, model family, tool schema digest, and/or active skill set?
- How much of the current skill and memory context should move from system/instructions into later input without harming response quality?

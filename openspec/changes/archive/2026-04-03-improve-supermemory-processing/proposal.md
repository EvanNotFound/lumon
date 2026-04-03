## Why

Nanobot's Supermemory backend currently summarizes a completed exchange and then relies on Supermemory to extract durable memories from the ingested text. This creates avoidable memory loss for high-value exchanges because exact user-requested memories can be over-compressed before Supermemory processes them, while raw-turn ingestion increases token cost and noise.

## What Changes

- Improve the Supermemory summary pipeline so ingested records are optimized for downstream memory extraction instead of generic human-readable summarization.
- Refine the `skip` / `summary` / `both` memory decision policy so most exchanges use concise summaries, while high-fidelity exchanges still keep a raw-turn fallback.
- Add guidance and configuration support for Supermemory extraction context so Nanobot can better steer durable memory capture without turning the backend into a raw transcript store.
- Preserve exact literals that are easy to lose during summarization, such as URLs, handles, IDs, repo names, and short key-value mappings.

## Capabilities

### New Capabilities
- `supermemory-processing`: Defines how Nanobot prepares, classifies, and sends durable conversation memory to Supermemory for extraction and later retrieval.

### Modified Capabilities

None.

## Impact

- Affected code: `nanobot/agent/memory/__init__.py`, `nanobot/agent/memory/supermemory.py`, `nanobot/config/schema.py`, and related tests.
- Affected systems: post-turn memory decision flow, Supermemory ingestion payloads, retrieved memory quality, and Supermemory configuration.
- External considerations: token-ingestion cost, extraction accuracy, and compatibility with Supermemory organizational and entity context features.

# ADR-049: Migrate from OpenAI/GenAI Plugin Embeddings to HuggingFace Inference API

**Status:** Accepted
**Date:** 2026-03-12
**Deciders:** MCF

## Context

SKUEL generated embeddings via the Neo4j GenAI plugin, which called OpenAI's `text-embedding-3-small` (1536 dims) from within Cypher using `genai.vector.encode()`. This created dependencies on both the GenAI plugin and OpenAI's embedding API.

Problems with the GenAI plugin approach:
- Required OpenAI API key passed into Neo4j container
- Plugin added Docker complexity (`NEO4J_PLUGINS`, procedure allowlists)
- The GenAI plugin was used exclusively for embeddings — `ai.text.completion()`/`ai.text.chat()` were never used in production code
- LLM calls already go through Python-side `LLMService`
- Complicated the AuraDB migration path (plugin availability varies)

## Decision

Replace the Neo4j GenAI plugin + OpenAI embeddings with HuggingFace Inference API using `BAAI/bge-large-en-v1.5`.

### Why This Model

The classic `sentence-transformers/all-mpnet-base-v2` (768 dims) is solid but not top-tier on modern retrieval benchmarks. `BAAI/bge-large-en-v1.5` (1024 dims) is the strongest well-established choice for retrieval quality — and it's available on HuggingFace Inference API.

It's a sentence-transformers-compatible model, but we use `huggingface_hub.InferenceClient` (not the `sentence-transformers` package) because we want API-hosted inference, not local model loading. This keeps the deployment lightweight — no torch, no GPU, just HTTP calls.

### New Stack

| Component | Before | After |
|-----------|--------|-------|
| Embedding model | OpenAI text-embedding-3-small | BAAI/bge-large-en-v1.5 (sentence-transformers-compatible) |
| Dimensions | 1536 | 1024 |
| Client | Neo4j GenAI plugin (Cypher-side) | `huggingface_hub.InferenceClient` (Python-side) |
| Inference | OpenAI API | HuggingFace Inference API (serverless) |
| Plugin dependency | GenAI plugin required | No plugin needed |
| API key | OPENAI_API_KEY (in Neo4j container) | HF_API_TOKEN (in app container) |
| Version | v1 | v2 |

### What Changed

- `Neo4jGenAIEmbeddingsService` → `HuggingFaceEmbeddingsService` (same public interface)
- Canonical import: `from core.services.embeddings_service import HuggingFaceEmbeddingsService`
- Old import path (`core.services.neo4j_genai_embeddings_service`) re-exports for backward compat
- `GenAIConfig` → `EmbeddingConfig` in unified_config.py (alias preserved)
- Docker: GenAI plugin removed, `OPENAI_API_KEY` removed from Neo4j container
- Vector indexes: dimension 1536 → 1024 (must be recreated)
- All existing embeddings cleared (must be regenerated with new model)

### What Didn't Change

- `Neo4jVectorSearchService` — uses native `db.index.vector.queryNodes()`, model-agnostic
- `embedding_text_builder.py` — text extraction is provider-independent
- `EmbeddingBackgroundWorker` — calls same interface
- All 12 AI services — receive `embeddings_service` via DI, interface unchanged
- `INTELLIGENCE_TIER=core` still skips embeddings entirely

## Consequences

### Positive
- Removes OpenAI dependency for embeddings (LLM calls still use OpenAI via LLMService)
- Simplifies Docker config (no GenAI plugin, no OPENAI_API_KEY in Neo4j container)
- Simplifies AuraDB migration path (no plugin to configure)
- Open-weight, sentence-transformers-compatible model — can move to local inference via `sentence-transformers` package later if needed (same model, different client)
- Top-tier retrieval quality on MTEB benchmarks (bge-large-en-v1.5 outperforms all-mpnet-base-v2)

### Negative
- One-time migration: must recreate vector indexes and re-embed all entities
- Slightly lower dimensionality (1024 vs 1536) — quality is actually higher per benchmarks
- HuggingFace Inference API is a new external dependency

### Migration

Run: `uv run python scripts/migrations/migrate_to_huggingface_embeddings.py`

This drops old indexes, clears old embeddings, then re-embed via `generate_embeddings_batch.py`.

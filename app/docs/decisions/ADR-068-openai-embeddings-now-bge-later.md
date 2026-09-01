---
updated: 2026-09-01
---

# ADR-068: OpenAI Embeddings Now, BGE Long-Term — Behind One Provider Chokepoint

**Status:** Accepted
**Date:** 2026-06-10
**Deciders:** MCF

## Context

ADR-049 (March 2026) decided to replace the Neo4j GenAI plugin + OpenAI embeddings with the
HuggingFace Inference API using `BAAI/bge-large-en-v1.5` (1024 dims). The code migration shipped,
but the June 2026 infrastructure review found the data migration never ran:

- The live database had **zero embeddings** on any node and zero ContentChunks.
- The live vector indexes were still the **1536-dim leftovers** from the pre-ADR-049 OpenAI era.
  `CREATE VECTOR INDEX IF NOT EXISTS` never alters an existing index, and Neo4j vector indexes
  silently ignore vectors whose dimension doesn't match — so BGE vectors written through the
  ADR-049 stack would have been **unsearchable** without anyone noticing.
- `INTELLIGENCE_TIER=core` kept the whole pipeline dormant, so none of this had surfaced.

Meanwhile the direction (2026-06-10) is: **get embeddings running now on OpenAI** (the key and SDK
are already FULL-tier requirements for chat), while **BGE remains the liked long-term option**.

Two smaller debts surfaced in the same review:

- **Dual version source:** the service wrote `EMBEDDING_VERSION` (constant) while the background
  worker wrote `config.genai.embedding_version` (env) — same default, two sources of truth.
- **Dead config:** `EmbeddingConfig` (`config.genai`) carried provider/model/dimension/enabled
  fields that nothing in the live pipeline read (the real toggle is `INTELLIGENCE_TIER`,
  ADR-043), plus one script reading a field that didn't even exist.

## Decision

### 1. OpenAI `text-embedding-3-small` at 1024 dims is the wired provider

A new `OpenAIEmbeddingAdapter` (`adapters/external/embeddings/openai_adapter.py`) implements the
existing `EmbeddingClientOperations` port. We request **1024 dims via the API `dimensions`
parameter** (Matryoshka truncation; native is 1536) so the Neo4j vector indexes stay
dimension-compatible with the staged BGE swap — the index migration happens once, not twice.

### 2. One provider chokepoint: `create_embedding_client()`

`adapters/external/embeddings/factory.py` is THE single place that decides the provider. The
bootstrap composition root and every standalone script construct their inference client there.
The future BGE swap is a one-line change in that factory.

The `HuggingFaceEmbeddingAdapter` (ADR-049) **stays as staged code** — it is the BGE long-term
path, not dead code (One Path Forward: delete the abandoned, never the staged).

### 3. The port owns model facts; the service is provider-agnostic

`EmbeddingClientOperations` gains `max_input_chars` alongside `model`/`dimension` — each adapter
knows its own model's input budget (BGE: 2000 chars ≈ 512 tokens; OpenAI: 24000 chars ≈ 6k
tokens). `HuggingFaceEmbeddingsService` is renamed **`EmbeddingsService`** and reads everything
off the port; the BGE constants moved into the HF adapter.

### 4. One version source: `EMBEDDING_VERSION` in `core/services/embeddings_service.py`

Bumped to **v3** (history: v1 = OpenAI @1536 via GenAI plugin; v2 = BGE @1024 via HF, never
backfilled; v3 = OpenAI @1024). The background worker now stores through
`EmbeddingsService.store_embedding_with_metadata()` instead of reaching into the backend with a
config-sourced version — version/model metadata has exactly one writer.

`EmbeddingConfig` / `config.genai` is **deleted** (the `GENAI_*` / `EMBEDDING_*` env vars with
it). Provider, model, and dimension live in code; the only runtime toggle is
`INTELLIGENCE_TIER`.

### 5. Vector indexes recreated at 1024

`scripts/create_vector_indexes.py` gained `--recreate` (drop + create — required for any
dimension change) and its defaults were fixed (CLI default was 1536 while the function default
was 1024 — the likely origin of the stale live indexes; labels list contained nonexistent
`Curriculum`/`LpStep`). The live indexes (`entity`, `contentchunk`, `task`, `goal`) are now
1024/COSINE.

### 6. Backfill goes through the service

`scripts/generate_embeddings_batch.py` now builds text via `build_embedding_text()` (the same
field maps as the event-driven path) and stores via `EmbeddingsService` — so backfilled nodes
carry the same version/model metadata the worker writes. Previously it wrote raw properties with
no `embedding_version`, which the cache layer would have treated as stale forever.

## Consequences

- FULL tier no longer needs `HF_API_TOKEN`; `OPENAI_API_KEY` (already required for chat) covers
  embeddings too.
- All embeddings must be (re)generated as v3 — trivial today (the corpus had zero embeddings).
- A future BGE swap = new factory line + `EMBEDDING_VERSION` bump + re-embed. Indexes stay.
- `scripts/migrations/migrate_to_huggingface_embeddings.py` deleted (superseded one-shot that <!-- historical -->
  never ran; `--recreate` replaces its index mechanics).
- ADR-049 is **superseded in its provider choice** but its architecture decisions stand:
  Python-side embedding generation, no Neo4j plugin, SDK behind the hexagonal boundary (ADR-063).

## Follow-ups (deliberately not in this change)

- The 5 curriculum/resource `*EmbeddingRequested` publish events (Ku, PathStep, LearningPath,
  Exercise, Resource) remain PLANNED (`scripts/detect_bloat.py`) — wiring them is a separate
  decision now that the backfill script covers the existing corpus.
- All embedding publishes are create-only; no domain re-embeds on update.
- ~~The worker re-queues failed batches without an attempt cap (only a 1000-item queue cap).~~
  Resolved (2026-06-10, follow-up PR): per-item generation + bounded retries
  (`MAX_GENERATION_ATTEMPTS`, drop-and-log with a `status="dropped"` metric).

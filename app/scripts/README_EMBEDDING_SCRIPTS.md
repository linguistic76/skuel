# Embedding Scripts - Quick Reference
**Command-line tools for vector search setup and maintenance**

---

## Overview

This directory contains scripts for managing embeddings and vector search in SKUEL.
Embeddings are generated Python-side via `EmbeddingsService` behind the
`create_embedding_client()` provider chokepoint — OpenAI `text-embedding-3-small` at
1024 dimensions (ADR-068; end-state is BGE per ADR-083). No Neo4j plugin is required.

1. **create_vector_indexes.py** — create, recreate, and verify vector indexes
2. **generate_embeddings_batch.py** — backfill and freshness-repair embeddings

---

## 1. Create Vector Indexes

**Purpose:** Create vector indexes for semantic similarity search

**Prerequisites:**
- Neo4j running (Docker or AuraDB) with connection env set (`NEO4J_URI`, credentials)
- No API key needed — index creation is pure Neo4j DDL

At bootstrap (FULL tier), `Neo4jSchemaManager.sync_vector_indexes()` auto-creates the
`Entity`, `ContentChunk`, `ReferenceChunk`, `Ku`, and `PathStep` indexes. This script is
for manual runs, the per-label `Task`/`Goal` optimization indexes, and dimension changes.

### Basic Usage

```bash
# Create indexes for all priority labels
# (Entity, ContentChunk, ReferenceChunk, Task, Goal, Ku, PathStep)
uv run python scripts/create_vector_indexes.py

# Verify existing vector indexes
uv run python scripts/create_vector_indexes.py --verify
```

### Advanced Usage

```bash
# Create indexes for specific labels only
uv run python scripts/create_vector_indexes.py --labels Ku Task

# Drop + recreate — REQUIRED when the embedding dimension changes
# (CREATE VECTOR INDEX IF NOT EXISTS never alters an existing index, and
# Neo4j silently ignores vectors whose dimension doesn't match the index)
uv run python scripts/create_vector_indexes.py --recreate
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--labels` | Entity labels to create indexes for | All 7 priority labels |
| `--dimension` | Vector dimension | `1024` (`EmbeddingGeometry.DIMENSION` — frozen, ADR-083) |
| `--similarity` | Similarity function (`cosine`/`euclidean`/`dot`) | `cosine` |
| `--recreate` | Drop each index before creating | `False` |
| `--verify` | Verify existing indexes instead of creating | `False` |

---

## 2. Generate Embeddings (Batch)

**Purpose:** Backfill embeddings for existing content and repair stale ones. Routine
freshness is the event-driven worker's job (ADR-074); this script is the backfill and
audit backstop — and THE freshness mechanism after one-shot script syncs
(`./dev vault-sync`), whose events die with the script process.

**Prerequisites:**
- `OPENAI_API_KEY` in the keychain (`scripts/migrate_secrets_to_keychain.py`) or env
- Vector indexes created (see above)

### Basic Usage

```bash
# Default mode: embed nodes that have NO embedding yet (coverage backfill)
uv run python scripts/generate_embeddings_batch.py

# One label only
uv run python scripts/generate_embeddings_batch.py --label Ku

# Re-embed drifted/version-mismatched nodes (skips unchanged text via content hash)
uv run python scripts/generate_embeddings_batch.py --stale
```

After `./dev vault-sync`, run **both** the default mode (new nodes) and `--stale`
(drifted nodes).

### Advanced Usage

```bash
# Full-corpus freshness audit, timestamp-free: check EVERY embedded node's stored
# hash/source text against its current text; re-embed only real mismatches
uv run python scripts/generate_embeddings_batch.py --audit

# One-shot hash rollout: stamp embedding_text_hash without re-embedding (zero API calls)
uv run python scripts/generate_embeddings_batch.py --stamp-hashes

# Test with limited batches
uv run python scripts/generate_embeddings_batch.py --label Ku --max-batches 2
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--label` | Specific label to process (e.g., Ku, PathStep, Task, ContentChunk) | All embeddable labels |
| `--batch-size` | Entities per batch | `25` |
| `--max-batches` | Maximum batches (for testing) | `None` (all) |
| `--stale` | Re-embed drifted/version-mismatched nodes instead of missing ones | `False` |
| `--audit` | Timestamp-free full-corpus hash sweep; re-embed real mismatches only | `False` |
| `--stamp-hashes` | Write `embedding_text_hash` onto embedded nodes, no re-embedding | `False` |

### When to Run

- **First-time setup / new deployment:** default mode after creating indexes
- **After `./dev vault-sync`:** default mode + `--stale`
- **After an `EMBEDDING_VERSION` bump (provider/model swap):** `--stale` re-embeds the corpus
- **Suspected silent staleness (raced stores, missed publishes):** `--audit`

---

## Common Workflows

### Initial Setup (First Time)

```bash
# 1. Ensure OPENAI_API_KEY is in the keychain and INTELLIGENCE_TIER=full in .env

# 2. Create vector indexes (bootstrap covers 5; this adds Task/Goal too)
uv run python scripts/create_vector_indexes.py

# 3. Verify indexes
uv run python scripts/create_vector_indexes.py --verify

# 4. Backfill embeddings for existing content
uv run python scripts/generate_embeddings_batch.py

# 5. Test semantic search
uv run pytest tests/integration/test_vector_search.py -v
```

### Dimension / Provider Change (ADR-level decision — see ADR-083)

```bash
# 1. Recreate indexes ONLY if the dimension changed (a same-dimension provider
#    swap, e.g. OpenAI → BGE at 1024, keeps the indexes)
uv run python scripts/create_vector_indexes.py --recreate

# 2. Re-embed the corpus (the EMBEDDING_VERSION bump makes everything stale)
uv run python scripts/generate_embeddings_batch.py --stale
```

---

## Troubleshooting

### "No vector indexes found"

```bash
uv run python scripts/create_vector_indexes.py
```

### "OPENAI_API_KEY is required to construct OpenAIEmbeddingAdapter"

Add the key to the keychain (`scripts/migrate_secrets_to_keychain.py`) or env. Index
creation works without it; embedding generation does not.

### "Embedding dimension mismatch" / vectors not searchable

The index dimension must match the adapter's (1024). Neo4j silently ignores
wrong-dimension vectors, so a mismatch looks like "search returns nothing":

```bash
uv run python scripts/create_vector_indexes.py --recreate
uv run python scripts/generate_embeddings_batch.py --stale
```

**Documentation:** See `/docs/development/EMBEDDINGS_SETUP.md`

---

## See Also

- **Setup Guide:** `/docs/development/EMBEDDINGS_SETUP.md`
- **Version upgrade runbook:** `/docs/operations/EMBEDDING_VERSION_UPGRADE.md`
- **Search Architecture:** `/docs/architecture/SEARCH_ARCHITECTURE.md`
- **Decisions:** `/docs/decisions/ADR-068-openai-embeddings-now-bge-later.md`,
  `/docs/decisions/ADR-083-qwen-bge-end-state-commitment.md`,
  `/docs/decisions/ADR-074-post-persist-embedding-events.md`

---

**Last Updated:** 2026-07-24
**Embedding Backend:** OpenAI Embeddings API (`text-embedding-3-small`, 1024 dims via the API `dimensions` param — ADR-068)
**Status:** Production Ready

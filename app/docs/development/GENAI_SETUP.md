---
title: Embeddings Setup
---
# Embeddings Setup (OpenAI Embeddings API)

**Last Updated:** 2026-06-10
**Status:** Production Ready

---

## Overview

SKUEL generates embeddings via the OpenAI Embeddings API using `text-embedding-3-small` at
**1024 dimensions** (requested via the API `dimensions` parameter; native is 1536). Embeddings
are generated Python-side — no Neo4j plugin required.

**See:** [ADR-068: OpenAI Embeddings Now, BGE Long-Term](/docs/decisions/ADR-068-openai-embeddings-now-bge-later.md)

### Architecture

| Component | Choice | Why |
|-----------|--------|-----|
| **Model** | `text-embedding-3-small` @1024 dims | Key + SDK already FULL-tier requirements (chat); 1024 keeps indexes compatible with the staged BGE swap |
| **Client** | `openai.AsyncOpenAI` behind `EmbeddingClientOperations` | Vendor SDK below the hexagonal boundary (ADR-063) |
| **Provider chokepoint** | `create_embedding_client()` in `adapters/external/embeddings/factory.py` | One-line swap point for the BGE long-term direction |
| **API key** | `OPENAI_API_KEY` (keychain or env) | Same credential as the LLM service |

**BGE long-term:** `HuggingFaceEmbeddingAdapter` (`BAAI/bge-large-en-v1.5`, also 1024 dims,
ADR-049) stays in the codebase as the staged long-term provider. Swapping = one line in the
factory + an `EMBEDDING_VERSION` bump + re-embed. Vector indexes stay (same dimension).

```
User Query → Python (EmbeddingsService) → OpenAI Embeddings API → Embedding
                ↓
          Neo4j Node (n.embedding) → Vector Index → Similarity Search → Results
```

### Key Features

- **Serverless inference:** No GPU, no model loading — just HTTP calls
- **No plugin dependency:** No Neo4j GenAI plugin needed
- **Vector similarity search:** Find semantically similar content across domains
- **Graceful degradation:** Application works without embeddings (`INTELLIGENCE_TIER=core`)
- **Version tracking:** `EMBEDDING_VERSION` (constant `"v3"` in
  `core/services/embeddings_service.py`) on every node; stale embeddings auto-regenerated

---

## Prerequisites

### Required

- **OpenAI API key** — in the keychain (`scripts/migrate_secrets_to_keychain.py`) or env
- **Neo4j** running (Docker or AuraDB)
- **uv** (for dependency management)

---

## Quick Start

### 1. Configure Environment

```bash
# .env — the only embedding-related toggle
INTELLIGENCE_TIER=full   # "full" enables embeddings, "core" disables
```

Provider, model, and dimension live in code (`adapters/external/embeddings/`) — there are no
embedding env vars. `OPENAI_API_KEY` comes from the keychain (preferred) or env.

### 2. Install Dependencies

```bash
cd /home/mike/skuel/app
uv sync
```

The `openai` package is included in project dependencies.

### 3. Create Vector Indexes

Vector indexes (`Entity`, `ContentChunk` at 1024 dims) are **automatically created at bootstrap**
when `INTELLIGENCE_TIER=full` (via `Neo4jSchemaManager.sync_vector_indexes()`). Full-text indexes
for keyword search are always created regardless of tier (via `sync_fulltext_indexes()`).

To create them manually, or to add the per-label `Task`/`Goal` optimization indexes:

```bash
uv run python scripts/create_vector_indexes.py
```

**Changing embedding dimension requires `--recreate`** — `CREATE VECTOR INDEX IF NOT EXISTS`
never alters an existing index, and Neo4j vector indexes silently ignore vectors of the wrong
dimension:

```bash
uv run python scripts/create_vector_indexes.py --recreate
```

### 4. Backfill Existing Entities

```bash
uv run python scripts/generate_embeddings_batch.py            # all embeddable labels
uv run python scripts/generate_embeddings_batch.py --label Ku # one label
```

### 5. Test Semantic Search

```bash
uv run pytest tests/integration/test_vector_search.py -v
```

---

## How It Works

### Embedding Generation

```python
from adapters.external.embeddings import create_embedding_client
from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
from core.services.embeddings_service import EmbeddingsService

# Composition root (bootstrap does this at FULL tier)
service = EmbeddingsService(
    backend=EmbeddingsBackend(executor=query_executor),
    embedding_client=create_embedding_client(),
)

# Generate embedding
result = await service.create_embedding("Python programming language")
# Result.ok([0.123, 0.456, ...])  # 1024-dim vector
```

### Version Tracking

Every embedding stored on a Neo4j node includes metadata:

```
n.embedding = [0.123, ...]          # 1024-dim vector
n.embedding_version = "v3"          # Tracks model/parameter version
n.embedding_model = "text-embedding-3-small"
n.embedding_updated_at = datetime() # When generated
n.embedding_source_text = "..."     # Source text
```

Version history: v1 = OpenAI @1536 via the GenAI plugin; v2 = BGE @1024 via HF (never
backfilled); v3 = OpenAI @1024 (ADR-068). The `get_or_create_embedding()` method checks version
before returning cached embeddings — stale versions are automatically regenerated.

### Cache-First Strategy

```
get_or_create_embedding(uid, label, text)
  → check_version_compatibility(uid, label)
    → is_current? Return cached embedding (no API call)
    → stale/missing? Generate new → store with metadata → return
```

---

## Graceful Degradation

SKUEL works with or without embeddings.

| Feature | With Embeddings | Without Embeddings |
|---------|----------------|-------------------|
| **Basic CRUD** | Full support | Full support |
| **Keyword Search** | Available | Primary method |
| **Semantic Search** | Primary method | Unavailable |
| **Vector Similarity** | Available | Falls back to keyword |
| **Related Content** | Semantic | Graph-based only |

### Testing Without API Calls

```bash
# Disable embeddings
INTELLIGENCE_TIER=core uv run python main.py

# All tests use mock embeddings — no API calls
uv run pytest tests/ -v
```

---

## Troubleshooting

### "OPENAI_API_KEY is required to construct OpenAIEmbeddingAdapter"

Add the key to the keychain (`scripts/migrate_secrets_to_keychain.py`) or env, or run with
`INTELLIGENCE_TIER=core` to skip embedding services.

### 401 AuthenticationError on embedding calls

The stored key is invalid or revoked — generate a fresh key at https://platform.openai.com and
update the keychain entry.

### "Embedding dimension mismatch"

The vector index dimension must match the adapter's `dimension` (1024). After any dimension
change:

```bash
uv run python scripts/create_vector_indexes.py --recreate
uv run python scripts/generate_embeddings_batch.py
```

### "Vector index not found"

```bash
uv run python scripts/create_vector_indexes.py
```

---

## See Also

- [ADR-068: OpenAI Embeddings Now, BGE Long-Term](/docs/decisions/ADR-068-openai-embeddings-now-bge-later.md)
- [ADR-049: HuggingFace Embeddings Migration](/docs/decisions/ADR-049-huggingface-embeddings-migration.md) (superseded in part)
- [ADR-063: LLM/Embeddings SDK Ports](/docs/decisions/ADR-063-llm-embeddings-sdk-ports.md)
- [Graceful Degradation Architecture](/docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md)
- [Search Architecture](/docs/architecture/SEARCH_ARCHITECTURE.md)
- [AuraDB Migration Guide](/docs/deployment/AURADB_MIGRATION_GUIDE.md)

---

**Last Updated:** 2026-06-10

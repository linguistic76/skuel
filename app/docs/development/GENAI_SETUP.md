---
title: Embeddings Setup
---
# Embeddings Setup (HuggingFace Inference API)

**Last Updated:** 2026-03-12
**Status:** Production Ready

---

## Overview

SKUEL generates embeddings via HuggingFace Inference API using `BAAI/bge-large-en-v1.5` (1024 dimensions). Embeddings are generated Python-side — no Neo4j plugin required.

**See:** [ADR-049: HuggingFace Embeddings Migration](/docs/decisions/ADR-049-huggingface-embeddings-migration.md)

### Architecture

| Component | Choice | Why |
|-----------|--------|-----|
| **Model** | `BAAI/bge-large-en-v1.5` (1024 dims) | Top-tier retrieval quality on MTEB benchmarks. Sentence-transformers-compatible. |
| **Client** | `huggingface_hub.InferenceClient` | API-hosted inference — no torch, no GPU, no local model loading. NOT `sentence-transformers` (that's for local inference). |
| **API key** | `HF_API_TOKEN` env var | Free tier available at huggingface.co |

**Why not `all-mpnet-base-v2`?** The classic sentence-transformers default (768 dims) is solid but not top-tier on modern retrieval benchmarks. `bge-large-en-v1.5` is the strongest well-established choice — and it's available on HuggingFace Inference API.

**Future flexibility:** Since `bge-large-en-v1.5` is sentence-transformers-compatible, we can move to local inference later by swapping `InferenceClient` for the `sentence-transformers` package (same model, different client).

```
User Query → Python (HuggingFaceEmbeddingsService) → HF Inference API → Embedding
                ↓
          Neo4j Node (n.embedding) → Vector Index → Similarity Search → Results
```

### Key Features

- **Serverless Inference:** No GPU, no model loading — just HTTP calls to HuggingFace
- **No Plugin Dependency:** No Neo4j GenAI plugin needed
- **Vector Similarity Search:** Find semantically similar content across domains
- **Graceful Degradation:** Application works without embeddings (`INTELLIGENCE_TIER=core`)
- **Version Tracking:** `EMBEDDING_VERSION=v2` on every node, stale embeddings auto-regenerated

---

## Prerequisites

### Required

- **HuggingFace API Token** — free at https://huggingface.co/settings/tokens
- **Neo4j** running (Docker or AuraDB)
- **uv** (for dependency management)

### Verify Prerequisites

```bash
uv --version       # Should be 1.7+
python --version   # Should be 3.12+
```

---

## Quick Start

### 1. Configure Environment

**Add to `/home/mike/skuel/app/.env`:**

```bash
# ============================================================================
# Embeddings (HuggingFace Inference API)
# ============================================================================
HF_API_TOKEN=hf_your-huggingface-token

# Optional overrides (defaults shown)
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
EMBEDDING_DIMENSION=1024
EMBEDDING_VERSION=v2
```

**Get HuggingFace Token:**
1. Visit https://huggingface.co/settings/tokens
2. Create new token (read access is sufficient)
3. Copy the token

### 2. Install Dependencies

```bash
cd /home/mike/skuel/app
uv sync
```

The `huggingface-hub` package is included in project dependencies.

### 3. Create Vector Indexes

```bash
uv run python scripts/create_vector_indexes.py
```

### 4. Test Semantic Search

```bash
uv run pytest tests/integration/test_vector_search.py -v
```

---

## Configuration

### Environment Variables

```bash
# Required
HF_API_TOKEN=hf_...              # HuggingFace API token

# Optional (defaults shown)
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5   # HuggingFace model
EMBEDDING_DIMENSION=1024                   # Vector dimensions
EMBEDDING_VERSION=v2                       # Version tag on nodes

# Intelligence tier toggle
INTELLIGENCE_TIER=full   # "full" enables embeddings, "core" disables
```

### Docker Setup

The `docker-compose.yml` passes `HF_API_TOKEN` to the app container:

```yaml
services:
  skuel-app:
    environment:
      HF_API_TOKEN: ${HF_API_TOKEN:-}
```

No Neo4j plugin configuration needed for embeddings.

---

## How It Works

### Embedding Generation

```python
from core.services.embeddings_service import HuggingFaceEmbeddingsService

# Service initialized at bootstrap with HF_API_TOKEN
service = HuggingFaceEmbeddingsService(executor=query_executor)

# Generate embedding
result = await service.create_embedding("Python programming language")
# Result.ok([0.123, 0.456, ...])  # 1024-dim vector
```

### Version Tracking

Every embedding stored on a Neo4j node includes metadata:

```
n.embedding = [0.123, ...]          # 1024-dim vector
n.embedding_version = "v2"          # Tracks model version
n.embedding_model = "BAAI/bge-large-en-v1.5"
n.embedding_updated_at = datetime() # When generated
n.embedding_source_text = "..."     # Source text
```

The `get_or_create_embedding()` method checks version before returning cached embeddings. Stale (v1) embeddings are automatically regenerated.

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

### "HF_API_TOKEN not set - embeddings will fail"

Set `HF_API_TOKEN` in `.env`. Get a token at https://huggingface.co/settings/tokens.

### "Embedding dimension mismatch"

Ensure `EMBEDDING_DIMENSION=1024` matches the model. If you previously used a different model (e.g., OpenAI text-embedding-3-small at 1536 dims), run the migration script:

```bash
uv run python scripts/migrations/migrate_to_huggingface_embeddings.py
```

### "Vector index not found"

```bash
uv run python scripts/create_vector_indexes.py
```

---

## Migration from GenAI Plugin (v1 → v2)

If migrating from the old OpenAI/GenAI plugin setup:

```bash
# Drops old indexes, clears old embeddings, ready for re-embedding
uv run python scripts/migrations/migrate_to_huggingface_embeddings.py

# Re-generate all embeddings with new model
uv run python scripts/generate_embeddings_batch.py
```

**See:** [ADR-049](/docs/decisions/ADR-049-huggingface-embeddings-migration.md) for full migration details.

---

## See Also

- [ADR-049: HuggingFace Embeddings Migration](/docs/decisions/ADR-049-huggingface-embeddings-migration.md)
- [Graceful Degradation Architecture](/docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md)
- [Search Architecture](/docs/architecture/SEARCH_ARCHITECTURE.md)
- [AuraDB Migration Guide](/docs/deployment/AURADB_MIGRATION_GUIDE.md)

---

**Last Updated:** 2026-03-12

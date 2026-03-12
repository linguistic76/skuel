# Embedding Scripts - Quick Reference
**Command-line tools for vector search setup and maintenance**

---

## Overview

This directory contains scripts for managing embeddings and vector search in SKUEL.
Embeddings are generated Python-side via `HuggingFaceEmbeddingsService` using the
HuggingFace Inference API with `BAAI/bge-large-en-v1.5` (1024 dimensions). No
Neo4j plugin is required.

1. **create_vector_indexes.py** - Create and verify vector indexes
2. **generate_embeddings_batch.py** - Generate embeddings for existing content

---

## 1. Create Vector Indexes

**Purpose:** Create vector indexes for semantic similarity search

**Prerequisites:**
- Neo4j 5.x+ running (Docker or AuraDB)
- `HF_API_TOKEN` environment variable set
- `INTELLIGENCE_TIER=full` in `.env`

### Basic Usage

```bash
# Create indexes for all priority entities (Ku, Task, Goal, LpStep)
uv run python scripts/create_vector_indexes.py

# Expected output:
# ✅ Vector index creation complete
#    Created: 4
#    Failed: 0
# Created indexes:
#   ✅ ku_embedding_idx
#   ✅ task_embedding_idx
#   ✅ goal_embedding_idx
#   ✅ lpstep_embedding_idx
```

### Advanced Usage

```bash
# Create indexes for specific entities only
uv run python scripts/create_vector_indexes.py --labels Ku Task

# Use different embedding dimensions
uv run python scripts/create_vector_indexes.py --dimension 1024

# Use different similarity function
uv run python scripts/create_vector_indexes.py --similarity euclidean
```

### Verify Indexes

```bash
# Verify existing vector indexes
uv run python scripts/create_vector_indexes.py --verify

# Expected output:
# ✅ Found 4 vector indexes
#   Index: ku_embedding_idx
#     Labels: ['Ku']
#     Properties: ['embedding']
#   ...
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--labels` | Entity labels to create indexes for | `Ku Task Goal LpStep` |
| `--dimension` | Vector dimension | `1024` (BAAI/bge-large-en-v1.5) |
| `--similarity` | Similarity function | `cosine` |
| `--verify` | Verify existing indexes instead of creating | `False` |

### When to Run

- **First time setup:** After configuring `HF_API_TOKEN` and `INTELLIGENCE_TIER=full`
- **Adding new entities:** When adding embedding fields to new entity types
- **After Neo4j version upgrade:** To ensure indexes are compatible

---

## 2. Generate Embeddings (Batch)

**Purpose:** Generate embeddings for existing content that doesn't have embeddings yet

**Prerequisites:**
- `HF_API_TOKEN` environment variable set
- `INTELLIGENCE_TIER=full` in `.env`
- Vector indexes created (see above)
- Entities exist in Neo4j

### Basic Usage

```bash
# Generate embeddings for all Knowledge Units
uv run python scripts/generate_embeddings_batch.py --label Ku

# Expected output:
# Processing batch 1/10...
# ✅ Generated embeddings for 25 nodes
# Processing batch 2/10...
# ✅ Generated embeddings for 25 nodes
# ...
# Total processed: 250 nodes
```

### Advanced Usage

```bash
# Test with limited batches (dry run)
uv run python scripts/generate_embeddings_batch.py --label Ku --max-batches 2

# Process all priority entities
uv run python scripts/generate_embeddings_batch.py --label Ku
uv run python scripts/generate_embeddings_batch.py --label Task
uv run python scripts/generate_embeddings_batch.py --label Goal
uv run python scripts/generate_embeddings_batch.py --label LpStep
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--label` | Entity label to process | **Required** |
| `--max-batches` | Maximum batches (for testing) | `None` (all) |
| `--batch-size` | Items per batch | `25` |

### When to Run

- **First time setup:** After creating vector indexes
- **Content updates:** Regenerate embeddings for modified content
- **New content ingestion:** Only needed for existing content (new content auto-generates)

---

## Common Workflows

### Initial Setup (First Time)

```bash
# 1. Ensure HF_API_TOKEN is set and INTELLIGENCE_TIER=full in .env

# 2. Create vector indexes
uv run python scripts/create_vector_indexes.py

# 3. Verify indexes created
uv run python scripts/create_vector_indexes.py --verify

# 4. Generate embeddings for existing content
uv run python scripts/generate_embeddings_batch.py --label Ku
uv run python scripts/generate_embeddings_batch.py --label Task
uv run python scripts/generate_embeddings_batch.py --label Goal
uv run python scripts/generate_embeddings_batch.py --label LpStep

# 5. Test vector search via API
# POST /api/search/unified with use_vector_search=true
```

**Time:** 5-10 minutes (indexes) + 2-8 hours (embeddings depending on content volume)

### Testing Before Production

```bash
# 1. Create indexes
uv run python scripts/create_vector_indexes.py

# 2. Test with limited batches (5 batches = 125 items)
uv run python scripts/generate_embeddings_batch.py --label Curriculum --max-batches 5

# 3. Verify embeddings created
# In Neo4j Browser:
# MATCH (ku:Curriculum) WHERE ku.embedding IS NOT NULL RETURN count(ku)

# 4. Test vector search
# POST /api/search/unified
```

**Time:** 15-30 minutes

### Monthly Maintenance

```bash
# 1. Check for entities without embeddings
# In Neo4j Browser:
# MATCH (ku:Curriculum) WHERE ku.embedding IS NULL RETURN count(ku)

# 2. Regenerate for new/modified content
uv run python scripts/generate_embeddings_batch.py --label Curriculum

# 3. Verify all have embeddings
uv run python scripts/create_vector_indexes.py --verify
```

---

## Troubleshooting

### "No vector indexes found"

**Problem:** Vector indexes don't exist

**Solution:**
```bash
uv run python scripts/create_vector_indexes.py
```

### "Embeddings service not available"

**Problem:** `INTELLIGENCE_TIER` is not set to `full`, or `HF_API_TOKEN` is missing

**Solution:**
```bash
# Update .env
INTELLIGENCE_TIER=full
HF_API_TOKEN=hf_your_token_here

# Restart app
```

### "Failed to create vector index"

**Problem:** Neo4j connection issue or version mismatch

**Solution:**
1. Verify Neo4j is running: `docker compose ps` (local) or check AuraDB console
2. Verify `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` in `.env`
3. Retry index creation

**Documentation:** See `/docs/development/GENAI_SETUP.md`

### "HF_API_TOKEN not set"

**Problem:** Missing HuggingFace Inference API token

**Solution:**
```bash
# Check environment variable
echo $HF_API_TOKEN

# Update .env if missing
HF_API_TOKEN=hf_your_token_here

# Restart app
```

---

## Performance Tips

### Optimize Batch Size
```bash
# Smaller batches (faster feedback, more API calls)
uv run python scripts/generate_embeddings_batch.py --label Ku --batch-size 10

# Larger batches (fewer API calls, longer wait)
uv run python scripts/generate_embeddings_batch.py --label Ku --batch-size 50
```

**Recommendation:** Use default (25) for best balance

### Run During Off-Hours
```bash
# Schedule for overnight processing
# Use cron or systemd timer
0 2 * * * cd /path/to/skuel && uv run python scripts/generate_embeddings_batch.py --label Ku
```

### Monitor Progress
```bash
# Run with verbose logging
SKUEL_LOG_LEVEL=DEBUG uv run python scripts/generate_embeddings_batch.py --label Ku
```

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Generate Embeddings

on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday at 2 AM

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: astral-sh/setup-uv@v6
      - name: Install dependencies
        run: uv sync
      - name: Generate embeddings
        env:
          HF_API_TOKEN: ${{ secrets.HF_API_TOKEN }}
          NEO4J_URI: ${{ secrets.NEO4J_URI }}
          NEO4J_USERNAME: ${{ secrets.NEO4J_USERNAME }}
          NEO4J_PASSWORD: ${{ secrets.NEO4J_PASSWORD }}
          INTELLIGENCE_TIER: full
        run: |
          uv run python scripts/generate_embeddings_batch.py --label Ku
```

---

## See Also

- **Setup Guide:** `/docs/development/GENAI_SETUP.md`
- **Search Architecture:** `/docs/architecture/SEARCH_ARCHITECTURE.md`

---

## Quick Command Reference

```bash
# CREATE VECTOR INDEXES
uv run python scripts/create_vector_indexes.py                    # All priority entities
uv run python scripts/create_vector_indexes.py --verify           # Verify existing
uv run python scripts/create_vector_indexes.py --labels Ku Task   # Specific entities

# GENERATE EMBEDDINGS
uv run python scripts/generate_embeddings_batch.py --label Ku              # All KUs
uv run python scripts/generate_embeddings_batch.py --label Curriculum --max-batches 5  # Test (125 items)
uv run python scripts/generate_embeddings_batch.py --label Task            # All Tasks

# VERIFY IN NEO4J
SHOW INDEXES                                           # Show all indexes
MATCH (ku:Curriculum) WHERE ku.embedding IS NOT NULL RETURN count(ku)  # Count with embeddings
MATCH (ku:Curriculum) WHERE ku.embedding IS NULL RETURN count(ku)      # Count without embeddings
```

---

**Last Updated:** 2026-03-12
**Embedding Backend:** HuggingFace Inference API (`BAAI/bge-large-en-v1.5`, 1024 dims)
**Status:** Production Ready

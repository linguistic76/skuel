# Neo4j GenAI Scripts - Quick Reference
**Command-line tools for vector search setup and maintenance**

---

## Overview

This directory contains scripts for managing Neo4j GenAI plugin integration:

1. **create_vector_indexes.py** - Create and verify vector indexes
2. **generate_embeddings_batch.py** - Generate embeddings for existing content

---

## 1. Create Vector Indexes

**Purpose:** Create vector indexes for semantic similarity search

**Prerequisites:**
- Neo4j 5.x+ with GenAI plugin installed
- OpenAI API key configured at database level (AuraDB console)

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

# Use different embedding dimensions (for text-embedding-3-large)
uv run python scripts/create_vector_indexes.py --dimension 3072

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
| `--dimension` | Vector dimension | `1536` (text-embedding-3-small) |
| `--similarity` | Similarity function | `cosine` |
| `--verify` | Verify existing indexes instead of creating | `False` |

### When to Run

- **First time setup:** After enabling GenAI plugin
- **Adding new entities:** When adding embedding fields to new entity types
- **After Neo4j version upgrade:** To ensure indexes are compatible

---

## 2. Generate Embeddings (Batch)

**Purpose:** Generate embeddings for existing content that doesn't have embeddings yet

**Prerequisites:**
- OpenAI API key configured (OPENAI_API_KEY environment variable)
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
# Estimated cost: $0.03
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

### Cost Estimation

**Pricing (text-embedding-3-small):** $0.00002 per 1,000 tokens

**Example Costs:**
```
1,000 KUs @ 500 tokens each = 500,000 tokens
Cost: $0.06 (one-time)

10,000 KUs @ 500 tokens each = 5,000,000 tokens
Cost: $0.60 (one-time)
```

**Monthly Search (10,000 queries):**
- Cost: ~$0.20/month

### When to Run

- **First time setup:** After creating vector indexes
- **Content updates:** Regenerate embeddings for modified content
- **New content ingestion:** Only needed for existing content (new content auto-generates)

---

## Common Workflows

### Initial Setup (First Time)

```bash
# 1. Create vector indexes
uv run python scripts/create_vector_indexes.py

# 2. Verify indexes created
uv run python scripts/create_vector_indexes.py --verify

# 3. Generate embeddings for existing content
uv run python scripts/generate_embeddings_batch.py --label Ku
uv run python scripts/generate_embeddings_batch.py --label Task
uv run python scripts/generate_embeddings_batch.py --label Goal
uv run python scripts/generate_embeddings_batch.py --label LpStep

# 4. Test vector search via API
# POST /api/search/unified with use_vector_search=true
```

**Time:** 5-10 minutes (indexes) + 2-8 hours (embeddings)
**Cost:** $0.06 - $0.60 (one-time, depends on content volume)

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
**Cost:** < $0.01

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

### "GenAI plugin is disabled"

**Problem:** GENAI_ENABLED=False in config

**Solution:**
```bash
# Update .env
GENAI_ENABLED=true
GENAI_VECTOR_SEARCH_ENABLED=true

# Restart app
```

### "Failed to create vector index"

**Problem:** GenAI plugin not installed in Neo4j/AuraDB

**Solution:**
1. Log into AuraDB console
2. Navigate to your instance
3. Go to Plugins → GenAI
4. Enable plugin and add OpenAI API key
5. Retry index creation

**Documentation:** See `/docs/development/GENAI_SETUP.md`

### "OpenAI API key not configured"

**Problem:** Missing or invalid API key

**Solution:**
```bash
# Check environment variable
echo $OPENAI_API_KEY

# Update .env if missing
OPENAI_API_KEY=sk-your-actual-key-here

# Restart app
```

### "Cost too high"

**Problem:** Batch processing will be expensive

**Solution:**
```bash
# Test with limited batches first
uv run python scripts/generate_embeddings_batch.py --label Ku --max-batches 5

# Calculate full cost before running:
# nodes * avg_tokens * $0.00002 / 1000
# Example: 10,000 * 500 * 0.00002 / 1000 = $0.60
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
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      - name: Generate embeddings
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          NEO4J_URI: ${{ secrets.NEO4J_URI }}
          NEO4J_USERNAME: ${{ secrets.NEO4J_USERNAME }}
          NEO4J_PASSWORD: ${{ secrets.NEO4J_PASSWORD }}
        run: |
          uv run python scripts/generate_embeddings_batch.py --label Ku
```

---

## See Also

- **Setup Guide:** `/docs/development/GENAI_SETUP.md`
- **Migration Guide:** `/docs/migrations/NEO4J_GENAI_MIGRATION.md`
- **Completion Summary:** `/home/mike/PHASE_7_IMPLEMENTATION_COMPLETE.md`

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

**Last Updated:** 2026-01-29
**Phase:** 7 (Neo4j GenAI Plugin Migration)
**Status:** ✅ Production Ready

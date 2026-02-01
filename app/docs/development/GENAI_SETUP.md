# Neo4j GenAI Plugin Setup (Docker)

**Last Updated:** 2026-02-01
**Status:** Production Ready

---

## Overview

SKUEL uses Neo4j's GenAI plugin for embeddings generation and vector similarity search in development. This guide covers Docker-based setup only.

**For production AuraDB deployment:** See [`/docs/deployment/AURADB_MIGRATION_GUIDE.md`](../deployment/AURADB_MIGRATION_GUIDE.md)

### Key Features

- **Embeddings Generation:** Create vector embeddings for semantic search
- **Vector Similarity Search:** Find semantically similar content across domains
- **Graceful Degradation:** Application works without GenAI features
- **Cost Effective:** ~$0.02 per 1M tokens with OpenAI
- **Docker-Native:** Zero infrastructure setup needed

### Architecture

```
User Query → Neo4j GenAI Plugin → OpenAI API → Embeddings
                ↓
          Vector Index → Similarity Search → Results
```

---

## Prerequisites

### Required

- **Docker & Docker Compose** (20.10+ and 2.0+)
- **OpenAI API Key** for embedding generation
- **Poetry** (for dependency management)

### Verify Prerequisites

```bash
docker --version       # Should be 20.10+
docker compose version # Should be 2.0+
poetry --version       # Should be 1.7+
python --version       # Should be 3.12+
```

---

## Quick Start (10 Minutes)

### 1. Start Neo4j with GenAI Plugin

```bash
# Navigate to infrastructure directory
cd /home/mike/skuel/infrastructure

# Start Neo4j (GenAI plugin auto-loaded)
docker compose up -d neo4j

# Verify plugin loaded
docker logs skuel-neo4j | grep -i genai
# Expected: "Loaded plugin: genai" or similar
```

**What's Happening:**
- Docker pulls Neo4j 2025.12.1 image
- GenAI plugin automatically loaded via `NEO4J_PLUGINS='["genai"]'`
- Neo4j starts on `bolt://localhost:7687`

### 2. Configure Environment Variables

**Add to `/home/mike/skuel/app/.env`:**

```bash
# ============================================================================
# Neo4j Connection (Docker)
# ============================================================================
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>  # From infrastructure .env
NEO4J_DATABASE=neo4j

# ============================================================================
# GenAI Configuration
# ============================================================================
# Enable GenAI features
GENAI_ENABLED=true
GENAI_VECTOR_SEARCH_ENABLED=true

# Embedding configuration
GENAI_EMBEDDING_MODEL=text-embedding-3-small
GENAI_EMBEDDING_DIMENSION=1536

# OpenAI API key (used per-query in Docker setup)
OPENAI_API_KEY=sk-proj-...  # Your OpenAI API key
```

**Get OpenAI API Key:**
1. Visit https://platform.openai.com/api-keys
2. Create new secret key
3. Copy immediately (won't be shown again)

### 3. Verify Setup

```bash
cd /home/mike/skuel/app

# Run verification script
poetry run python scripts/verify_genai_setup.py
```

**Expected Output:**
```
✅ Neo4j connection successful (bolt://localhost:7687)
✅ GenAI plugin available
✅ OpenAI API key configured
✅ Vector indexes exist (or will be created on first use)
✅ Test embedding generation successful

Setup complete! GenAI features ready to use.
```

### 4. Create Vector Indexes

```bash
# Create vector indexes for all supported entities
poetry run python scripts/create_vector_indexes.py
```

**Expected Output:**
```
Creating vector indexes...
✅ Created: ku_embedding_idx (1536d, cosine)
✅ Created: task_embedding_idx (1536d, cosine)
✅ Created: goal_embedding_idx (1536d, cosine)
✅ Created: habit_embedding_idx (1536d, cosine)

Total: 4 indexes created
```

### 5. Test Semantic Search

```bash
# Run integration tests
poetry run pytest tests/integration/test_vector_search.py -v
```

**Expected:** All tests passing

---

## Docker Setup Details

### GenAI Plugin Configuration

The GenAI plugin is configured via `docker-compose.yml`:

```yaml
# /home/mike/skuel/infrastructure/docker-compose.yml
services:
  neo4j:
    image: neo4j:2025.12.1
    environment:
      # Enable GenAI plugin (auto-loads from /products to /plugins)
      NEO4J_PLUGINS: '["genai"]'

      # OpenAI API key (accessible via procedures)
      OPENAI_API_KEY: "${NEO4J_OPENAI_API_KEY}"

      # Allow GenAI plugin procedures
      NEO4J_dbms_security_procedures_unrestricted: "genai.*"
      NEO4J_dbms_security_procedures_allowlist: "genai.*"
```

**Key Differences from AuraDB:**
- Plugin loaded via `NEO4J_PLUGINS` environment variable
- API key passed **per-query** via `token` parameter
- No database-level API key configuration

### Per-Query Token Passing

In Docker setup, OpenAI API key is passed with each query:

```python
# Example: Generate embedding with per-query token
result = await driver.execute_query('''
    RETURN genai.vector.encode($text, "OpenAI", {
        token: $api_key,
        model: "text-embedding-3-small",
        dimensions: 1536
    }) AS embedding
''', {
    'text': 'Hello world',
    'api_key': os.getenv('OPENAI_API_KEY')
})
```

**SKUEL handles this automatically** - you don't need to modify code.

---

## Feature Detection

SKUEL automatically detects available features at runtime.

### Check Available Features

```python
from core.utils.services_bootstrap import bootstrap

# Bootstrap services
services = await bootstrap()

# Check embeddings availability
if services.get("embeddings"):
    print("✅ Embeddings available - semantic search enabled")
else:
    print("⚠️ Embeddings unavailable - using keyword search only")

# Check vector search availability
if services.get("vector_search"):
    print("✅ Vector search available")
else:
    print("⚠️ Vector search unavailable")
```

### Configuration Flags

Control GenAI features via environment variables:

```bash
# Enable/disable GenAI features
GENAI_ENABLED=true           # Master switch
GENAI_VECTOR_SEARCH_ENABLED=true  # Vector similarity search

# Embedding configuration
GENAI_EMBEDDING_MODEL=text-embedding-3-small  # OpenAI model
GENAI_EMBEDDING_DIMENSION=1536               # Vector dimensions

# Optional: Override defaults
GENAI_BATCH_SIZE=25          # Batch size for embedding generation
GENAI_SIMILARITY_THRESHOLD=0.7  # Minimum similarity score
```

---

## Graceful Degradation

SKUEL is designed to work with or without GenAI features.

### Feature Availability Matrix

| Feature | With GenAI | Without GenAI |
|---------|-----------|---------------|
| **Basic CRUD** | ✅ Full support | ✅ Full support |
| **Keyword Search** | ✅ Available | ✅ Primary method |
| **Semantic Search** | ✅ Primary method | ❌ Unavailable |
| **AI Insights** | ✅ Available | ❌ Unavailable |
| **Vector Similarity** | ✅ Available | ⚠️ Falls back to keyword |
| **Related Content** | ✅ Semantic | ⚠️ Graph-based only |

### Fallback Behavior

When embeddings are unavailable:

1. **Search Routes:** Return keyword search results
2. **Similar Content:** Uses graph relationships instead of vectors
3. **UI Messages:** Inform users semantic search unavailable
4. **API Responses:** Include `semantic_search_available: false` flag

### Testing Fallback

```bash
# Disable GenAI to test fallback behavior
GENAI_ENABLED=false poetry run python skuel.py

# Verify keyword search works
curl http://localhost:8000/api/knowledge/search?q=python

# Should return results using keyword matching
```

---

## Troubleshooting

### "GenAI plugin not available"

**Symptoms:**
- Error: "Neo4j GenAI plugin not available"
- Embeddings fail with database error
- Vector search unavailable

**Check:**

1. ✅ GenAI plugin loaded in Docker
   ```bash
   docker logs skuel-neo4j | grep -i genai
   # Should show: "Loaded plugin: genai"
   ```

2. ✅ Plugin environment variable set
   ```bash
   docker exec skuel-neo4j env | grep NEO4J_PLUGINS
   # Should show: NEO4J_PLUGINS=["genai"]
   ```

3. ✅ Plugin procedures allowed
   ```bash
   docker exec skuel-neo4j env | grep unrestricted
   # Should show: genai.* in allowlist
   ```

**Solution:**

```bash
# Restart Neo4j to reload plugin
cd /home/mike/skuel/infrastructure
docker compose restart neo4j

# Wait 30 seconds for startup
sleep 30

# Verify plugin loaded
docker logs skuel-neo4j | tail -20
```

### "Embeddings unavailable"

**Symptoms:**
- Embeddings service returns `None`
- Searches fall back to keywords
- Warning: "Embeddings service unavailable"

**Check:**

1. ✅ OpenAI API key configured
   ```bash
   grep OPENAI_API_KEY /home/mike/skuel/app/.env
   # Should show: OPENAI_API_KEY=sk-proj-...
   ```

2. ✅ GENAI_ENABLED flag set
   ```bash
   grep GENAI_ENABLED /home/mike/skuel/app/.env
   # Should show: GENAI_ENABLED=true
   ```

3. ✅ Neo4j running
   ```bash
   docker ps | grep neo4j
   # Should show: skuel-neo4j (running)
   ```

**Solutions:**
- Set `OPENAI_API_KEY` in `.env`
- Verify API key is valid: https://platform.openai.com/api-keys
- Check OpenAI key has credits: https://platform.openai.com/usage
- Restart application: `systemctl restart skuel`

### "Vector index not found"

**Symptoms:**
- Error: "Vector index ku_embedding_idx not found"
- Vector search fails with database error

**Solution:**

Vector indexes are created automatically on first use, but you can create them manually:

```bash
# Create missing indexes
poetry run python scripts/create_vector_indexes.py
```

**Manual Index Creation (if needed):**

```cypher
// Open Neo4j Browser: http://localhost:7474

// Create vector index for KU entities
CREATE VECTOR INDEX ku_embedding_idx IF NOT EXISTS
FOR (n:Ku)
ON n.embedding
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
}
```

### "OpenAI rate limit exceeded"

**Symptoms:**
- Error: "Rate limit reached for text-embedding-3-small"
- Batch embedding generation fails

**Solutions:**

1. **Reduce batch size:**
   ```bash
   poetry run python scripts/generate_embeddings_batch.py --batch-size 10
   ```

2. **Add delays between batches:**
   ```python
   # In batch script
   await asyncio.sleep(1)  # 1 second between batches
   ```

3. **Upgrade OpenAI tier:**
   - Visit https://platform.openai.com/settings/organization/billing
   - Increase rate limits with higher tier

4. **Process incrementally:**
   ```bash
   # Process one entity type at a time
   poetry run python scripts/generate_embeddings_batch.py --label Ku --max-batches 10
   ```

### "Embedding dimension mismatch"

**Symptoms:**
- Error: "Expected 1536 dimensions, got 768"
- Vector index creation fails

**Check:**
```bash
# Verify embedding model configuration
grep GENAI_EMBEDDING /home/mike/skuel/app/.env
```

**Solution:**

Ensure consistent configuration:

```bash
# In .env
GENAI_EMBEDDING_MODEL=text-embedding-3-small  # Produces 1536d
GENAI_EMBEDDING_DIMENSION=1536
```

**If you previously used different model:**

```cypher
// Open Neo4j Browser: http://localhost:7474

// Remove old embeddings
MATCH (n)
WHERE n.embedding IS NOT NULL
  AND size(n.embedding) <> 1536
REMOVE n.embedding, n.embedding_model, n.embedding_updated_at
```

Then regenerate with correct model.

### Docker Container Issues

**Symptoms:**
- Neo4j container won't start
- Container crashes on startup
- Permission errors

**Check:**

1. ✅ Docker daemon running
   ```bash
   docker info
   # Should show system info
   ```

2. ✅ Port 7687 not in use
   ```bash
   lsof -i:7687
   # Should be empty or show neo4j only
   ```

3. ✅ Volume permissions correct
   ```bash
   ls -la /home/mike/skuel/infrastructure/neo4j/data
   # Should be readable by Docker
   ```

**Solutions:**

```bash
# Stop and remove container
docker compose down neo4j

# Fix permissions (if needed)
sudo chown -R $USER:$USER /home/mike/skuel/infrastructure/neo4j/

# Restart with fresh logs
docker compose up -d neo4j
docker logs -f skuel-neo4j
```

---

## Best Practices

### 1. Use Docker for Development

**Why:**
- Fast iteration cycle
- No external dependencies
- Complete control over configuration
- Easy to reset/recreate
- Free (no cloud costs)

**How:**
```bash
# Start/stop as needed
docker compose up -d neo4j     # Start
docker compose stop neo4j      # Stop
docker compose restart neo4j   # Restart
```

### 2. Monitor OpenAI Usage

**Why:**
- Control costs during development
- Detect issues early
- Optimize batch sizes
- Understand usage patterns

**How:**
1. OpenAI Dashboard → Usage
2. Set billing alerts at $10/month (development threshold)
3. Monitor daily usage
4. Review cost reports weekly

### 3. Use Batch Operations

**Why:**
- Faster processing
- Better throughput
- Lower overhead
- Optimal Neo4j performance

**How:**
```bash
# Generate embeddings in batches of 25-50
poetry run python scripts/generate_embeddings_batch.py --batch-size 25
```

**Optimal Batch Sizes:**
- Small entities (~100 tokens): batch_size=50
- Medium entities (~200 tokens): batch_size=25
- Large entities (~500 tokens): batch_size=10

### 4. Cache Embeddings

**Why:**
- Avoid regenerating unchanged content
- Lower costs
- Faster operations

**How:**
```python
# Check if embedding exists
if not entity.embedding or content_changed:
    # Generate new embedding
    embedding = await embeddings_service.create_embedding(text)
else:
    # Reuse existing embedding
    embedding = entity.embedding
```

### 5. Test Without API Calls

**Why:**
- Fast test execution
- No API costs
- Deterministic results
- CI/CD friendly

**How:**
```bash
# Use mock fixtures
poetry run pytest tests/ -v

# All tests use mock embeddings - no API calls
```

### 6. Backup Regularly

**Why:**
- Protect against data loss
- Enable easy rollback
- Test restore procedures

**How:**
```bash
# Create backup
docker compose exec neo4j \
  neo4j-admin database dump neo4j \
  --to-path=/backups/backup_$(date +%Y%m%d).dump

# Copy to host
docker cp skuel-neo4j:/backups/backup_*.dump \
  /home/mike/skuel/infrastructure/neo4j/backups/
```

---

## Performance Optimization

### Batch Size Tuning

**Test different batch sizes:**

```bash
# Small batches (safer, slower)
time poetry run python scripts/generate_embeddings_batch.py --batch-size 10

# Medium batches (recommended)
time poetry run python scripts/generate_embeddings_batch.py --batch-size 25

# Large batches (faster, riskier)
time poetry run python scripts/generate_embeddings_batch.py --batch-size 50
```

**Recommended:**
- Development: batch_size=25
- CI/CD: batch_size=10 (conservative)

### Vector Index Configuration

**Default (good for most cases):**
```cypher
CREATE VECTOR INDEX ku_embedding_idx
FOR (n:Ku) ON n.embedding
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
}
```

**For better recall (slower):**
```cypher
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine',
    `vector.quantization.enabled`: false  # Disable quantization
  }
}
```

### Docker Resource Tuning

**Increase memory for large datasets:**

```yaml
# docker-compose.yml
services:
  neo4j:
    environment:
      # Increase heap size
      NEO4J_server_memory_heap_initial__size: "1G"
      NEO4J_server_memory_heap_max__size: "4G"

      # Increase page cache
      NEO4J_server_memory_pagecache_size: "2G"
```

**After changing configuration:**
```bash
docker compose restart neo4j
```

---

## Security Considerations

### API Key Management

**✅ DO:**
- Store keys in `.env` (never commit to git)
- Use separate keys for dev/staging/prod
- Rotate keys regularly (every 90 days)
- Set spending limits in OpenAI dashboard

**❌ DON'T:**
- Commit keys to git
- Share keys in plaintext
- Use same key across environments
- Hardcode keys in source code

### Docker Network Security

**Best Practices:**

```yaml
# docker-compose.yml - Localhost-only binding
services:
  neo4j:
    ports:
      - "127.0.0.1:7474:7474"  # HTTP (Neo4j Browser)
      - "127.0.0.1:7687:7687"  # Bolt (Application)
```

This prevents external access to Neo4j.

### Audit Logging

```python
# Log embedding generation for audit trail
logger.info(
    "Generated embeddings",
    extra={
        "entity_type": "Ku",
        "entity_uid": uid,
        "user_uid": user_uid,
        "model": "text-embedding-3-small",
        "tokens": estimated_tokens,
    }
)
```

---

## Production Deployment

**When ready for production, migrate to AuraDB:**

See complete guide: [`/docs/deployment/AURADB_MIGRATION_GUIDE.md`](../deployment/AURADB_MIGRATION_GUIDE.md)

**Migration provides:**
- Automated backups and monitoring
- 99.95% uptime SLA
- Database-level API key configuration
- Managed infrastructure
- Professional support

**Estimated migration time:** 4-6 hours

---

## See Also

### Related Documentation

- [AuraDB Migration Guide](../deployment/AURADB_MIGRATION_GUIDE.md) - Production deployment
- [Vector Search Architecture](../architecture/SEARCH_ARCHITECTURE.md) - Technical details
- [Testing Guide](./TESTING.md) - Running tests with mock services

### External Resources

- [Neo4j GenAI Plugin Documentation](https://neo4j.com/docs/genai/plugin/current/)
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
- [Vector Indexes in Neo4j](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

### Scripts Reference

| Script | Purpose |
|--------|---------|
| `verify_genai_setup.py` | Verify GenAI plugin configuration |
| `generate_embeddings_batch.py` | Generate embeddings for existing entities |
| `create_vector_indexes.py` | Create vector indexes manually |
| `check_embeddings_coverage.py` | Check embedding generation progress |

---

**Questions or Issues?**

- Check [Troubleshooting](#troubleshooting) section above
- Review [AuraDB Migration Guide](../deployment/AURADB_MIGRATION_GUIDE.md) for production
- Check logs: `docker logs -f skuel-neo4j`
- Check application logs: `tail -f logs/skuel.log`

---

**Last Updated:** 2026-02-01
**Maintained By:** SKUEL Core Team
**Status:** Production Ready (Docker Development)

# Neo4j GenAI Plugin Setup Guide

**Last Updated:** 2026-01-28
**Status:** Production Ready

---

## Overview

SKUEL uses Neo4j's GenAI plugin for embeddings generation and vector similarity search. This guide covers setup for both local development and production environments.

### Key Features

- **Embeddings Generation:** Create vector embeddings for semantic search
- **Vector Similarity Search:** Find semantically similar content across domains
- **Graceful Degradation:** Application works without GenAI features
- **Cost Effective:** ~$0.02 per 1M tokens with OpenAI

### Architecture

```
User Query → Neo4j GenAI Plugin → OpenAI API → Embeddings
                ↓
          Vector Index → Similarity Search → Results
```

---

## Prerequisites

### Required

- **Neo4j AuraDB** (Professional tier or higher)
  - OR Neo4j 5.26+ with GenAI plugin installed
- **OpenAI API Key** for embedding generation
- **SKUEL Master Key** for credential encryption

### Optional

- Docker (for local testing with testcontainers)
- Poetry (for dependency management)

---

## Quick Start (AuraDB - Recommended)

### 1. Connect to Shared Development Instance

The fastest way to get started is using the shared development AuraDB instance with GenAI plugin pre-configured.

**Add to your `.env`:**

```bash
# Neo4j Connection
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<get-from-team-lead>
NEO4J_DATABASE=neo4j

# GenAI Features
GENAI_ENABLED=true
GENAI_VECTOR_SEARCH_ENABLED=true
GENAI_EMBEDDING_MODEL=text-embedding-3-small
GENAI_EMBEDDING_DIMENSION=1536
```

### 2. Configure OpenAI API Key

Store securely in SKUEL's credential store:

```bash
poetry run python -m core.config.credential_setup

# Interactive prompts:
# Select: "2. Set up single credential"
# Credential key: OPENAI_API_KEY
# Credential value: sk-proj-... (your OpenAI API key)
```

**Get OpenAI API Key:**
1. Visit https://platform.openai.com/api-keys
2. Create new secret key
3. Copy immediately (won't be shown again)

### 3. Verify Setup

```bash
poetry run python scripts/verify_genai_setup.py
```

**Expected Output:**
```
✅ Neo4j connection successful
✅ GenAI plugin available
✅ OpenAI API key configured
✅ Vector indexes exist (or will be created on first use)
✅ Test embedding generation successful

Setup complete! GenAI features ready to use.
```

### 4. Test Semantic Search

```bash
# Run integration tests
poetry run pytest tests/integration/test_vector_search.py -v

# Run E2E tests
poetry run pytest tests/e2e/test_semantic_search_flow.py -v
```

---

## AuraDB Configuration

### Database-Level API Key Setup

Neo4j GenAI plugin uses database-level API key configuration (more secure than per-query passing).

**Steps:**

1. Log in to [Neo4j Aura Console](https://console.neo4j.io/)
2. Select your database instance
3. Navigate to **Settings** → **GenAI Integration**
4. Click **Add API Key**
5. Select **OpenAI** as provider
6. Enter your OpenAI API key
7. Click **Save**

**Benefits:**
- ✅ Centralized key management
- ✅ No per-query credential passing
- ✅ Automatic key rotation support
- ✅ Team access control

**Note:** API key is encrypted and stored securely by Neo4j. SKUEL does not store or handle the OpenAI key directly.

### Choosing AuraDB Tier

| Tier | GenAI Plugin | Vector Indexes | Recommended For |
|------|--------------|----------------|-----------------|
| Free | ❌ Not available | ❌ | Learning/testing |
| Professional | ✅ Available | ✅ | Development |
| Enterprise | ✅ Available | ✅ | Production |

**Recommendation:** Professional tier (~$65/month) for development and staging.

---

## Local Development (Alternative)

For developers who prefer local Neo4j instances:

### Option 1: Use Testcontainers (Testing Only)

```bash
# Testcontainers automatically start Neo4j for tests
poetry run pytest tests/integration/ -v

# Note: GenAI plugin NOT available in testcontainers
# Tests use mock embeddings services
```

### Option 2: Local Neo4j with Plugin

```bash
# 1. Install Neo4j 5.26+
# Download from: https://neo4j.com/download/

# 2. Install GenAI plugin
# Follow: https://neo4j.com/docs/genai/plugin/current/installation/

# 3. Configure plugin in neo4j.conf
dbms.genai.enabled=true
dbms.genai.openai.api_key=${OPENAI_API_KEY}

# 4. Start Neo4j
neo4j start

# 5. Update .env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-password>
GENAI_ENABLED=true
```

**Note:** Local setup requires more configuration. Shared AuraDB is recommended for most developers.

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

## Cost Estimation

### OpenAI Embeddings

**Model:** `text-embedding-3-small`
- **Pricing:** $0.02 per 1 million tokens
- **Typical Entity:** ~200 tokens (title + content)
- **1,000 Entities:** ~$0.004 USD
- **10,000 Entities:** ~$0.04 USD

**Example Calculation:**
```
Scenario: Ingest 5,000 knowledge units
Average length: 300 tokens per KU
Total tokens: 5,000 × 300 = 1,500,000 tokens
Cost: 1.5M × $0.02 / 1M = $0.03 USD
```

### AuraDB Costs

| Tier | Monthly Cost | Storage | GenAI Plugin |
|------|-------------|---------|--------------|
| Free | $0 | 50k nodes | ❌ Not available |
| Professional | ~$65 | 1M nodes | ✅ Included |
| Enterprise | Custom | Unlimited | ✅ Included |

**Note:** GenAI plugin has no additional fees beyond AuraDB subscription.

### Development Usage Estimates

**Typical Developer:**
- 100-500 entities created/modified per month
- ~$0.01-0.05 per month in OpenAI costs
- AuraDB: $65/month (shared among team)

**Team Estimate (5 developers):**
- Shared AuraDB instance: $65/month
- Combined OpenAI usage: $5-15/month
- **Total: ~$80/month** for team

**Production Estimate:**
- 50,000+ entities
- Initial backfill: ~$2-5 one-time
- Ongoing: ~$5-20/month
- AuraDB: $65-250/month (based on tier)

---

## Troubleshooting

### "GenAI plugin not available"

**Symptoms:**
- Error: "Neo4j GenAI plugin not available"
- Embeddings fail with database error
- Vector search unavailable

**Check:**
1. ✅ Connected to AuraDB (not local Neo4j)
   ```bash
   echo $NEO4J_URI  # Should be neo4j+s://...databases.neo4j.io
   ```

2. ✅ Using Professional tier or higher
   - Log in to Aura console
   - Check database tier

3. ✅ Plugin enabled in Aura console
   - Settings → GenAI Integration
   - Verify API key configured

4. ✅ Environment variable set
   ```bash
   echo $GENAI_ENABLED  # Should be 'true'
   ```

**Solution:**
- Upgrade to Professional tier, OR
- Enable GenAI plugin in Aura console, OR
- Use shared development instance

### "Embeddings unavailable"

**Symptoms:**
- Embeddings service returns `None`
- Searches fall back to keywords
- Warning: "Embeddings service unavailable"

**Check:**
1. ✅ OpenAI API key configured
   ```bash
   poetry run python -c "from core.config.credential_store import get_credential; print('Key exists:', get_credential('OPENAI_API_KEY') is not None)"
   ```

2. ✅ GENAI_ENABLED flag set
   ```bash
   grep GENAI_ENABLED .env
   ```

3. ✅ Services bootstrapped correctly
   ```python
   from core.utils.services_bootstrap import bootstrap
   services = await bootstrap()
   print("Embeddings:", services.get("embeddings"))
   ```

**Solutions:**
- Run credential setup: `poetry run python -m core.config.credential_setup`
- Verify API key in `.env`: `GENAI_ENABLED=true`
- Check OpenAI key is valid and has credits

### "Vector index not found"

**Symptoms:**
- Error: "Vector index ku_embedding_idx not found"
- Vector search fails with database error

**Solution:**

Vector indexes are created automatically on first use, but you can create them manually:

```bash
# Check if indexes exist
poetry run python scripts/check_vector_indexes.py

# Create missing indexes
poetry run python scripts/create_vector_indexes.py
```

**Manual Index Creation (if needed):**

```cypher
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
grep GENAI_EMBEDDING /env
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
// Remove old embeddings
MATCH (n)
WHERE n.embedding IS NOT NULL
  AND size(n.embedding) <> 1536
REMOVE n.embedding, n.embedding_model, n.embedding_updated_at
```

Then regenerate with correct model.

---

## Best Practices

### 1. Use Shared AuraDB for Development

**Why:**
- Zero setup overhead
- GenAI plugin pre-configured
- Team collaboration easy
- No local infrastructure needed

**How:**
```bash
# Get credentials from team lead
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<team-password>
```

### 2. Configure API Key at Database Level

**Why:**
- More secure (no key in code)
- Centralized management
- Team access control
- Automatic rotation support

**How:**
- Aura Console → Settings → GenAI Integration → Add API Key

### 3. Enable Graceful Degradation

**Why:**
- App works without embeddings
- Easier onboarding for new developers
- Resilient to API outages
- Lower costs during development

**How:**
```python
# Services automatically check for embeddings
if embeddings_service:
    # Use semantic search
else:
    # Fall back to keyword search
```

### 4. Monitor API Usage

**Why:**
- Control costs
- Detect issues early
- Optimize batch sizes
- Plan scaling

**How:**
1. OpenAI Dashboard → Usage
2. Set billing alerts
3. Monitor daily usage
4. Review cost reports monthly

### 5. Use Batch Operations

**Why:**
- Faster processing
- Better throughput
- Lower overhead
- Optimal Neo4j performance

**How:**
```bash
# Generate embeddings in batches of 25-100
poetry run python scripts/generate_embeddings_batch.py --batch-size 50
```

**Optimal Batch Sizes:**
- Small entities (~100 tokens): batch_size=100
- Medium entities (~200 tokens): batch_size=50
- Large entities (~500 tokens): batch_size=25

### 6. Cache Embeddings

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

### 7. Test Without API Calls

**Why:**
- Fast test execution
- No API costs
- Deterministic results
- CI/CD friendly

**How:**
```bash
# Use mock fixtures (Phase 6.1)
poetry run pytest tests/ -v

# All tests use mock embeddings - no API calls
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
- Production: batch_size=50

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

### Caching Strategy

```python
# Cache embeddings in Redis (optional)
async def get_or_create_embedding(text: str, cache_key: str):
    # Check cache
    cached = await redis.get(f"embedding:{cache_key}")
    if cached:
        return json.loads(cached)

    # Generate new
    result = await embeddings_service.create_embedding(text)
    if result.is_ok:
        await redis.setex(f"embedding:{cache_key}", 3600, json.dumps(result.value))
        return result.value
```

---

## Security Considerations

### API Key Management

**✅ DO:**
- Store keys in SKUEL credential store (encrypted)
- Use database-level key configuration in AuraDB
- Rotate keys regularly (every 90 days)
- Use separate keys for dev/staging/prod
- Set spending limits in OpenAI dashboard

**❌ DON'T:**
- Commit keys to git
- Share keys in plaintext
- Use same key across environments
- Store keys in `.env` files (use credential store)

### Access Control

```bash
# Restrict who can modify GenAI configuration
# In Aura console:
# 1. Settings → Access Control
# 2. Limit "Admin" role to select users
# 3. Use "Read-only" for most developers
```

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

## See Also

### Related Documentation

- [Migration Guide](../migrations/NEO4J_GENAI_MIGRATION.md) - Migrating existing systems
- [Vector Search Architecture](../architecture/SEARCH_ARCHITECTURE.md) - Technical details
- [Credential Management](./CREDENTIAL_MANAGEMENT.md) - Secure key storage
- [Testing Guide](./TESTING.md) - Running tests with mock services

### External Resources

- [Neo4j GenAI Plugin Documentation](https://neo4j.com/docs/genai/plugin/current/)
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
- [Vector Indexes in Neo4j](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)

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
- Review [Migration Guide](../migrations/NEO4J_GENAI_MIGRATION.md)
- Check logs: `tail -f logs/skuel.log`
- Contact team lead for shared credentials

---

**Last Updated:** 2026-01-28
**Maintained By:** SKUEL Core Team
**Status:** Production Ready

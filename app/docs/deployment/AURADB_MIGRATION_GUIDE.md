---
title: Auradb Migration Guide
---
# AuraDB Production Migration Guide

**Last Updated:** 2026-03-12
**Migration Type:** Infrastructure Change (Docker → AuraDB)
**Estimated Time:** 4-6 hours

---

## Overview

This guide covers migrating from Docker-based Neo4j to Neo4j AuraDB (production deployment). It assumes the app is already deployed on DigitalOcean App Platform (see [DO Migration Guide](./DO_MIGRATION_GUIDE.md) if you have not done that yet). The migration here is primarily a Neo4j swap: the app deployment itself does not change.

**Note:** Embeddings are generated Python-side via HuggingFace Inference API (see [ADR-049](/docs/decisions/ADR-049-huggingface-embeddings-migration.md)). No Neo4j GenAI plugin is required. This simplifies the AuraDB migration — no plugin configuration needed.

### Current Setup (Development)

- **Environment:** Docker-based Neo4j 2025.12.1
- **Connection:** `bolt://localhost:7687`
- **Plugins:** APOC (meta only) — no GenAI plugin needed
- **Embeddings:** Python-side via HuggingFace Inference API (`HF_API_TOKEN`)
- **Management:** Manual via docker-compose
- **Backup:** Manual via Neo4j CLI

### Target Setup (Production)

- **Environment:** Neo4j AuraDB Professional/Enterprise
- **Connection:** `neo4j+s://xxx.databases.neo4j.io`
- **Plugins:** None required (APOC may be available natively)
- **Embeddings:** Same Python-side HuggingFace Inference API (no change)
- **Management:** Automated via AuraDB console
- **Backup:** Automated daily snapshots

---

## When to Migrate

### You Should Migrate When...

✅ Deploying to production environment
✅ Need automated backups and monitoring
✅ Require high availability and uptime SLA
✅ Team needs centralized database management
✅ Want to eliminate infrastructure maintenance

### You Should NOT Migrate If...

❌ Still in active development (Docker is faster)
❌ Running on localhost only
❌ Need rapid schema changes and testing
❌ Cost-sensitive early-stage project
❌ Require complete control over Neo4j configuration

**Recommendation:** Use Docker for development/staging, AuraDB for production.

---

## Key Differences: Docker vs AuraDB

### Connection Configuration

| Aspect | Docker (Current) | AuraDB (Production) |
|--------|------------------|---------------------|
| **URI Format** | `bolt://localhost:7687` | `neo4j+s://c3a6c0c8.databases.neo4j.io` |
| **TLS/SSL** | Optional (not required) | Required (`neo4j+s://` protocol) |
| **Authentication** | Username/password | Username/password (no change) |
| **Environment Variable** | `NEO4J_URI=bolt://localhost:7687` | `NEO4J_URI=neo4j+s://xxx.databases.neo4j.io` |

### Embeddings

| Aspect | Docker (Current) | AuraDB (Production) |
|--------|------------------|---------------------|
| **Generation** | Python-side (HuggingFace Inference API) | Same — no change |
| **API Key** | `HF_API_TOKEN` in app container | `HF_API_TOKEN` in app container |
| **Neo4j Plugin** | None needed | None needed |
| **Vector Indexes** | 1024-dim cosine | 1024-dim cosine (recreate after migration) |

### Management & Maintenance

| Aspect | Docker (Current) | AuraDB (Production) |
|--------|------------------|---------------------|
| **Start/Stop** | `docker compose up/down` | Always running (managed service) |
| **Backups** | Manual via `neo4j-admin` | Automated daily + on-demand |
| **Updates** | Manual image pull + restart | Automatic patch management |
| **Monitoring** | Manual via logs | Built-in metrics dashboard |
| **Scaling** | Fixed resources | Vertical scaling via console |

### Cost Comparison

| Environment | Setup Cost | Monthly Cost | Management Effort |
|-------------|-----------|--------------|-------------------|
| **Docker** | $0 (uses existing infrastructure) | $0 (local resources) | High (manual maintenance) |
| **AuraDB Professional** | $0 (instant setup) | ~$65/month | Low (managed service) |
| **AuraDB Enterprise** | $0 (instant setup) | Custom pricing | Minimal (fully managed) |

---

## Prerequisites

### Before You Begin

- [ ] **Backup:** Export current Neo4j database from Docker
- [ ] **Credentials:** Neo4j Aura account (create at https://console.neo4j.io/)
- [ ] **API Keys:** HuggingFace API token for embeddings (`HF_API_TOKEN`)
- [ ] **Time:** 4-6 hours for full migration
- [ ] **Testing:** Staging environment for validation
- [ ] **Access:** Admin access to AuraDB console

### Required Tools

```bash
# Verify tools available
uv --version  # Should be 1.7+
python --version  # Should be 3.12+
neo4j-admin --version  # For data export (if using Docker data)
```

---

## Migration Phases

## Phase 1: Backup Current Docker Database

**Time: 30 minutes**

### 1.1 Export Entity Counts

```bash
# Export current entity counts for verification
cd /home/mike/skuel/app
uv run python scripts/export_entity_counts.py \
  --output=pre_migration_counts_$(date +%Y%m%d).json

# Example output:
# {
#   "Ku": 1234,
#   "Task": 3456,
#   "Goal": 789,
#   "timestamp": "2026-02-01T10:00:00Z"
# }
```

### 1.2 Backup Neo4j Data

**Stop Docker container:**

```bash
cd /home/mike/skuel/infrastructure
docker compose stop neo4j
```

**Create backup:**

```bash
# Backup via docker exec
docker compose run --rm neo4j \
  neo4j-admin database dump neo4j \
  --to-path=/backups/backup_$(date +%Y%m%d_%H%M%S).dump

# Copy backup to host
docker cp skuel-neo4j:/backups/backup_*.dump ./neo4j/backups/
```

### 1.3 Document Current Configuration

```bash
# Export current environment variables
grep NEO4J /home/mike/skuel/app/.env > neo4j_config_backup.txt

# Document current schema
uv run python scripts/export_schema.py > schema_backup.cypher
```

---

## Phase 2: Create AuraDB Instance

**Time: 15 minutes**

### 2.1 Sign Up / Log In

1. Visit https://console.neo4j.io/
2. Sign up or log in with existing credentials
3. Verify email if new account

### 2.2 Create Database Instance

**In AuraDB Console:**

1. Click **"New Instance"**
2. Configure instance:
   - **Name:** `skuel-production` (or your preferred name)
   - **Tier:** Select tier (see recommendations below)
   - **Region:** Choose region closest to application servers
   - **Version:** Latest stable (5.26+)
3. Click **"Create"**
4. Wait 2-3 minutes for provisioning

**Tier Recommendations:**

| Tier | Use Case | Monthly Cost | Storage | GenAI Plugin |
|------|----------|--------------|---------|--------------|
| **Free** | Testing only | $0 | 50k nodes | ❌ Not available |
| **Professional** | Production (recommended) | ~$65 | 1M nodes | ✅ Included |
| **Enterprise** | Large-scale production | Custom | Unlimited | ✅ Included |

**Recommendation:** Start with Professional tier, upgrade to Enterprise if needed.

### 2.3 Save Connection Credentials

AuraDB will display connection details once provisioned:

```
Connection URI: neo4j+s://c3a6c0c8.databases.neo4j.io
Username: neo4j
Password: <randomly-generated-password>
```

**⚠️ CRITICAL:** Save the password immediately - it's shown only once!

**Add to `.env` (production environment):**

```bash
# ============================================================================
# Neo4j AuraDB Connection
# ============================================================================
NEO4J_URI=neo4j+s://c3a6c0c8.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-auradb-password>
NEO4J_DATABASE=neo4j
```

### 2.4 Verify Connectivity

```bash
# Test connection from application server
uv run python -c "
import asyncio
import os
from neo4j import AsyncGraphDatabase

async def test():
    driver = AsyncGraphDatabase.driver(
        os.getenv('NEO4J_URI'),
        auth=('neo4j', os.getenv('NEO4J_PASSWORD'))
    )
    result = await driver.execute_query('RETURN 1 AS test')
    print(f'✅ AuraDB connection successful: {result[0][0][\"test\"]}')
    await driver.close()

asyncio.run(test())
"
```

**Expected Output:**
```
✅ AuraDB connection successful: 1
```

---

## Phase 3: Verify Embeddings Work

**Time: 5 minutes**

Embeddings are generated Python-side via HuggingFace Inference API. No Neo4j plugin setup is needed. Just ensure `HF_API_TOKEN` is set in your production environment.

### 3.1 Verify HF Token

```bash
# Ensure HF_API_TOKEN is in production .env
grep HF_API_TOKEN /home/mike/skuel/app/.env
```

### 3.2 Test Embedding Generation

```bash
uv run python -c "
from huggingface_hub import InferenceClient
import os
client = InferenceClient(model='BAAI/bge-large-en-v1.5', token=os.getenv('HF_API_TOKEN'))
result = client.feature_extraction('test')
print(f'✅ HuggingFace embeddings working! Dimension: {len(result[0]) if hasattr(result, \"__len__\") else \"unknown\"}')
"
```

---

## Phase 4: Data Migration

**Time: 1-3 hours (depends on data size)**

### 4.1 Choose Migration Method

| Method | Use Case | Time | Complexity |
|--------|----------|------|------------|
| **A: Dump & Restore** | Full database migration | 1-3 hours | Low |
| **B: Cypher Export/Import** | Selective data migration | 2-4 hours | Medium |
| **C: Fresh Start** | New production deployment | 30 minutes | Low |

**Recommendation:** Use Method A for existing production data, Method C for fresh deployments.

### 4.2 Method A: Dump & Restore (Recommended)

**Step 1: Export from Docker**

```bash
# Already done in Phase 1.2
# Backup file: ./neo4j/backups/backup_YYYYMMDD_HHMMSS.dump
```

**Step 2: Upload to AuraDB**

AuraDB Professional/Enterprise supports restore from backup:

1. In AuraDB Console → Select database
2. Click **"Import"** tab
3. Click **"Upload Backup"**
4. Select your `.dump` file
5. Click **"Start Import"**
6. Wait for completion (progress bar shown)

**Alternative: Use Cloud Storage**

If backup is large (>1GB):

```bash
# Upload to S3/GCS/Azure
aws s3 cp ./neo4j/backups/backup_*.dump s3://your-bucket/

# In AuraDB Console:
# Import → From Cloud Storage → Enter S3 URL
```

**Step 3: Verify Import**

```bash
# Check entity counts match
uv run python scripts/export_entity_counts.py \
  --output=post_migration_counts_$(date +%Y%m%d).json

# Compare counts
uv run python scripts/compare_counts.py \
  --before=pre_migration_counts_*.json \
  --after=post_migration_counts_*.json
```

**Expected Output:**
```
✅ All entity counts match
✅ No data loss detected
```

### 4.3 Method B: Cypher Export/Import

For selective migration or if Method A isn't available:

**Step 1: Export Data as Cypher**

```bash
# Export all nodes and relationships
docker exec skuel-neo4j cypher-shell -u neo4j -p <password> \
  "MATCH (n) RETURN n" --format plain > nodes_export.cypher

docker exec skuel-neo4j cypher-shell -u neo4j -p <password> \
  "MATCH ()-[r]->() RETURN r" --format plain > relationships_export.cypher
```

**Step 2: Import into AuraDB**

```bash
# Import via Neo4j Browser or cypher-shell
# Connect to AuraDB first, then run exported Cypher
```

**Note:** This method is slower and doesn't preserve all metadata. Use Method A if possible.

### 4.4 Method C: Fresh Start

For new deployments without existing data:

```bash
# No data migration needed
# Proceed to Phase 5 for schema setup
```

---

## Phase 5: Schema Migration

**Time: 15 minutes**

### 5.1 Create Constraints

**Run constraint creation script:**

```bash
# Create all constraints
uv run python scripts/create_constraints.py
```

**Or manually via Neo4j Browser:**

```cypher
// User constraints
CREATE CONSTRAINT user_uid_unique IF NOT EXISTS FOR (u:User) REQUIRE u.uid IS UNIQUE;

// Activity domain constraints (6 domains)
CREATE CONSTRAINT task_uid_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.uid IS UNIQUE;
CREATE CONSTRAINT goal_uid_unique IF NOT EXISTS FOR (g:Goal) REQUIRE g.uid IS UNIQUE;
CREATE CONSTRAINT habit_uid_unique IF NOT EXISTS FOR (h:Habit) REQUIRE h.uid IS UNIQUE;
CREATE CONSTRAINT event_uid_unique IF NOT EXISTS FOR (e:Event) REQUIRE e.uid IS UNIQUE;
CREATE CONSTRAINT choice_uid_unique IF NOT EXISTS FOR (c:Choice) REQUIRE c.uid IS UNIQUE;
CREATE CONSTRAINT principle_uid_unique IF NOT EXISTS FOR (p:Principle) REQUIRE p.uid IS UNIQUE;

// Curriculum domain constraints (3 domains)
CREATE CONSTRAINT ku_uid_unique IF NOT EXISTS FOR (k:Entity) REQUIRE k.uid IS UNIQUE;
CREATE CONSTRAINT ls_uid_unique IF NOT EXISTS FOR (l:Ls) REQUIRE l.uid IS UNIQUE;
CREATE CONSTRAINT lp_uid_unique IF NOT EXISTS FOR (lp:Lp) REQUIRE lp.uid IS UNIQUE;

// Content domain constraints (2 domains)
CREATE CONSTRAINT journal_uid_unique IF NOT EXISTS FOR (j:Journal) REQUIRE j.uid IS UNIQUE;
CREATE CONSTRAINT assignment_uid_unique IF NOT EXISTS FOR (a:Assignment) REQUIRE a.uid IS UNIQUE;

// LifePath constraint
CREATE CONSTRAINT lifepath_uid_unique IF NOT EXISTS FOR (lp:LifePath) REQUIRE lp.uid IS UNIQUE;
```

### 5.2 Create Vector Indexes

**Run vector index creation script:**

```bash
# Create vector indexes for embeddings
uv run python scripts/create_vector_indexes.py
```

**Or manually:**

```cypher
// KU vector index
CREATE VECTOR INDEX ku_embedding_idx IF NOT EXISTS
FOR (n:Entity)
ON n.embedding
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};

// Task vector index
CREATE VECTOR INDEX task_embedding_idx IF NOT EXISTS
FOR (n:Task)
ON n.embedding
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};

// Goal vector index
CREATE VECTOR INDEX goal_embedding_idx IF NOT EXISTS
FOR (n:Goal)
ON n.embedding
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};

// Habit vector index
CREATE VECTOR INDEX habit_embedding_idx IF NOT EXISTS
FOR (n:Habit)
ON n.embedding
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};
```

### 5.3 Verify Schema

```bash
# Verify constraints and indexes
uv run python scripts/verify_schema.py
```

**Expected Output:**
```
✅ Constraints: 13/13 created
✅ Vector Indexes: 4/4 active
✅ Schema migration complete
```

---

## Phase 6: Update Application Configuration

**Time: 15 minutes**

### 6.1 Update Production Environment Variables

**In production `.env` file:**

```bash
# ============================================================================
# Neo4j AuraDB Connection (Production)
# ============================================================================
NEO4J_URI=neo4j+s://c3a6c0c8.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<auradb-password>
NEO4J_DATABASE=neo4j

# ============================================================================
# Embeddings (HuggingFace Inference API)
# ============================================================================
HF_API_TOKEN=hf_your-token

# Optional overrides (defaults shown)
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
EMBEDDING_DIMENSION=1024

# Intelligence tier
INTELLIGENCE_TIER=full
```

### 6.2 Remove Docker-Specific Configuration

**Remove or comment out:**

```bash
# ❌ REMOVE - Docker-specific (not needed for AuraDB)
# NEO4J_HEAP_INIT=512m              # AuraDB manages memory
# NEO4J_HEAP_MAX=2G                 # AuraDB manages memory
# NEO4J_PAGECACHE=1G                # AuraDB manages memory
```

### 6.3 Update Code Comments (If Needed)

If your application code has Docker-specific comments, update them:

**Note:** Embeddings are Python-side (`HuggingFaceEmbeddingsService`), so no Neo4j-specific embedding config changes are needed for AuraDB. Just ensure `HF_API_TOKEN` is set in the production app environment.

---

## Phase 7: Generate Embeddings (If Fresh Start)

**Time: 30 minutes - 2 hours**

**Skip this phase if you migrated existing data with embeddings from Docker.**

### 7.1 Estimate Embedding Needs

```bash
# Count entities needing embeddings
uv run python scripts/count_entities_without_embeddings.py

# Example output:
# Ku: 1,234 entities
# Task: 3,456 entities
# Goal: 789 entities
# Total: 5,479 entities
# Estimated cost: ~$0.02 USD
# Estimated time: ~8-12 minutes
```

### 7.2 Run Batch Generation

```bash
# Generate embeddings for all entities
uv run python scripts/generate_embeddings_batch.py

# Progress output shows real-time status
```

### 7.3 Verify Embeddings

```bash
# Check coverage
uv run python scripts/verify_embeddings.py

# Expected: 100% coverage for all entity types
```

---

## Phase 8: Testing & Verification

**Time: 30 minutes**

### 8.1 Run Integration Tests

```bash
# Test database connectivity
uv run pytest tests/integration/test_neo4j_connection.py -v

# Test GenAI plugin
uv run pytest tests/integration/test_vector_search.py -v

# Test semantic search
uv run pytest tests/e2e/test_semantic_search_flow.py -v
```

**Expected:** All tests passing

### 8.2 Smoke Test Application

```bash
# Start application
uv run python main.py

# Should start without errors
```

**Check logs for:**
```
✅ Neo4j connection successful (AuraDB)
✅ GenAI embeddings service created
✅ Vector search service initialized
✅ All services bootstrapped successfully
```

### 8.3 Test Key Features

**Via Web UI (http://localhost:8000):**

1. **Create Entity:** Create a new Task/Goal/KU
   - Should save successfully
   - Should generate embedding within 30 seconds

2. **Search:** Test semantic search
   - Search for "python programming"
   - Should return relevant results with 🔍 badge

3. **Detail Page:** View entity detail
   - Check "Related Content" section
   - Should show semantically similar entities

4. **Graph Operations:** Test relationship queries
   - Navigate between related entities
   - Should load quickly (<100ms)

### 8.4 Performance Verification

```bash
# Run performance tests
uv run python scripts/benchmark_queries.py

# Compare with Docker baseline
```

**Expected Performance:**

| Operation | Docker | AuraDB | Notes |
|-----------|--------|--------|-------|
| Simple query (<10 nodes) | ~50ms | ~80ms | +30ms network latency (acceptable) |
| Complex query (100+ nodes) | ~150ms | ~120ms | AuraDB faster (better hardware) |
| Vector search (k=10) | ~60ms | ~50ms | AuraDB optimized indexes |

---

## Phase 9: Production Deployment

**Time: 30 minutes**

### 9.1 Pre-Deployment Checklist

- [ ] All tests passing in staging
- [ ] AuraDB connection verified
- [ ] Embeddings service verified
- [ ] Embeddings generated (if needed)
- [ ] Vector indexes active
- [ ] Entity counts verified
- [ ] Backups configured in AuraDB
- [ ] Monitoring enabled
- [ ] Team notified
- [ ] Rollback plan documented

### 9.2 Deploy Configuration

```bash
# Update production .env with AuraDB credentials
# (Already done in Phase 6.1)

# Restart application
systemctl restart skuel  # Or your deployment method
```

### 9.3 Post-Deployment Verification

```bash
# Run smoke tests in production
uv run python scripts/smoke_test_production.py

# Expected output:
# ✅ Application started successfully
# ✅ AuraDB connection working
# ✅ Semantic search working
# ✅ All systems operational
```

### 9.4 Monitor Initial Usage

**Watch application logs:**

```bash
tail -f /var/log/skuel/application.log | grep -i "neo4j\|auradb\|embedding"
```

**Check AuraDB Metrics:**

1. Visit AuraDB Console → Your Database → **Metrics**
2. Monitor:
   - Query latency (should be <100ms p95)
   - Connection count (should be stable)
   - CPU/Memory usage (should be <70%)
   - Disk usage (should have headroom)

**Check OpenAI Usage:**

1. Visit https://platform.openai.com/usage
2. Verify embedding costs are as expected
3. Set up billing alerts if not already configured

---

## Troubleshooting

### Issue: "Connection refused" or "Connection timeout"

**Symptoms:**
```
Error: Could not connect to neo4j+s://xxx.databases.neo4j.io
Connection timeout after 30s
```

**Check:**

1. **Verify URI format:**
   ```bash
   echo $NEO4J_URI
   # Should be: neo4j+s://xxx.databases.neo4j.io
   # NOT: bolt://localhost:7687
   ```

2. **Check AuraDB status:**
   - Log in to AuraDB Console
   - Verify database status is "Running"

3. **Verify firewall/network:**
   ```bash
   # Test network connectivity
   nc -zv xxx.databases.neo4j.io 7687
   ```

4. **Check credentials:**
   ```bash
   # Verify password is correct
   # Try manual connection via Neo4j Browser
   ```

**Solution:**
- Update `NEO4J_URI` to correct AuraDB URI
- Ensure application server can reach AuraDB (check firewall)
- Reset password in AuraDB console if needed

### Issue: "Embeddings unavailable"

**Symptoms:**
```
Warning: HF_API_TOKEN not set - embeddings will fail
```

**Solution:**
- Ensure `HF_API_TOKEN` is set in production app environment
- Get a token at https://huggingface.co/settings/tokens
- Restart the application after setting the token

### Issue: "Slow query performance"

**Symptoms:**
- Queries taking >500ms
- Application feels sluggish
- Timeouts in logs

**Check:**

1. **Verify indexes exist:**
   ```cypher
   SHOW INDEXES;
   ```

2. **Check query patterns:**
   ```bash
   # View slow queries in AuraDB Console
   # Metrics → Query Performance
   ```

3. **Monitor AuraDB resources:**
   - CPU usage >80%?
   - Memory usage >90%?
   - Consider tier upgrade

**Solution:**
- Create missing indexes: `uv run python scripts/create_constraints.py`
- Optimize queries (add WHERE clauses, use parameters)
- Upgrade AuraDB tier if consistently overloaded

### Issue: "High embedding costs"

**Note:** HuggingFace Inference API is pay-per-request (serverless). Monitor usage at https://huggingface.co/settings/billing. Embedding costs are typically minimal compared to LLM costs.

---

## Rollback Plan

### Quick Rollback: Revert to Docker

**Time: 15 minutes**

If AuraDB migration has issues, revert to Docker:

```bash
# 1. Update .env to Docker configuration
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<docker-password>

# 2. Start Docker Neo4j
cd /home/mike/skuel/infrastructure
docker compose up -d neo4j

# 3. Restore data (if needed)
docker compose run --rm neo4j \
  neo4j-admin database load neo4j \
  --from-path=/backups/backup_YYYYMMDD_HHMMSS.dump

# 4. Restart application
systemctl restart skuel
```

**Verification:**

```bash
# Test Docker connection
uv run python -c "
import asyncio, os
from neo4j import AsyncGraphDatabase
async def test():
    driver = AsyncGraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', os.getenv('NEO4J_PASSWORD')))
    await driver.execute_query('RETURN 1')
    print('✅ Docker Neo4j working')
    await driver.close()
asyncio.run(test())
"
```

### Full Rollback: Restore AuraDB Backup

**Time: 30 minutes**

If AuraDB data is corrupted but you want to stay on AuraDB:

1. **In AuraDB Console:**
   - Select database → **Backups** tab
   - Choose backup from before migration
   - Click **"Restore"**
   - Wait for completion (~10-15 minutes)

2. **Verify restoration:**
   ```bash
   # Check entity counts
   uv run python scripts/verify_entity_counts.py
   ```

---

## Cost Analysis

### Migration Costs (One-Time)

| Item | Estimated Cost | Notes |
|------|----------------|-------|
| AuraDB setup | $0 | No setup fees |
| Initial embeddings | Minimal | HuggingFace Inference API (serverless) |
| Developer time | 4-6 hours | Configuration + testing |
| **Total** | **<$1** | Primarily time investment |

### Ongoing Costs (Monthly)

| Item | Monthly Cost | Notes |
|------|--------------|-------|
| AuraDB Professional | ~$65 | Fixed monthly subscription |
| Ongoing embeddings | Minimal | HuggingFace Inference API (new entities only) |
| Backup storage | Included | Automated daily backups |
| **Total** | **~$65** | Embeddings cost negligible |

### Cost Comparison: Docker vs AuraDB

| Aspect | Docker (Development) | AuraDB (Production) |
|--------|---------------------|---------------------|
| **Infrastructure** | $0 (local resources) | $65/month (managed) |
| **Backup Storage** | Manual (own storage) | Included (automated) |
| **Monitoring** | Manual (own tools) | Included (built-in) |
| **Maintenance** | High (manual updates) | Low (automated) |
| **Uptime SLA** | None (best effort) | 99.95% (Professional) |
| **Support** | Community forums | Email support included |
| **Total Monthly** | $0 + time cost | $65 + minimal time |

**Recommendation:** Docker for development saves cost but requires maintenance. AuraDB for production provides reliability and automation worth the $65/month.

---

## Post-Migration Best Practices

### 1. Monitor AuraDB Performance

**Daily Checks (first week):**
- Query latency trends
- Connection pool usage
- Embedding generation rate
- HuggingFace API costs

**Weekly Checks (ongoing):**
- Backup verification
- Storage usage trends
- Index performance
- Error rate monitoring

### 2. Optimize Costs

```bash
# Set daily embedding limits
GENAI_MAX_DAILY_EMBEDDINGS=10000

# Only embed entities that need search
# Skip temporary/draft entities
```

**Embedding Cost Best Practices:**
- Monitor HuggingFace usage at https://huggingface.co/settings/billing
- Cache embeddings for unchanged content (version tracking handles this)
- Only embed entities that need search

### 3. Automate Backups

AuraDB automates daily backups, but verify:

```bash
# Weekly backup verification script
uv run python scripts/verify_auradb_backups.py

# Should confirm:
# ✅ Daily backups exist
# ✅ Backups are complete
# ✅ Restore tested monthly
```

### 4. Security Hardening

```bash
# Rotate AuraDB password quarterly
# Via AuraDB Console → Settings → Security

# Rotate HuggingFace API token quarterly
# Via https://huggingface.co/settings/tokens

# Audit access logs monthly
# Via AuraDB Console → Audit Logs
```

### 5. Capacity Planning

**Monitor growth trends:**
- Nodes created per month
- Relationships created per month
- Storage usage trend
- Query complexity changes

**Upgrade triggers:**
- Storage >80% of tier limit
- CPU usage >80% sustained
- Query latency >200ms p95
- Connection pool saturation

---

## Support and Resources

### Getting Help During Migration

**AuraDB Support:**
- Console: https://console.neo4j.io/support
- Email: support@neo4j.com (Professional tier)
- Community: https://community.neo4j.com

**SKUEL-Specific:**
- Check logs: `tail -f logs/skuel.log`
- Review troubleshooting section above
- Test in staging first
- Contact team lead if issues persist

### Related Documentation

- [DigitalOcean Migration Guide](./DO_MIGRATION_GUIDE.md) - Stage 2: App Platform + Droplet (prerequisite for this guide)
- [Embeddings Setup](../development/GENAI_SETUP.md) - HuggingFace embeddings setup
- [Vector Search Architecture](../architecture/SEARCH_ARCHITECTURE.md) - Technical details
- [Testing Guide](../development/TESTING.md) - Running tests
- [Production Deployment Guide](./PRODUCTION_DEPLOYMENT_GUIDE.md) - Full deployment checklist

### External Resources

- [Neo4j AuraDB Documentation](https://neo4j.com/docs/aura/)
- [ADR-049: HuggingFace Embeddings Migration](/docs/decisions/ADR-049-huggingface-embeddings-migration.md)
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
- [Vector Indexes in Neo4j](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)

---

## Migration Checklist

### Pre-Migration

- [ ] Backup Docker database created
- [ ] Entity counts exported
- [ ] Schema documented
- [ ] AuraDB account created
- [ ] Team notified of migration window

### AuraDB Setup

- [ ] AuraDB instance created (Professional tier)
- [ ] Connection verified from application
- [ ] HF_API_TOKEN configured in app environment
- [ ] Embeddings generation verified (Python-side, no plugin needed)

### Data Migration

- [ ] Migration method chosen (Dump/Cypher/Fresh)
- [ ] Data imported to AuraDB
- [ ] Entity counts verified (matches Docker)
- [ ] Relationships preserved
- [ ] No data loss detected

### Schema Setup

- [ ] Constraints created (13 total)
- [ ] Vector indexes created (4 total)
- [ ] Indexes verified active
- [ ] Schema matches Docker

### Configuration

- [ ] Production `.env` updated (neo4j+s:// URI)
- [ ] Docker-specific config removed
- [ ] HF_API_TOKEN set in production environment
- [ ] Application code reviewed (no changes needed)

### Testing

- [ ] Integration tests passing
- [ ] Semantic search working
- [ ] Vector search working
- [ ] Performance acceptable (<100ms p95)
- [ ] Entity counts match pre-migration

### Deployment

- [ ] Staging deployment successful
- [ ] Production deployment completed
- [ ] Smoke tests passing
- [ ] Monitoring enabled (AuraDB console)
- [ ] Logs verified (no errors)

### Post-Migration

- [ ] Performance monitored (48 hours)
- [ ] Costs monitored (HuggingFace + AuraDB)
- [ ] Backups verified
- [ ] Team trained on AuraDB console
- [ ] Documentation updated

---

## Frequently Asked Questions

### Q: Can I use Docker and AuraDB simultaneously?

**A:** Yes! Use Docker for development/staging, AuraDB for production:

```bash
# Development .env
NEO4J_URI=bolt://localhost:7687

# Production .env  NEO4J_URI=neo4j+s://xxx.databases.neo4j.io
```

### Q: Do I need to change my code?

**A:** No! SKUEL's Neo4j integration is abstract. Only change `.env` configuration.

### Q: What about embeddings cost?

**A:** Minimal. HuggingFace Inference API is serverless pay-per-request. Embedding costs are typically negligible.

### Q: Can I downgrade from AuraDB back to Docker?

**A:** Yes! Export AuraDB data, import into Docker. See Rollback Plan section.

### Q: What if AuraDB has an outage?

**A:** AuraDB has 99.95% uptime SLA. For critical systems, consider:
- Multi-region deployment
- Enterprise tier (99.99% SLA)
- Automated failover

### Q: How do I know if I need to upgrade tiers?

**A:** Monitor in AuraDB Console:
- Storage >80% → Upgrade
- CPU >80% sustained → Upgrade
- Query latency >200ms p95 → Optimize or upgrade

---

**Migration Complete!**

Your SKUEL instance now runs on Neo4j AuraDB with production-grade reliability, automated backups, and centralized GenAI configuration.

**Next Steps:**
- Monitor for 48 hours
- Optimize based on actual usage patterns
- Document any environment-specific changes
- Train team on AuraDB console

---

**Last Updated:** 2026-02-01
**Maintained By:** SKUEL Core Team
**Questions?** Check troubleshooting section or contact team lead

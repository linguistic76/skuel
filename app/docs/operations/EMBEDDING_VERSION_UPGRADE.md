# Embedding Version Upgrade Workflow

## Overview

When upgrading embedding models (e.g., OpenAI releases text-embedding-3-small-v2), follow this systematic workflow to re-embed all Activity domain entities with version tracking.

**Applies to:** Tasks, Goals, Habits, Events, Choices, Principles
**KUs:** Already have version tracking via `Neo4jGenAIEmbeddingsService`

---

## Prerequisites

- Database backup completed
- New embedding model tested and validated
- Sufficient OpenAI API credits (estimate cost based on entity counts)
- Downtime window scheduled (if running live migration)

---

## Step 1: Update Configuration

Update the embedding version and model in your environment:

```bash
# Set new version
export EMBEDDING_VERSION="v2"

# Set new model (if model name changed)
export GENAI_EMBEDDING_MODEL="text-embedding-3-small-v2"

# Restart application for changes to take effect
```

**Config location:** `/core/config/unified_config.py`

```python
@dataclass
class GenAIConfig:
    embedding_version: str = field(default="v1")  # Increment for upgrades
    embedding_model: str = field(default="text-embedding-3-small")
```

---

## Step 2: Identify Entities Needing Re-embedding

Query the database to find entities with old version:

### Count by Domain

```cypher
MATCH (n)
WHERE n.embedding_version IS NOT NULL
  AND n.embedding_version < 'v2'
  AND (n:Task OR n:Goal OR n:Habit OR n:Event OR n:Choice OR n:Principle)
RETURN labels(n)[0] as entity_type, count(n) as count
ORDER BY count DESC
```

**Expected output:**
```
entity_type | count
------------|------
Task        | 1,245
Goal        |   342
Habit       |   189
Event       |   567
Choice      |    78
Principle   |    34
```

### Get Specific UIDs (for batch processing)

```cypher
MATCH (n:Task)
WHERE n.embedding_version = 'v1'
RETURN n.uid
LIMIT 100
```

---

## Step 3: Cost Estimation

**OpenAI Pricing (as of 2026):**
- text-embedding-3-small: $0.00002 per 1,000 tokens
- Average entity: ~500 tokens
- Formula: `(entity_count * 500 * 0.00002) / 1000`

**Example:**
```
2,455 entities * 500 tokens = 1,227,500 tokens
1,227,500 * $0.00002 / 1000 = $0.0245 (~2.5 cents)
```

---

## Step 4: Run Re-embedding Migration

**Option A: Background Worker (Recommended)**

The embedding worker will automatically use the new version for new embeddings. For existing entities:

```bash
# Publish EmbeddingRequested events for all old-version entities
poetry run python scripts/migrations/reembed_activity_domains.py \
    --from-version v1 \
    --to-version v2 \
    --batch-size 100
```

**Option B: Direct Cypher (for manual control)**

```cypher
// Re-embed all Tasks with v1 embeddings
MATCH (n:Task)
WHERE n.embedding_version = 'v1'
WITH n
LIMIT 100
// Trigger re-embedding via application layer
```

---

## Step 5: Monitor Progress

### Check Version Distribution

```cypher
MATCH (n)
WHERE n.embedding_version IS NOT NULL
  AND (n:Task OR n:Goal OR n:Habit OR n:Event OR n:Choice OR n:Principle)
RETURN
  n.embedding_version as version,
  labels(n)[0] as entity_type,
  count(n) as count
ORDER BY version, entity_type
```

**Expected progression:**
```
version | entity_type | count
--------|-------------|------
v1      | Task        | 1,000  (decreasing)
v1      | Goal        |   300  (decreasing)
v2      | Task        |   245  (increasing)
v2      | Goal        |    42  (increasing)
```

### Worker Metrics

Check embedding worker status:

```bash
curl http://localhost:8000/api/background/embedding-worker/metrics
```

**Response:**
```json
{
  "total_processed": 1245,
  "total_success": 1240,
  "total_failed": 5,
  "queue_size": 50,
  "success_rate": 99.6
}
```

---

## Step 6: Verify Upgrade Complete

### Confirm All Entities Updated

```cypher
MATCH (n)
WHERE n.embedding_version IS NOT NULL
  AND n.embedding_version < 'v2'
  AND (n:Task OR n:Goal OR n:Habit OR n:Event OR n:Choice OR n:Principle)
RETURN count(n) as remaining
```

**Expected:** `remaining: 0`

### Validate Embedding Quality

```cypher
// Check sample embeddings have correct model and version
MATCH (n:Task)
WHERE n.embedding_version = 'v2'
RETURN
  n.uid,
  n.embedding_version,
  n.embedding_model,
  n.embedding_updated_at
LIMIT 5
```

---

## Rollback Strategy

If issues arise during migration:

### 1. Stop Embedding Worker

```bash
# Set config to pause new embeddings
export GENAI_ENABLED="false"
# Restart application
```

### 2. Revert Configuration

```bash
# Roll back to previous version
export EMBEDDING_VERSION="v1"
export GENAI_EMBEDDING_MODEL="text-embedding-3-small"
```

### 3. Restore from Backup (if needed)

```bash
# Restore Neo4j backup
neo4j-admin restore --from=/backups/pre-upgrade
```

---

## Future Considerations

### Automatic Version Detection

**Future enhancement:** Detect model changes automatically:

```python
# In EmbeddingBackgroundWorker
def _detect_version_mismatch(self) -> bool:
    """Check if model changed since last embedding"""
    current_model = self.config.genai.embedding_model
    stored_model = await self._get_latest_embedding_model()
    return current_model != stored_model
```

### Incremental Re-embedding

**Strategy:** Re-embed in priority order:
1. Active tasks (status != COMPLETED)
2. Recent entities (created_at > 30 days ago)
3. High-value entities (linked to life path goals)
4. Historical/archived entities

---

## Related Documentation

- `/docs/architecture/EMBEDDING_VERSION_TRACKING.md` - Architecture decision
- `/scripts/migrations/backfill_activity_embedding_versions.py` - Initial backfill
- `/core/services/background/embedding_worker.py` - Worker implementation
- `/core/config/unified_config.py` - Configuration

---

## Version History

| Version | Date       | Change |
|---------|------------|--------|
| v1      | 2026-01-29 | Initial Activity domain embeddings |
| v2      | TBD        | Model upgrade (when implemented) |

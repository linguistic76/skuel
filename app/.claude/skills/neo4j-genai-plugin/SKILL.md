---
name: neo4j-genai-plugin
description: Expert guide to Neo4j GenAI plugin integration for AI-powered graph features. Use when working with embeddings, vector search, RAG workflows, semantic relationships, text generation, or when the user mentions GenAI plugin, genai.vector.encode, ai.text.embed, vector indexes, hybrid search, local Neo4j Docker setup, or LLM integration with Neo4j.
allowed-tools: Read, Grep, Glob
---

# Neo4j GenAI Plugin - Expert Guide

Database-native AI capabilities for embeddings, vector search, RAG workflows, and semantic relationships.

**Current Setup:** Docker-based Neo4j (development)
**Production Migration:** See `/docs/deployment/AURADB_MIGRATION_GUIDE.md`

## Core Philosophy

### Database-Native Embeddings

Neo4j GenAI plugin brings AI capabilities directly into the database via Cypher functions:
- **`genai.vector.encode()`** - Single text → vector embedding (requires token parameter)
- **`genai.vector.encodeBatch()`** - Multiple texts → vectors (50 optimal batch size, requires token parameter)
- **`ai.text.completion()`** - Text generation with context
- **`ai.text.chat()`** - Multi-turn conversations with chat IDs

**IMPORTANT:** Local Neo4j requires passing OpenAI API key as `token` parameter per-query. AuraDB configures it at database level.

Embeddings are stored as graph properties (`embedding: List[Float]`), not external state. This enables:
- Vector similarity search via `db.index.vector.queryNodes()`
- Graph + semantic hybrid queries
- No external vector database dependency
- Atomic updates with graph mutations

### Cost Model & Graceful Degradation

**Cost:** OpenAI text-embedding-3-small costs ~$0.02 per 1M tokens
- 5,000 KUs with 500-token descriptions = ~$0.03 total
- Batch operations are cost-effective for bulk ingestion

**Graceful Degradation (SKUEL Requirement):**
```python
# App MUST work without GenAI
if not genai_config.enabled:
    return await fallback_keyword_search(query)

# Feature detection pattern
embedding_result = await embeddings_service.generate_embedding(text)
if embedding_result.is_error:
    logger.info("Falling back to keyword search")
    return await fulltext_search(query)
```

SKUEL separates analytics (graph-only, always available) from AI (LLM-dependent, optional):
- `BaseAnalyticsService` - Graph analytics, NO AI dependencies
- `BaseAIService` - LLM features, graceful degradation

### When to Use GenAI Plugin vs Python Clients

| Use Case | GenAI Plugin (Cypher) | Python Client (OpenAI SDK) |
|----------|----------------------|---------------------------|
| Embeddings during ingestion | ✅ Atomic with graph write | ❌ Separate operation |
| Vector search in Cypher | ✅ Native `db.index.vector.*` | ❌ Requires external index |
| Batch embeddings (50+) | ✅ `ai.text.embedBatch()` | ⚠️ Manual batching |
| Text generation | ⚠️ Simple prompts only | ✅ Complex prompts, streaming |
| Multi-turn chat | ⚠️ Basic with chat IDs | ✅ Full conversation API |
| Cost tracking | ❌ No native support | ✅ Token usage in response |

**SKUEL Pattern:** Use GenAI plugin for embeddings/search, Python clients for complex generation.

## Quick Start

### Core Functions Reference

| Function | Purpose | Returns | Example |
|----------|---------|---------|---------|
| `genai.vector.encode(text, provider, config)` | Single embedding | `List[Float]` (1536-dim) | `genai.vector.encode(ku.content, 'OpenAI', {token: $key, model: 'text-embedding-3-small'})` |
| `genai.vector.encodeBatch(texts, provider, config)` | Batch embeddings | `List[List[Float]]` | `genai.vector.encodeBatch([t1, t2, t3], 'OpenAI', {token: $key, model: 'text-embedding-3-small'})` |
| `db.index.vector.queryNodes(index, k, vector)` | Vector search | Nodes + scores | `db.index.vector.queryNodes('ku_embeddings', 10, $vector)` |
| `ai.text.completion(prompt, config)` | Text generation | String | `ai.text.completion("Explain: " + text, {model: "gpt-4o-mini"})` |
| `ai.text.chat(messages, config)` | Multi-turn chat | String | `ai.text.chat([{role: "user", content: q}], {chatId: "session1"})` |

### Docker (Current) vs AuraDB (Production) Configuration

**Critical Difference:** API key configuration differs between Docker development and AuraDB production.

| Configuration | Docker (Development) | AuraDB (Production) |
|---------------|---------------------|---------------------|
| **Plugin Installation** | Auto-loaded via `NEO4J_PLUGINS='["genai"]'` | Enabled via console |
| **API Key Location** | Passed per-query as `token` parameter | Configured at database level |
| **Connection** | `bolt://localhost:7687` | `neo4j+s://xxx.databases.neo4j.io` |
| **Neo4j Version** | 2025.12.1+ (calendar versioning) | Managed by Neo4j |
| **Function Syntax** | `genai.vector.encode(text, 'OpenAI', {token: $key, ...})` | Same, but token optional if configured |

**Local Docker Setup (for development):**

```yaml
# docker-compose.yml
services:
  neo4j:
    image: neo4j:2025.12.1
    environment:
      NEO4J_PLUGINS: '["genai"]'  # Auto-loads GenAI plugin
      NEO4J_AUTH: "neo4j/your-password"
      NEO4J_genai_openai_api__key: "${OPENAI_API_KEY}"  # Optional, for convenience
      NEO4J_dbms_security_procedures_unrestricted: "genai.*"
      NEO4J_dbms_security_procedures_allowlist: "genai.*"
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - ./neo4j/data:/data
      - ./neo4j/logs:/logs
```

**Important:** Even with environment variable set, local setups typically require passing `token` explicitly in Cypher queries.

**AuraDB Setup:** No manual configuration needed - GenAI plugin comes pre-configured with API key management.

### Configuration Checklist

**Environment Variables (`.env`):**
```bash
# GenAI plugin (required for embeddings/vector search)
GENAI_ENABLED=true
GENAI_EMBEDDING_MODEL=text-embedding-3-small
GENAI_EMBEDDING_DIMENSIONS=1536
GENAI_BATCH_SIZE=50

# OpenAI (required for GenAI plugin)
OPENAI_API_KEY=sk-...

# Vector search configuration
VECTOR_SEARCH_DEFAULT_K=10
VECTOR_SEARCH_MIN_SIMILARITY=0.7
VECTOR_SEARCH_HYBRID_WEIGHT=0.7  # 70% vector, 30% fulltext
```

**Neo4j Setup:**
- **Local Docker:** Set `NEO4J_PLUGINS='["genai"]'` to auto-load (Neo4j 2025.12.1+)
- **AuraDB Professional:** GenAI plugin pre-installed
- **Self-hosted:** Plugin bundled with Neo4j 5.26+ in `/products` directory

**Verification Command:**
```bash
poetry run python scripts/verify_genai_setup.py
```

Expected output:
```
✓ GenAI plugin available
✓ OpenAI API key configured
✓ Embedding generation works (1536 dimensions)
✓ Vector indexes: ku_embeddings, ls_embeddings, lp_embeddings, user_embeddings
```

### First Embedding Example

**Generate and store embedding (local Neo4j with token parameter):**
```cypher
MATCH (ku:KnowledgeUnit {uid: 'ku.python-basics'})
SET ku.embedding = genai.vector.encode(
    ku.content,
    'OpenAI',
    {
        token: $openai_api_key,
        model: 'text-embedding-3-small',
        dimensions: 1536
    }
),
    ku.embedding_version = 'v2'
RETURN ku.uid, size(ku.embedding) AS dimensions
```

**Note:** `$openai_api_key` parameter must be passed from application code. AuraDB can omit `token` if configured at database level.

**Search similar KUs:**
```cypher
MATCH (query:KnowledgeUnit {uid: 'ku.python-basics'})
CALL db.index.vector.queryNodes('ku_embeddings', 10, query.embedding)
YIELD node, score
RETURN node.uid, node.title, score
ORDER BY score DESC
```

## Architecture Overview

### Three-Layer Model

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Domain Services (Activity, Curriculum, Content)   │
│ - UnifiedIngestionService (auto-embedding Priority 1)       │
│ - SearchRouter (hybrid search Priority 1)                   │
│ - LpIntelligenceService (semantic scoring Priority 1)       │
│ - AskesisService (RAG workflows Priority 2)                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: GenAI Services (Embeddings, Vector Search)         │
│ - Neo4jGenAIEmbeddingsService (version tracking, batching)  │
│ - Neo4jVectorSearchService (hybrid search, RRF, learning)   │
└─────────────────────────────────────────────────────────────┐
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Neo4j GenAI Plugin (Database-Native)               │
│ - genai.vector.encode() / genai.vector.encodeBatch()        │
│ - db.index.vector.queryNodes()                              │
│ - ai.text.completion() / ai.text.chat()                     │
└─────────────────────────────────────────────────────────────┘
```

**Service Hierarchy:**
- **Domain services** - Business logic, protocol-based
- **GenAI services** - Embedding/search wrappers, Result[T] pattern
- **Neo4j plugin** - Database-native AI functions (Cypher)

### Vector Index Architecture

SKUEL has **4 HNSW vector indexes** configured:

| Index Name | Label | Property | Dimensions | Similarity | Provider |
|-----------|-------|----------|------------|------------|----------|
| `ku_embeddings` | KnowledgeUnit | `embedding` | 1536 | Cosine | OpenAI |
| `ls_embeddings` | LearningSequence | `embedding` | 1536 | Cosine | OpenAI |
| `lp_embeddings` | LearningPath | `embedding` | 1536 | Cosine | OpenAI |
| `user_embeddings` | User | `embedding` | 1536 | Cosine | OpenAI |

**Index Configuration (HNSW parameters):**
```cypher
CREATE VECTOR INDEX ku_embeddings IF NOT EXISTS
FOR (ku:KnowledgeUnit)
ON (ku.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
}
```

**HNSW Tuning (default values are optimal for most use cases):**
- `m`: 16 (connections per layer, higher = better recall, slower build)
- `efConstruction`: 200 (search effort during build, higher = better quality, slower)
- `efSearch`: 10 (runtime search effort, higher = better recall, slower queries)

SKUEL uses defaults - only tune if benchmarks show issues.

### Key Files

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| Embeddings Service | `/core/services/neo4j_genai_embeddings_service.py` | 492 | Version tracking, batch ops, error handling |
| Vector Search Service | `/core/services/neo4j_vector_search_service.py` | 980 | Hybrid search, RRF, learning-aware search |
| Ingestion (Integration) | `/core/services/ingestion/unified_ingestion_service.py` | 1200+ | Auto-embedding during KU ingestion |
| Search Router | `/adapters/inbound/search/search_router.py` | 800+ | Unified search orchestration |
| Config | `/core/config/unified_config.py` | 1000+ | VectorSearchConfig, GenAIConfig |
| Verification Script | `/scripts/verify_genai_setup.py` | 200+ | Setup validation |

## Cypher Patterns

### Single Embedding Generation

**Basic pattern (local Neo4j):**
```cypher
MATCH (ku:KnowledgeUnit {uid: $uid})
SET ku.embedding = genai.vector.encode(
    ku.content,
    'OpenAI',
    {
        token: $openai_api_key,
        model: 'text-embedding-3-small',
        dimensions: 1536
    }
)
RETURN ku.uid, size(ku.embedding) AS dimensions
```

**With version tracking (recommended):**
```cypher
MATCH (ku:KnowledgeUnit {uid: $uid})
WHERE ku.embedding IS NULL OR ku.embedding_version <> 'v2'
SET ku.embedding = genai.vector.encode(
    ku.content,
    'OpenAI',
    {
        token: $openai_api_key,
        model: $model,
        dimensions: $dimensions
    }
),
    ku.embedding_version = 'v2',
    ku.embedding_updated_at = datetime()
RETURN ku.uid
```

**Conditional generation (cost optimization):**
```cypher
MATCH (ku:KnowledgeUnit {uid: $uid})
WITH ku,
     CASE WHEN ku.embedding IS NULL THEN true
          WHEN ku.embedding_version <> $current_version THEN true
          ELSE false END AS needs_update
WHERE needs_update = true
SET ku.embedding = genai.vector.encode(
    ku.content,
    'OpenAI',
    {
        token: $openai_api_key,
        model: $model,
        dimensions: $dimensions
    }
),
    ku.embedding_version = $current_version
RETURN ku.uid
```

### Batch Embeddings

**Optimal batch size: 50 items** (balance between API limits and throughput)

**Important:** `genai.vector.encodeBatch()` requires passing texts and configuration in specific format.

```cypher
// Batch embedding pattern (simplified - use from Python driver)
CALL genai.vector.encodeBatch(
    $texts,  // List of texts from Python
    'OpenAI',
    {
        token: $openai_api_key,
        model: 'text-embedding-3-small',
        dimensions: 1536
    }
)
YIELD index, embedding
RETURN index, embedding
ORDER BY index
```

**Python driver pattern (recommended for batch operations):**
```python
# See Python Integration section below for complete batch embedding pattern
# Batch operations are better handled in Python with proper error isolation
```

**Resilient batch with fallback (individual embeddings):**
```cypher
MATCH (ku:KnowledgeUnit)
WHERE ku.embedding IS NULL
WITH collect(ku) AS batch LIMIT 50
CALL {
  WITH batch
  UNWIND batch AS ku
  SET ku.embedding = genai.vector.encode(
      ku.content,
      'OpenAI',
      {
          token: $openai_api_key,
          model: 'text-embedding-3-small',
          dimensions: 1536
      }
  ),
      ku.embedding_version = 'v2'
  RETURN count(ku) AS success_count
}
RETURN success_count
```

### Store with Metadata (Version Tracking)

**Full metadata pattern:**
```cypher
MATCH (ku:KnowledgeUnit {uid: $uid})
SET ku.embedding = genai.vector.encode(
    ku.content,
    'OpenAI',
    {
        token: $openai_api_key,
        model: $model,
        dimensions: $dimensions
    }
),
    ku.embedding_version = $version,          // 'v2' = text-embedding-3-small
    ku.embedding_model = $model,              // 'text-embedding-3-small'
    ku.embedding_dimensions = $dimensions,    // 1536
    ku.embedding_updated_at = datetime(),
    ku.embedding_cost_tokens = size(ku.content) / 4  // Approximate
RETURN ku.uid
```

**Why version tracking matters:**
- Model changes (ada-002 → text-embedding-3-small) require re-embedding
- Avoid unnecessary API calls (check version before regenerating)
- Cost tracking (sum tokens across all embeddings)
- Debugging (when did this embedding get created?)

### Vector Similarity Search

**Basic vector search (top-k):**
```cypher
CALL db.index.vector.queryNodes('ku_embeddings', $k, $query_vector)
YIELD node, score
RETURN node.uid, node.title, score
ORDER BY score DESC
```

**With similarity threshold:**
```cypher
CALL db.index.vector.queryNodes('ku_embeddings', $k, $query_vector)
YIELD node, score
WHERE score >= $min_similarity  // e.g., 0.7
RETURN node.uid, node.title, score
ORDER BY score DESC
```

**Graph-enriched search (expand with relationships):**
```cypher
CALL db.index.vector.queryNodes('ku_embeddings', $k, $query_vector)
YIELD node AS ku, score
MATCH (ku)-[:PART_OF]->(ls:LearningSequence)
MATCH (ls)-[:PART_OF]->(lp:LearningPath)
RETURN ku.uid, ku.title, score,
       ls.title AS sequence,
       lp.title AS path
ORDER BY score DESC
```

### Hybrid Search (Vector + Fulltext)

**Reciprocal Rank Fusion (RRF) - combines vector and keyword search:**

```cypher
// 1. Vector search
CALL db.index.vector.queryNodes('ku_embeddings', $k, $query_vector)
YIELD node AS vector_node, score AS vector_score
WITH collect({node: vector_node, score: vector_score, rank: apoc.coll.indexOf(collect(vector_node), vector_node) + 1}) AS vector_results

// 2. Fulltext search
CALL db.index.fulltext.queryNodes('ku_fulltext', $query_text)
YIELD node AS text_node, score AS text_score
WITH vector_results, collect({node: text_node, score: text_score, rank: apoc.coll.indexOf(collect(text_node), text_node) + 1}) AS text_results

// 3. Reciprocal Rank Fusion (RRF)
UNWIND vector_results + text_results AS result
WITH result.node AS node,
     sum(1.0 / (60 + result.rank)) AS rrf_score
RETURN node.uid, node.title, rrf_score
ORDER BY rrf_score DESC
LIMIT $k
```

**Weighted hybrid (70% vector, 30% fulltext):**
```cypher
// Combine scores with weights
WITH vector_score * $vector_weight + text_score * $text_weight AS hybrid_score
RETURN node.uid, hybrid_score
ORDER BY hybrid_score DESC
```

**SKUEL default:** 70% vector, 30% fulltext (configurable via `VECTOR_SEARCH_HYBRID_WEIGHT`)

### Semantic Relationship Inference

**Find semantically similar entities (create SEMANTICALLY_RELATED):**

```cypher
MATCH (source:KnowledgeUnit {uid: $source_uid})
WHERE source.embedding IS NOT NULL
CALL db.index.vector.queryNodes('ku_embeddings', 20, source.embedding)
YIELD node AS target, score
WHERE target.uid <> source.uid
  AND score >= $similarity_threshold  // e.g., 0.85
  AND NOT (source)-[:SEMANTICALLY_RELATED]-(target)
MERGE (source)-[r:SEMANTICALLY_RELATED]-(target)
SET r.similarity_score = score,
    r.created_at = datetime(),
    r.inferred = true
RETURN count(r) AS relationships_created
```

**Batch semantic enrichment (post-ingestion):**
```cypher
MATCH (ku:KnowledgeUnit)
WHERE ku.embedding IS NOT NULL
  AND NOT (ku)-[:SEMANTICALLY_RELATED]-()
WITH ku LIMIT 100
CALL {
  WITH ku
  CALL db.index.vector.queryNodes('ku_embeddings', 10, ku.embedding)
  YIELD node AS similar, score
  WHERE similar.uid <> ku.uid AND score >= 0.85
  MERGE (ku)-[r:SEMANTICALLY_RELATED]-(similar)
  SET r.similarity_score = score
  RETURN count(r) AS links
}
RETURN sum(links) AS total_relationships
```

### Anti-Patterns (What NOT to Do)

❌ **Embedding without version tracking:**
```cypher
// BAD - no way to know if re-embedding needed
SET ku.embedding = genai.vector.encode(ku.content, 'OpenAI', {token: $key, model: 'text-embedding-3-small'})
```

✅ **Good - version tracked:**
```cypher
SET ku.embedding = genai.vector.encode(ku.content, 'OpenAI', {token: $key, model: 'text-embedding-3-small'}),
    ku.embedding_version = 'v2'
```

❌ **Small batches (inefficient):**
```cypher
// BAD - 10 items per batch = many API calls
WITH collect(ku) AS batch LIMIT 10
```

✅ **Good - 50 items optimal:**
```cypher
WITH collect(ku) AS batch LIMIT 50
```

❌ **Ignoring similarity threshold:**
```cypher
// BAD - returns low-quality matches
CALL db.index.vector.queryNodes('ku_embeddings', 100, $vector)
YIELD node, score
RETURN node
```

✅ **Good - filter by similarity:**
```cypher
CALL db.index.vector.queryNodes('ku_embeddings', 100, $vector)
YIELD node, score
WHERE score >= 0.7  // Only high-quality matches
RETURN node, score
```

❌ **Re-embedding unchanged content:**
```cypher
// BAD - wastes money
MATCH (ku:KnowledgeUnit)
SET ku.embedding = genai.vector.encode(ku.content, 'OpenAI', {...})
```

✅ **Good - conditional update:**
```cypher
MATCH (ku:KnowledgeUnit)
WHERE ku.embedding IS NULL OR ku.embedding_version <> 'v2'
SET ku.embedding = genai.vector.encode(ku.content, 'OpenAI', {token: $key, ...})
```

## Python Integration

### Neo4jGenAIEmbeddingsService Usage

**Location:** `/core/services/neo4j_genai_embeddings_service.py` (492 lines)

**Initialization:**
```python
from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
from core.config.unified_config import settings

embeddings_service = Neo4jGenAIEmbeddingsService(
    driver=neo4j_driver,
    config=settings.genai
)
```

**Generate single embedding:**
```python
from core.result import Result

embedding_result: Result[list[float]] = await embeddings_service.generate_embedding(
    text="Python is a high-level programming language"
)

if embedding_result.is_error:
    logger.error(f"Embedding failed: {embedding_result.error}")
    return await fallback_keyword_search(query)

embedding = embedding_result.value  # List[float], 1536 dimensions
```

**Batch embeddings (50 optimal):**
```python
texts = [ku.content for ku in knowledge_units[:50]]

batch_result: Result[list[list[float]]] = await embeddings_service.generate_embeddings_batch(
    texts=texts
)

if batch_result.is_error:
    # Fallback to individual embeddings
    embeddings = []
    for text in texts:
        result = await embeddings_service.generate_embedding(text)
        if result.is_error:
            embeddings.append(None)  # Mark failure
        else:
            embeddings.append(result.value)
else:
    embeddings = batch_result.value
```

**Store embedding with metadata:**
```python
store_result: Result[None] = await embeddings_service.store_embedding(
    uid="ku.python-basics",
    embedding=embedding,
    version="v2",
    model="text-embedding-3-small"
)
```

**Ensure embedding (conditional generation):**
```python
# Only generates if missing or version mismatch
ensure_result: Result[list[float]] = await embeddings_service.ensure_embedding(
    uid="ku.python-basics",
    text=ku.content,
    current_version="v2"
)

if ensure_result.is_error:
    logger.warning(f"Could not ensure embedding for {uid}")
else:
    embedding = ensure_result.value  # Existing or newly generated
```

### Neo4jVectorSearchService Usage

**Location:** `/core/services/neo4j_vector_search_service.py` (980 lines)

**Initialization:**
```python
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

vector_search = Neo4jVectorSearchService(
    driver=neo4j_driver,
    embeddings_service=embeddings_service,
    config=settings.vector_search
)
```

**Basic vector search:**
```python
from core.models.search.search_models import VectorSearchResult

search_result: Result[list[VectorSearchResult]] = await vector_search.search_by_text(
    query_text="What is Python?",
    index_name="ku_embeddings",
    k=10,
    min_similarity=0.7
)

if not search_result.is_error:
    for result in search_result.value:
        print(f"{result.uid}: {result.title} (score: {result.similarity_score:.3f})")
```

**Hybrid search (vector + fulltext):**
```python
hybrid_result: Result[list[VectorSearchResult]] = await vector_search.hybrid_search(
    query_text="Python programming",
    vector_index="ku_embeddings",
    fulltext_index="ku_fulltext",
    k=10,
    vector_weight=0.7,  # 70% semantic, 30% keyword
    fulltext_weight=0.3
)
```

**Learning-aware search (personalized):**
```python
from core.services.user.unified_user_context import UserContext

# Boost based on user's learning state
personalized_result = await vector_search.learning_aware_search(
    query_text="Advanced Python concepts",
    user_context=user_context,  # Contains mastery levels
    index_name="ku_embeddings",
    k=20
)

# Applies boosts:
# - NOT_STARTED: +15% (new material)
# - IN_PROGRESS: +10% (current focus)
# - MASTERED: -20% (already learned)
```

### Error Handling with Result[T]

**Standard pattern:**
```python
from core.result import Result
from core.errors import Errors

async def semantic_search(query: str) -> Result[list[dict[str, Any]]]:
    # Step 1: Generate query embedding
    embedding_result = await embeddings_service.generate_embedding(query)
    if embedding_result.is_error:
        return Errors.integration(
            "Failed to generate query embedding",
            details={"error": str(embedding_result.error)}
        )

    # Step 2: Vector search
    search_result = await vector_search.search_by_vector(
        vector=embedding_result.value,
        index_name="ku_embeddings",
        k=10
    )
    if search_result.is_error:
        return Errors.database(
            "Vector search failed",
            details={"error": str(search_result.error)}
        )

    # Step 3: Success
    return Result.ok([r.to_dict() for r in search_result.value])
```

**Graceful degradation pattern:**
```python
async def search_with_fallback(query: str) -> Result[list[dict[str, Any]]]:
    # Try semantic search first
    if genai_config.enabled:
        semantic_result = await semantic_search(query)
        if not semantic_result.is_error:
            return semantic_result
        logger.info("Semantic search failed, falling back to keyword")

    # Fallback to keyword search (always available)
    return await keyword_search(query)
```

### Batch Operations with Resilience

**Batch with error isolation:**
```python
async def embed_knowledge_units(uids: list[str]) -> tuple[int, int]:
    """Returns (success_count, failure_count)."""
    successes = 0
    failures = 0

    # Process in batches of 50
    for i in range(0, len(uids), 50):
        batch_uids = uids[i:i+50]

        # Try batch operation first
        batch_result = await embeddings_service.embed_batch(batch_uids)

        if not batch_result.is_error:
            successes += len(batch_uids)
            continue

        # Batch failed - process individually for error isolation
        logger.warning(f"Batch failed, processing {len(batch_uids)} items individually")
        for uid in batch_uids:
            individual_result = await embeddings_service.embed_single(uid)
            if individual_result.is_error:
                failures += 1
                logger.error(f"Failed to embed {uid}: {individual_result.error}")
            else:
                successes += 1

    return successes, failures
```

## SKUEL Integration Patterns

### Priority 1: Auto-Embedding During Ingestion

**Integration Point:** `UnifiedIngestionService.ingest_single_ku()`

**Current state:** Manual embedding via separate script
**Target state:** Automatic embedding during KU creation

**Implementation:**
```python
# In /core/services/ingestion/unified_ingestion_service.py

async def ingest_single_ku(
    self,
    content: str,
    metadata: dict[str, Any]
) -> Result[str]:
    # 1. Create KU in graph
    ku_result = await self.ku_service.create_knowledge_unit(
        request=KuRequest(
            title=metadata["title"],
            content=content,
            domain=metadata.get("domain")
        ),
        user_uid=metadata["user_uid"]
    )

    if ku_result.is_error:
        return ku_result

    ku_uid = ku_result.value

    # 2. Generate and store embedding (NEW)
    if self.genai_config.enabled:
        embedding_result = await self.embeddings_service.ensure_embedding(
            uid=ku_uid,
            text=content,
            current_version="v2"
        )

        if embedding_result.is_error:
            # Log warning but don't fail ingestion
            logger.warning(f"Embedding generation failed for {ku_uid}: {embedding_result.error}")

    # 3. Return success
    return Result.ok(ku_uid)
```

**Benefits:**
- Embeddings always up-to-date
- No separate embedding script needed
- Graceful degradation (ingestion succeeds even if embedding fails)

### Priority 1: Semantic Search Enhancement

**Integration Point:** `SearchRouter.faceted_search()` and `SearchRouter.advanced_search()`

**Current state:** Keyword-only search
**Target state:** Hybrid search (vector + keyword) by default

**Implementation:**
```python
# In /adapters/inbound/search/search_router.py

async def faceted_search(
    self,
    query: str,
    domains: list[EntityType],
    user_context: UserContext,
    k: int = 20
) -> Result[list[dict[str, Any]]]:
    # Use hybrid search if GenAI enabled
    if self.genai_config.enabled:
        hybrid_result = await self._hybrid_search(query, domains, k)
        if not hybrid_result.is_error:
            return hybrid_result
        logger.info("Hybrid search failed, falling back to keyword")

    # Fallback to keyword search
    return await self._keyword_search(query, domains, k)

async def _hybrid_search(
    self,
    query: str,
    domains: list[EntityType],
    k: int
) -> Result[list[dict[str, Any]]]:
    # Generate query embedding
    embedding_result = await self.embeddings_service.generate_embedding(query)
    if embedding_result.is_error:
        return embedding_result  # Propagate error for fallback

    # Execute hybrid search per domain
    all_results = []
    for domain in domains:
        index_name = f"{domain.value}_embeddings"

        domain_results = await self.vector_search.hybrid_search(
            query_text=query,
            vector_index=index_name,
            fulltext_index=f"{domain.value}_fulltext",
            k=k,
            vector_weight=0.7,  # 70% semantic, 30% keyword
            fulltext_weight=0.3
        )

        if not domain_results.is_error:
            all_results.extend(domain_results.value)

    # Sort by hybrid score and return top-k
    all_results.sort(key=lambda x: x.similarity_score, reverse=True)
    return Result.ok([r.to_dict() for r in all_results[:k]])
```

### Priority 1: Semantic Relationship Inference

**Integration Point:** Post-ingestion enrichment (new service method)

**Implementation:**
```python
# In /core/services/knowledge/ku_intelligence_service.py

async def infer_semantic_relationships(
    self,
    ku_uid: str,
    similarity_threshold: float = 0.85
) -> Result[int]:
    """Find and create SEMANTICALLY_RELATED relationships based on embedding similarity."""

    # Get KU embedding
    ku_result = await self.backend.get(ku_uid)
    if ku_result.is_error:
        return ku_result

    ku = ku_result.value
    if not ku.embedding:
        return Errors.validation("KU has no embedding")

    # Find similar KUs
    similar_result = await self.vector_search.search_by_vector(
        vector=ku.embedding,
        index_name="ku_embeddings",
        k=20,
        min_similarity=similarity_threshold
    )

    if similar_result.is_error:
        return similar_result

    # Create relationships (exclude self)
    relationships_created = 0
    for result in similar_result.value:
        if result.uid == ku_uid:
            continue

        create_result = await self.relationship_service.create_bidirectional_relationship(
            source_uid=ku_uid,
            target_uid=result.uid,
            relationship_type=RelationshipName.SEMANTICALLY_RELATED,
            properties={
                "similarity_score": result.similarity_score,
                "inferred": True,
                "created_at": datetime.now().isoformat()
            }
        )

        if not create_result.is_error:
            relationships_created += 1

    return Result.ok(relationships_created)
```

**Batch enrichment (for existing KUs):**
```python
async def enrich_all_kus_with_semantic_relationships(
    self,
    batch_size: int = 100
) -> Result[dict[str, int]]:
    """Batch process all KUs for semantic relationship inference."""
    stats = {"processed": 0, "relationships_created": 0, "errors": 0}

    # Get all KUs with embeddings
    query = """
    MATCH (ku:KnowledgeUnit)
    WHERE ku.embedding IS NOT NULL
      AND NOT (ku)-[:SEMANTICALLY_RELATED]-()
    RETURN ku.uid AS uid
    LIMIT $batch_size
    """

    while True:
        result = await self.backend.driver.execute_query(query, batch_size=batch_size)
        records = result.records

        if not records:
            break

        for record in records:
            ku_uid = record["uid"]
            infer_result = await self.infer_semantic_relationships(ku_uid)

            stats["processed"] += 1
            if infer_result.is_error:
                stats["errors"] += 1
            else:
                stats["relationships_created"] += infer_result.value

        logger.info(f"Processed {stats['processed']} KUs, created {stats['relationships_created']} relationships")

    return Result.ok(stats)
```

### Priority 1: Learning Path Optimization

**Integration Point:** `LpIntelligenceService.recommend_next_learning_steps()`

**Current state:** Graph-based recommendations (prerequisites, relationships)
**Target state:** Semantic similarity + graph structure

**Implementation:**
```python
# In /core/services/learning/lp_intelligence_service.py

async def recommend_next_learning_steps(
    self,
    user_context: UserContext,
    k: int = 10
) -> Result[list[dict[str, Any]]]:
    # Get user's current KUs (in progress, recently completed)
    current_kus = user_context.knowledge_units_in_progress + user_context.knowledge_units_recently_completed[:5]

    if not current_kus:
        return await self._recommend_beginner_kus(user_context)

    # Generate recommendations based on semantic similarity
    recommendations = []
    for ku_uid in current_kus:
        # Find semantically similar KUs
        similar_result = await self.vector_search.learning_aware_search(
            query_text=ku_uid,  # Use KU itself as query
            user_context=user_context,
            index_name="ku_embeddings",
            k=5
        )

        if not similar_result.is_error:
            recommendations.extend(similar_result.value)

    # Deduplicate and score
    seen_uids = set()
    unique_recommendations = []
    for rec in recommendations:
        if rec.uid not in seen_uids and rec.uid not in user_context.knowledge_units_mastered:
            seen_uids.add(rec.uid)

            # Boost score based on prerequisites met
            prerequisite_score = await self._calculate_prerequisite_score(rec.uid, user_context)
            rec.similarity_score *= (1 + prerequisite_score)

            unique_recommendations.append(rec)

    # Sort by adjusted score
    unique_recommendations.sort(key=lambda x: x.similarity_score, reverse=True)

    return Result.ok([r.to_dict() for r in unique_recommendations[:k]])
```

### Priority 2: Cross-Domain Bridge Detection

**Use Case:** Find semantic connections between Activity and Curriculum domains

**Example:** Task "Learn Python decorators" → KU "Python Decorators"

**Implementation:**
```python
async def find_cross_domain_semantic_bridges(
    self,
    source_uid: str,
    source_domain: EntityType,
    target_domain: EntityType,
    k: int = 5
) -> Result[list[dict[str, Any]]]:
    """Find semantically similar entities across domains."""

    # Get source entity content for embedding
    source = await self._get_entity_content(source_uid, source_domain)
    if not source:
        return Errors.not_found(f"Entity {source_uid} not found")

    # Generate embedding if needed
    embedding_result = await self.embeddings_service.generate_embedding(source.content)
    if embedding_result.is_error:
        return embedding_result

    # Search in target domain
    target_index = f"{target_domain.value}_embeddings"
    search_result = await self.vector_search.search_by_vector(
        vector=embedding_result.value,
        index_name=target_index,
        k=k,
        min_similarity=0.75  # Lower threshold for cross-domain
    )

    return search_result
```

### Priority 2: Relationship Explanation Generation

**Use Case:** Explain WHY two KUs are related using LLM

**Implementation:**
```python
async def generate_relationship_explanation(
    self,
    source_uid: str,
    target_uid: str,
    similarity_score: float
) -> Result[str]:
    """Generate natural language explanation for semantic relationship."""

    # Get KU content
    source = await self.backend.get(source_uid)
    target = await self.backend.get(target_uid)

    if source.is_error or target.is_error:
        return Errors.not_found("KU not found")

    # Generate explanation using ai.text.completion()
    prompt = f"""
    Explain the semantic relationship between these two knowledge units:

    KU 1: {source.value.title}
    Content: {source.value.content[:500]}...

    KU 2: {target.value.title}
    Content: {target.value.content[:500]}...

    Similarity Score: {similarity_score:.3f}

    Provide a concise (2-3 sentences) explanation of how these topics relate.
    """

    query = """
    RETURN ai.text.completion($prompt, {
        model: 'gpt-4o-mini',
        temperature: 0.3
    }) AS explanation
    """

    result = await self.backend.driver.execute_query(query, prompt=prompt)
    explanation = result.records[0]["explanation"]

    return Result.ok(explanation)
```

## RAG Workflows

### Basic RAG Pattern

**Retrieve → Generate workflow:**

```python
async def answer_question_with_context(
    self,
    question: str,
    k: int = 5
) -> Result[str]:
    """Basic RAG: retrieve relevant KUs, generate answer."""

    # Step 1: Retrieve relevant knowledge
    search_result = await self.vector_search.search_by_text(
        query_text=question,
        index_name="ku_embeddings",
        k=k,
        min_similarity=0.7
    )

    if search_result.is_error or not search_result.value:
        return Errors.not_found("No relevant knowledge found")

    # Step 2: Build context from retrieved KUs
    context_parts = []
    for result in search_result.value:
        ku = await self.backend.get(result.uid)
        if not ku.is_error:
            context_parts.append(f"**{ku.value.title}**\n{ku.value.content}\n")

    context = "\n---\n".join(context_parts)

    # Step 3: Generate answer with context
    prompt = f"""
    Answer the following question using ONLY the provided knowledge context.
    If the context doesn't contain enough information, say so.

    QUESTION: {question}

    KNOWLEDGE CONTEXT:
    {context}

    ANSWER:
    """

    query = """
    RETURN ai.text.completion($prompt, {
        model: 'gpt-4o-mini',
        temperature: 0.3,
        max_tokens: 500
    }) AS answer
    """

    result = await self.backend.driver.execute_query(query, prompt=prompt)
    answer = result.records[0]["answer"]

    return Result.ok(answer)
```

### Graph-Enhanced RAG

**Expand vector search results with 1-2 hop graph traversal:**

```python
async def graph_enhanced_rag(
    self,
    question: str,
    k: int = 5,
    expand_hops: int = 1
) -> Result[str]:
    """RAG with graph context expansion."""

    # Step 1: Vector search for initial KUs
    search_result = await self.vector_search.search_by_text(
        query_text=question,
        index_name="ku_embeddings",
        k=k
    )

    if search_result.is_error:
        return search_result

    initial_uids = [r.uid for r in search_result.value]

    # Step 2: Expand with graph relationships
    expanded_context = await self._expand_graph_context(initial_uids, expand_hops)

    # Step 3: Generate answer with expanded context
    prompt = f"""
    Answer the question using the knowledge graph context below.

    QUESTION: {question}

    INITIAL MATCHES (most relevant):
    {expanded_context['initial']}

    RELATED KNOWLEDGE (via graph relationships):
    {expanded_context['related']}

    ANSWER:
    """

    # Use ai.text.completion() for generation
    query = """
    RETURN ai.text.completion($prompt, {
        model: 'gpt-4o-mini',
        temperature: 0.3
    }) AS answer
    """

    result = await self.backend.driver.execute_query(query, prompt=prompt)
    return Result.ok(result.records[0]["answer"])

async def _expand_graph_context(
    self,
    initial_uids: list[str],
    hops: int
) -> dict[str, str]:
    """Expand initial KUs with graph relationships."""
    query = """
    MATCH (ku:KnowledgeUnit)
    WHERE ku.uid IN $uids
    WITH collect(ku) AS initial_kus

    // Initial content
    UNWIND initial_kus AS ku
    WITH collect(ku.title + ': ' + ku.content) AS initial_content

    // Expand with relationships (1-2 hops)
    MATCH (ku:KnowledgeUnit)-[:PREREQUISITE_FOR|PART_OF|SEMANTICALLY_RELATED*1..$hops]-(related:KnowledgeUnit)
    WHERE ku.uid IN $uids AND related.uid NOT IN $uids
    WITH initial_content, collect(DISTINCT related.title + ': ' + related.content) AS related_content

    RETURN {
        initial: initial_content,
        related: related_content
    } AS context
    """

    result = await self.backend.driver.execute_query(query, uids=initial_uids, hops=hops)
    context = result.records[0]["context"]

    return {
        "initial": "\n\n".join(context["initial"]),
        "related": "\n\n".join(context["related"])
    }
```

**Trade-offs:**
- **Pros:** More complete context, discovers non-obvious connections
- **Cons:** +100ms latency, more tokens (higher cost), potential noise

**When to use:** Complex questions requiring multi-faceted understanding

### Multi-Hop Reasoning RAG

**Chain multiple retrieval-generation steps:**

```python
async def multi_hop_rag(
    self,
    question: str,
    max_hops: int = 3
) -> Result[str]:
    """Multi-step reasoning with intermediate retrieval."""

    current_question = question
    reasoning_chain = []

    for hop in range(max_hops):
        # Retrieve context for current question
        search_result = await self.vector_search.search_by_text(
            query_text=current_question,
            index_name="ku_embeddings",
            k=5
        )

        if search_result.is_error:
            break

        # Build context
        context = self._build_context_from_results(search_result.value)

        # Generate intermediate answer or next question
        prompt = f"""
        Question: {current_question}

        Context:
        {context}

        If you can answer the question, provide the FINAL ANSWER.
        If you need more information, generate a FOLLOW-UP QUESTION to retrieve additional context.

        Format:
        FINAL ANSWER: [answer]
        OR
        FOLLOW-UP QUESTION: [question]
        """

        response = await self._call_completion(prompt)
        reasoning_chain.append(response)

        if response.startswith("FINAL ANSWER:"):
            return Result.ok(response.replace("FINAL ANSWER:", "").strip())

        # Extract follow-up question for next hop
        current_question = response.replace("FOLLOW-UP QUESTION:", "").strip()

    # Max hops reached without final answer
    return Errors.business(
        "Could not answer question within reasoning depth",
        details={"reasoning_chain": reasoning_chain}
    )
```

### Conversational RAG with Memory

**Multi-turn conversation using `ai.text.chat()`:**

```python
async def conversational_rag(
    self,
    user_message: str,
    chat_id: str,
    user_context: UserContext
) -> Result[str]:
    """Multi-turn RAG with conversation memory."""

    # Step 1: Retrieve relevant knowledge for current message
    search_result = await self.vector_search.learning_aware_search(
        query_text=user_message,
        user_context=user_context,
        index_name="ku_embeddings",
        k=5
    )

    if search_result.is_error:
        return search_result

    # Step 2: Build context from retrieved knowledge
    knowledge_context = self._build_context_from_results(search_result.value)

    # Step 3: Use ai.text.chat() for multi-turn conversation
    # Chat history is managed by chatId in Neo4j GenAI plugin
    query = """
    RETURN ai.text.chat([
        {
            role: 'system',
            content: $system_prompt
        },
        {
            role: 'user',
            content: $user_message
        }
    ], {
        model: 'gpt-4o-mini',
        chatId: $chat_id,
        temperature: 0.7
    }) AS response
    """

    system_prompt = f"""
    You are a learning assistant helping a user understand knowledge from their personal knowledge graph.

    KNOWLEDGE CONTEXT (retrieved via semantic search):
    {knowledge_context}

    Answer the user's question using this context and any previous conversation history.
    """

    result = await self.backend.driver.execute_query(
        query,
        system_prompt=system_prompt,
        user_message=user_message,
        chat_id=chat_id
    )

    response = result.records[0]["response"]
    return Result.ok(response)
```

**Chat ID management:**
- Use `f"user:{user_uid}:session:{timestamp}"` for chat IDs
- Neo4j GenAI plugin stores conversation history in memory
- Clear chat: delete chat ID from plugin state (implementation-specific)

## Cost Optimization & Best Practices

### Batching Strategy

**Optimal batch size: 50 items** (balance between API limits and throughput)

```python
OPTIMAL_BATCH_SIZE = 50

async def batch_embed_with_optimal_size(
    self,
    texts: list[str]
) -> Result[list[list[float]]]:
    """Process texts in optimal batches."""
    all_embeddings = []

    for i in range(0, len(texts), OPTIMAL_BATCH_SIZE):
        batch = texts[i:i+OPTIMAL_BATCH_SIZE]

        batch_result = await self.embeddings_service.generate_embeddings_batch(batch)
        if batch_result.is_error:
            return batch_result

        all_embeddings.extend(batch_result.value)

    return Result.ok(all_embeddings)
```

**Why 50?**
- OpenAI API limit: 2048 inputs per request
- Network overhead: Larger batches = fewer HTTP requests
- Error isolation: Smaller batches = easier to debug failures
- Benchmarking shows 50 is optimal for SKUEL's use cases

### Caching with Version Tracking

**Avoid re-embedding unchanged content:**

```python
async def ensure_embedding_with_cache(
    self,
    uid: str,
    text: str,
    current_version: str = "v2"
) -> Result[list[float]]:
    """Only generate embedding if missing or version mismatch."""

    # Check existing embedding
    query = """
    MATCH (n {uid: $uid})
    RETURN n.embedding AS embedding, n.embedding_version AS version
    """

    result = await self.backend.driver.execute_query(query, uid=uid)
    record = result.records[0] if result.records else None

    # Return cached if version matches
    if record and record["embedding"] and record["version"] == current_version:
        return Result.ok(record["embedding"])

    # Generate new embedding
    embedding_result = await self.embeddings_service.generate_embedding(text)
    if embedding_result.is_error:
        return embedding_result

    # Store with version
    await self._store_embedding(uid, embedding_result.value, current_version)

    return embedding_result
```

**Version strategy:**
- `v1` = text-embedding-ada-002 (legacy)
- `v2` = text-embedding-3-small (current)
- `v3` = Future model upgrades

**When to increment version:**
- Model change (ada-002 → text-embedding-3-small)
- Dimension change (1536 → 3072)
- Preprocessing change (truncation, normalization)

### Cost Monitoring

**OpenAI text-embedding-3-small pricing:** ~$0.02 per 1M tokens

**Estimate tokens:**
```python
def estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 characters."""
    return len(text) // 4

def estimate_embedding_cost(texts: list[str]) -> float:
    """Estimate cost in USD."""
    total_tokens = sum(estimate_tokens(t) for t in texts)
    cost_per_million = 0.02
    return (total_tokens / 1_000_000) * cost_per_million
```

**Example costs:**
- 5,000 KUs × 500 tokens each = 2.5M tokens = **$0.05**
- 100,000 KUs × 500 tokens = 50M tokens = **$1.00**

**Cost tracking in graph:**
```cypher
MATCH (ku:KnowledgeUnit)
WHERE ku.embedding IS NOT NULL
WITH sum(ku.embedding_cost_tokens) AS total_tokens
RETURN total_tokens, (total_tokens / 1000000.0) * 0.02 AS estimated_cost_usd
```

### Provider Selection Guide

**Embedding model comparison:**

| Model | Dimensions | Cost/1M tokens | Quality | Use Case |
|-------|-----------|----------------|---------|----------|
| text-embedding-3-small | 1536 | $0.02 | Good | Production (SKUEL default) |
| text-embedding-3-large | 3072 | $0.13 | Better | High-precision needs |
| text-embedding-ada-002 | 1536 | $0.10 | Baseline | Legacy (deprecated) |

**SKUEL uses text-embedding-3-small:**
- Best cost/quality ratio
- 1536 dimensions (manageable index size)
- Cosine similarity works well

**When to upgrade to 3-large:**
- Domain requires high precision (legal, medical)
- Willing to pay 6.5x more
- Index size not a concern (3072-dim vectors)

### Vector Index Tuning

**HNSW parameters (Neo4j defaults are optimal for most cases):**

| Parameter | Default | High Recall | High Speed |
|-----------|---------|-------------|------------|
| `m` | 16 | 32 | 8 |
| `efConstruction` | 200 | 400 | 100 |
| `efSearch` | 10 | 40 | 5 |

**When to tune:**
- Benchmark shows <90% recall → Increase `m` and `efConstruction`
- Queries >100ms → Decrease `efSearch`
- Index build >1 hour → Decrease `efConstruction`

**SKUEL uses defaults** - only tune if benchmarks show issues.

**Index monitoring:**
```cypher
SHOW VECTOR INDEXES YIELD name, state, populationPercent, size
```

### Common Anti-Patterns

❌ **Re-embedding on every query:**
```python
# BAD - generates new embedding every time
embedding = await embeddings_service.generate_embedding(query)
```

✅ **Good - cache query embeddings:**
```python
# Use simple in-memory cache for repeated queries
@lru_cache(maxsize=1000)
async def get_cached_query_embedding(query: str) -> list[float]:
    return await embeddings_service.generate_embedding(query)
```

❌ **No error handling:**
```python
# BAD - crashes on API failure
embedding = await embeddings_service.generate_embedding(text).value
```

✅ **Good - graceful degradation:**
```python
embedding_result = await embeddings_service.generate_embedding(text)
if embedding_result.is_error:
    return await fallback_keyword_search(query)
```

❌ **Synchronous batch processing:**
```python
# BAD - serial processing
for text in texts:
    await generate_embedding(text)  # One at a time!
```

✅ **Good - batch API call:**
```python
# Process all at once
await embeddings_service.generate_embeddings_batch(texts)
```

❌ **Ignoring version tracking:**
```cypher
# BAD - no way to know when to re-embed
SET ku.embedding = genai.vector.encode(ku.content, 'OpenAI', {token: $key, model: 'text-embedding-3-small'})
```

✅ **Good - version metadata:**
```cypher
SET ku.embedding = genai.vector.encode(ku.content, 'OpenAI', {token: $key, model: 'text-embedding-3-small'}),
    ku.embedding_version = 'v2',
    ku.embedding_updated_at = datetime()
```

❌ **Low similarity threshold:**
```python
# BAD - returns many irrelevant results
min_similarity=0.5  # Too low!
```

✅ **Good - high threshold for quality:**
```python
min_similarity=0.7  # Good balance
# Or 0.85 for semantic relationships
```

---

## Troubleshooting

### Common Issues and Solutions

**Issue: "Unknown function 'ai.text.embed'"**
- **Cause:** Using outdated function names from older documentation
- **Solution:** Use `genai.vector.encode()` instead of `ai.text.embed()`, and `genai.vector.encodeBatch()` instead of `ai.text.embedBatch()`
- **Context:** Neo4j 2025.12.1+ uses the `genai.*` namespace

**Issue: "'token' is expected to have been set"**
- **Cause:** Missing OpenAI API key in function call
- **Solution:** Pass API key as `token` parameter in configuration object:
```python
query = """
RETURN genai.vector.encode(
    $text,
    'OpenAI',
    {
        token: $openai_api_key,  # REQUIRED for local Neo4j
        model: $model,
        dimensions: $dimensions
    }
) AS embedding
"""
```

**Issue: "'list' object has no attribute 'get'"**
- **Cause:** Incorrect result unpacking from `execute_query()`
- **Solution:** Unpack the tuple returned by `execute_query()`:
```python
# Wrong:
result = await driver.execute_query(query, params)
embedding = result[0]["embedding"]  # ❌ Fails

# Correct:
records, summary, keys = await driver.execute_query(query, params)
embedding = records[0]["embedding"]  # ✅ Works
```

**Issue: GenAI plugin not found**
- **Cause:** Plugin not enabled in Docker container
- **Solution:** Add to `docker-compose.yml`:
```yaml
environment:
  NEO4J_PLUGINS: '["genai"]'  # Auto-loads plugin
  NEO4J_dbms_security_procedures_unrestricted: "genai.*"
  NEO4J_dbms_security_procedures_allowlist: "genai.*"
```

**Issue: Neo4j authentication failure after password change**
- **Cause:** Old data directory still exists (bind-mount volumes persist)
- **Solution:** Delete Neo4j data directory and restart:
```bash
cd /path/to/infrastructure
rm -rf neo4j/data/*
docker compose up -d
```

**Issue: "OPENAI_API_KEY not set" warning in Python**
- **Cause:** .env file not loaded before importing services
- **Solution:** Add at top of script:
```python
from dotenv import load_dotenv
load_dotenv()  # BEFORE importing services
```

**Issue: Embeddings work in Neo4j Browser but fail in Python**
- **Cause:** Parameter name mismatch or missing configuration
- **Solution:** Verify parameter names match between Python and Cypher:
```python
params = {
    "text": text,
    "openai_api_key": self.openai_api_key,  # Match $openai_api_key in Cypher
    "model": self.model,
    "dimensions": self.dimension,
}
```

### Verification Commands

**Check GenAI plugin is loaded:**
```cypher
CALL dbms.procedures() YIELD name
WHERE name STARTS WITH 'genai'
RETURN name
ORDER BY name
```

**Test embedding generation:**
```cypher
RETURN genai.vector.encode(
    'test text',
    'OpenAI',
    {
        token: 'your-openai-api-key-here',
        model: 'text-embedding-3-small',
        dimensions: 1536
    }
) AS embedding
```

**Check vector indexes:**
```cypher
SHOW VECTOR INDEXES
```

---

## See Also

**Related Skills:**
- `neo4j-cypher-patterns` - Cypher basics (prerequisite)
- `python` - Async patterns, Result[T] (prerequisite)
- `skuel-search-architecture` - SearchRouter integration
- `base-analytics-service` - Intelligence services
- `result-pattern` - Error handling

**SKUEL Documentation:**
- `/docs/development/GENAI_SETUP.md` - Setup guide
- `/docs/architecture/SEARCH_ARCHITECTURE.md` - Search overview
- `/docs/architecture/SEARCH_ARCHITECTURE.md` - Semantic Search section (merged)
- `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md` - Service patterns

**Source Files:**
- `/core/services/neo4j_genai_embeddings_service.py` - Embeddings service
- `/core/services/neo4j_vector_search_service.py` - Vector search
- `/core/services/ingestion/unified_ingestion_service.py` - Ingestion
- `/core/config/unified_config.py` - VectorSearchConfig
- `/scripts/verify_genai_setup.py` - Verification script

---

## Deep Dive Resources

**Architecture:**
- [Query Architecture](/docs/patterns/query_architecture.md) - Graph database architecture
- [SEARCH_ARCHITECTURE.md](/docs/architecture/SEARCH_ARCHITECTURE.md) - Unified search with vector search
- [ADR-034](/docs/decisions/ADR-034-semantic-search-phase1-enhancement.md) - Semantic search enhancement

**Development Setup:**
- [GENAI_SETUP.md](/docs/development/GENAI_SETUP.md) - Local Docker Neo4j with GenAI plugin

**Migration:**
- [AURADB_MIGRATION_GUIDE.md](/docs/deployment/AURADB_MIGRATION_GUIDE.md) - Production AuraDB migration

**Patterns:**
- [query_architecture.md](/docs/patterns/query_architecture.md) - Query patterns

---

**External Resources:**
- [Neo4j GenAI Plugin Documentation](https://neo4j.com/docs/genai/plugin/current/)
- [OpenAI Embeddings Guide](https://platform.openai.com/docs/guides/embeddings)
- [Vector Indexes in Neo4j](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Reciprocal Rank Fusion Paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)

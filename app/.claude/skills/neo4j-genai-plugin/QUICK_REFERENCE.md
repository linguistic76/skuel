# Neo4j GenAI Plugin - Quick Reference

Fast lookup guide for common operations, methods, and configuration.

## Common Operations

| Operation | Code | Notes |
|-----------|------|-------|
| **Single embedding** | `ai.text.embed(text, 'text-embedding-3-small')` | Returns List[Float] (1536-dim) |
| **Batch embeddings** | `ai.text.embedBatch(texts, 'text-embedding-3-small')` | Optimal: 50 items per batch |
| **Store with version** | `SET ku.embedding = ai.text.embed(...), ku.embedding_version = 'v2'` | Always track version |
| **Vector search** | `db.index.vector.queryNodes('ku_embeddings', 10, $vector)` | Returns nodes + similarity scores |
| **Hybrid search (RRF)** | See PATTERNS.md, Pattern 2 | 70% vector, 30% fulltext (default) |
| **Semantic relationships** | `WHERE score >= 0.85` then `MERGE (a)-[:SEMANTICALLY_RELATED]-(b)` | High threshold for quality |
| **Text generation** | `ai.text.completion($prompt, {model: 'gpt-4o-mini'})` | Simple prompts only |
| **Multi-turn chat** | `ai.text.chat($messages, {chatId: 'session1'})` | Conversation memory via chatId |
| **Learning-aware search** | `vector_search.learning_aware_search(query, user_context)` | Boosts based on mastery |
| **Conditional embedding** | `WHERE ku.embedding IS NULL OR ku.embedding_version <> 'v2'` | Avoid re-embedding |
| **Graph-enhanced RAG** | Vector search → 1-2 hop expansion → Generate | +100ms, more context |
| **Check embedding exists** | `RETURN EXISTS(ku.embedding) AS has_embedding` | Boolean check |
| **Count embeddings** | `MATCH (ku:KnowledgeUnit) WHERE ku.embedding IS NOT NULL RETURN count(ku)` | Stats |
| **Estimate cost** | `len(text) // 4 * 0.02 / 1_000_000` | ~$0.02 per 1M tokens |
| **Verify setup** | `poetry run python scripts/verify_genai_setup.py` | Check plugin availability |

## Python Methods Reference

### Neo4jGenAIEmbeddingsService

| Method | Purpose | Returns |
|--------|---------|---------|
| `generate_embedding(text)` | Single text → embedding | `Result[list[float]]` |
| `generate_embeddings_batch(texts)` | Batch texts → embeddings | `Result[list[list[float]]]` |
| `store_embedding(uid, embedding, version)` | Store with metadata | `Result[None]` |
| `ensure_embedding(uid, text, version)` | Conditional generation (cache) | `Result[list[float]]` |
| `get_embedding(uid)` | Retrieve stored embedding | `Result[list[float]]` |
| `has_embedding(uid)` | Check if exists | `Result[bool]` |
| `get_embedding_stats()` | Count, version distribution | `Result[dict[str, Any]]` |

**Example:**
```python
from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService

embeddings_service = Neo4jGenAIEmbeddingsService(driver, config)

# Single embedding
result = await embeddings_service.generate_embedding("Python is a programming language")
if not result.is_error:
    embedding = result.value  # list[float], 1536 dimensions

# Batch embeddings (50 optimal)
batch_result = await embeddings_service.generate_embeddings_batch(texts[:50])
if not batch_result.is_error:
    embeddings = batch_result.value  # list[list[float]]

# Ensure embedding (cache-aware)
ensure_result = await embeddings_service.ensure_embedding(
    uid="ku.python-basics",
    text=ku.content,
    current_version="v2"
)
```

### Neo4jVectorSearchService

| Method | Purpose | Returns |
|--------|---------|---------|
| `search_by_text(query, index, k)` | Text query → vector search | `Result[list[VectorSearchResult]]` |
| `search_by_vector(vector, index, k)` | Direct vector search | `Result[list[VectorSearchResult]]` |
| `hybrid_search(query, vector_index, fulltext_index)` | Vector + keyword (RRF) | `Result[list[VectorSearchResult]]` |
| `learning_aware_search(query, user_context)` | Personalized search | `Result[list[VectorSearchResult]]` |
| `find_similar(uid, index, k)` | Find similar to entity | `Result[list[VectorSearchResult]]` |
| `batch_search(queries, index, k)` | Multiple queries | `Result[list[list[VectorSearchResult]]]` |
| `get_search_stats()` | Performance metrics | `Result[dict[str, Any]]` |
| `search_with_filters(query, filters, index)` | Filtered vector search | `Result[list[VectorSearchResult]]` |

**Example:**
```python
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService

vector_search = Neo4jVectorSearchService(driver, embeddings_service, config)

# Text query → vector search
search_result = await vector_search.search_by_text(
    query_text="What is Python?",
    index_name="ku_embeddings",
    k=10,
    min_similarity=0.7
)

# Hybrid search (70% vector, 30% fulltext)
hybrid_result = await vector_search.hybrid_search(
    query_text="Python programming",
    vector_index="ku_embeddings",
    fulltext_index="ku_fulltext",
    k=10,
    vector_weight=0.7,
    fulltext_weight=0.3
)

# Learning-aware search (personalized)
personalized = await vector_search.learning_aware_search(
    query_text="Advanced Python",
    user_context=user_context,  # Contains mastery levels
    index_name="ku_embeddings",
    k=20
)

# Process results
if not search_result.is_error:
    for result in search_result.value:
        print(f"{result.uid}: {result.title} (score: {result.similarity_score:.3f})")
```

### VectorSearchResult Model

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Entity UID |
| `title` | `str` | Entity title |
| `similarity_score` | `float` | 0.0-1.0 cosine similarity |
| `content` | `str | None` | Entity content (optional) |
| `metadata` | `dict[str, Any]` | Additional properties |

## Configuration Reference

### Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GENAI_ENABLED` | `bool` | `false` | Enable GenAI plugin features |
| `GENAI_EMBEDDING_MODEL` | `str` | `text-embedding-3-small` | OpenAI embedding model |
| `GENAI_EMBEDDING_DIMENSIONS` | `int` | `1536` | Embedding dimensions |
| `GENAI_BATCH_SIZE` | `int` | `50` | Optimal batch size |
| `GENAI_COMPLETION_MODEL` | `str` | `gpt-4o-mini` | Text generation model |
| `GENAI_CHAT_MODEL` | `str` | `gpt-4o-mini` | Chat model |
| `INTELLIGENCE_TIER` | `str` | `full` | `core` (no AI) or `full` (AI enabled) — ADR-043 |
| `OPENAI_API_KEY` | `str` | — | OpenAI API key (required when `INTELLIGENCE_TIER=full`) |
| `VECTOR_SEARCH_DEFAULT_K` | `int` | `10` | Default result count |
| `VECTOR_SEARCH_MIN_SIMILARITY` | `float` | `0.7` | Minimum similarity threshold |
| `VECTOR_SEARCH_HYBRID_WEIGHT` | `float` | `0.7` | Vector weight in hybrid (0-1) |

### Vector Indexes (4 total)

| Index Name | Label | Property | Dimensions | Use Case |
|-----------|-------|----------|------------|----------|
| `ku_embeddings` | `KnowledgeUnit` | `embedding` | 1536 | KU semantic search |
| `ls_embeddings` | `LearningSequence` | `embedding` | 1536 | LS semantic search |
| `lp_embeddings` | `LearningPath` | `embedding` | 1536 | LP semantic search |
| `user_embeddings` | `User` | `embedding` | 1536 | User interest/profile |

### GenAIConfig Class

**Location:** `/core/config/unified_config.py`

```python
from core.config.unified_config import settings

config = settings.genai

# Access config values
enabled: bool = config.enabled
model: str = config.embedding_model
dimensions: int = config.embedding_dimensions
batch_size: int = config.batch_size
```

### VectorSearchConfig Class

**Location:** `/core/config/unified_config.py`

```python
from core.config.unified_config import settings

config = settings.vector_search

# Access config values
default_k: int = config.default_k
min_similarity: float = config.min_similarity
hybrid_weight: float = config.hybrid_weight
```

## Common Pitfalls

| Pitfall | Problem | Solution |
|---------|---------|----------|
| **No version tracking** | Can't detect model changes | Always set `embedding_version = 'v2'` |
| **Small batch size** | Too many API calls | Use 50 items per batch (optimal) |
| **Low similarity threshold** | Irrelevant results | Use 0.7 for search, 0.85 for relationships |
| **Re-embedding unchanged content** | Wasted cost | Check version before generating |
| **No graceful degradation** | App breaks without GenAI | Always fallback to keyword search |
| **Synchronous batch processing** | Slow ingestion | Use `ai.text.embedBatch()` not loops |
| **Ignoring embedding failures** | Silent data loss | Check `result.is_error` and log |
| **Hardcoded model names** | Config drift | Use `settings.genai.embedding_model` |
| **Missing error handling** | Crashes on API failure | Wrap in Result[T] pattern |
| **No cost tracking** | Budget surprises | Store `embedding_cost_tokens` |
| **Vector-only search** | Misses exact keywords | Use hybrid search (70/30 default) |
| **Unbounded vector search** | Performance issues | Always use `LIMIT` and `min_similarity` |
| **No index monitoring** | Stale indexes | Check `SHOW VECTOR INDEXES` |
| **Assuming embeddings exist** | Crashes on NULL | `WHERE ku.embedding IS NOT NULL` |
| **Wrong similarity function** | Poor results | Use cosine (default) not euclidean |

## Cypher Quick Patterns

### Generate and Store (with version)
```cypher
MATCH (ku:KnowledgeUnit {uid: $uid})
WHERE ku.embedding IS NULL OR ku.embedding_version <> 'v2'
SET ku.embedding = ai.text.embed(ku.content, 'text-embedding-3-small'),
    ku.embedding_version = 'v2',
    ku.embedding_updated_at = datetime()
RETURN ku.uid
```

### Batch Embeddings (50 optimal)
```cypher
MATCH (ku:KnowledgeUnit)
WHERE ku.embedding IS NULL
WITH collect(ku) AS kus LIMIT 50
UNWIND kus AS ku
WITH ku, ai.text.embedBatch([k.content | k IN kus], 'text-embedding-3-small') AS embeddings
SET ku.embedding = embeddings[apoc.coll.indexOf(kus, ku)],
    ku.embedding_version = 'v2'
RETURN count(ku)
```

### Vector Search
```cypher
CALL db.index.vector.queryNodes('ku_embeddings', 10, $query_vector)
YIELD node, score
WHERE score >= 0.7
RETURN node.uid, node.title, score
ORDER BY score DESC
```

### Semantic Relationships
```cypher
MATCH (ku:KnowledgeUnit {uid: $uid})
WHERE ku.embedding IS NOT NULL
CALL db.index.vector.queryNodes('ku_embeddings', 20, ku.embedding)
YIELD node AS similar, score
WHERE similar.uid <> ku.uid AND score >= 0.85
MERGE (ku)-[r:SEMANTICALLY_RELATED]-(similar)
SET r.similarity_score = score, r.inferred = true
RETURN count(r)
```

### Graph-Enhanced Context
```cypher
CALL db.index.vector.queryNodes('ku_embeddings', $k, $vector)
YIELD node AS ku, score
MATCH (ku)-[:PART_OF]->(ls:LearningSequence)
MATCH (ls)-[:PART_OF]->(lp:LearningPath)
RETURN ku.uid, ku.title, score, ls.title AS sequence, lp.title AS path
ORDER BY score DESC
```

### Text Completion
```cypher
RETURN ai.text.completion($prompt, {
    model: 'gpt-4o-mini',
    temperature: 0.3,
    max_tokens: 500
}) AS response
```

### Multi-Turn Chat
```cypher
RETURN ai.text.chat([
    {role: 'system', content: $system_prompt},
    {role: 'user', content: $user_message}
], {
    model: 'gpt-4o-mini',
    chatId: $chat_id,
    temperature: 0.7
}) AS response
```

## Performance Benchmarks

| Operation | Latency | Cost | Notes |
|-----------|---------|------|-------|
| Single embedding | 50-100ms | ~$0.000002 | 500 tokens |
| Batch embeddings (50) | 200-500ms | ~$0.0001 | 25,000 tokens total |
| Vector search (k=10) | 10-30ms | Free | HNSW index |
| Hybrid search (k=10) | 30-60ms | Free | RRF fusion |
| Graph-enhanced RAG | 100-200ms | Depends on expansion | +1-2 hop traversal |
| Text completion | 500-2000ms | ~$0.0001 | 500 tokens generated |

**Optimization tips:**
- Batch embeddings in groups of 50
- Cache query embeddings for repeated searches
- Use min_similarity threshold to reduce result processing
- Pre-compute semantic relationships during ingestion
- Monitor index populationPercent (should be 100%)

## Integration Points (Priority Order)

### Priority 1 (High Value, Immediate)
1. **Auto-embedding during ingestion** → `UnifiedIngestionService.ingest_single_ku()`
2. **Semantic search enhancement** → `SearchRouter.faceted_search()` with hybrid default
3. **Semantic relationship inference** → Post-ingestion graph enrichment
4. **Learning path optimization** → `LpIntelligenceService.recommend_next_learning_steps()`

### Priority 2 (Medium Value, Near-term)
5. **Cross-domain bridge detection** → Activity ↔ Curriculum semantic links
6. **Relationship explanations** → Use `ai.text.completion()` for "why related?"
7. **Graph-enhanced RAG** → Askesis integration
8. **Conversational RAG** → `ai.text.chat()` for multi-turn queries

### Priority 3 (Lower Priority, Future)
9. **neo4j-graphrag-python migration** → Replace custom services with official SDK
10. **Embedding model experimentation** → A/B test different models
11. **Multi-modal embeddings** → Image/audio content support

---

## Cost Calculator

```python
def estimate_embedding_cost(num_texts: int, avg_tokens: int = 500) -> dict[str, float]:
    """Estimate embedding cost in USD."""
    total_tokens = num_texts * avg_tokens
    cost_per_million = 0.02  # text-embedding-3-small

    return {
        "total_tokens": total_tokens,
        "cost_usd": (total_tokens / 1_000_000) * cost_per_million,
        "cost_per_item": (total_tokens / 1_000_000) * cost_per_million / num_texts
    }

# Examples:
# 5,000 KUs × 500 tokens = $0.05
# 100,000 KUs × 500 tokens = $1.00
```

## Verification Checklist

✅ **Setup verified:**
```bash
poetry run python scripts/verify_genai_setup.py
```

✅ **Indexes exist:**
```cypher
SHOW VECTOR INDEXES YIELD name, state, populationPercent
```

✅ **Embeddings generating:**
```cypher
MATCH (ku:KnowledgeUnit {uid: 'ku.test'})
SET ku.embedding = ai.text.embed('test content', 'text-embedding-3-small')
RETURN size(ku.embedding)  // Should return 1536
```

✅ **Vector search working:**
```cypher
CALL db.index.vector.queryNodes('ku_embeddings', 5, $test_vector)
YIELD node, score
RETURN node.uid, score
```

✅ **Hybrid search configured:**
```python
# In SearchRouter
hybrid_weight = settings.vector_search.hybrid_weight  # Should be 0.7
```

✅ **Graceful degradation:**
```python
# In service
if not settings.genai.enabled:
    return await fallback_keyword_search(query)
```

---

**See SKILL.md for detailed patterns and PATTERNS.md for implementation examples.**

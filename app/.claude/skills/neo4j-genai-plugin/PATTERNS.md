# Neo4j GenAI Plugin - Implementation Patterns

Production-ready patterns for embeddings, vector search, and RAG workflows.

## Pattern 1: Embedding Generation with Version Tracking

### Problem
Avoid unnecessary re-generation when embedding model changes or content updates.

### Solution
Store version metadata with embeddings, check before regenerating.

### Full Implementation

```python
from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
from core.result import Result
from core.errors import Errors
from datetime import datetime

class EmbeddingManager:
    """Manages embeddings with version tracking and cost optimization."""

    CURRENT_VERSION = "v2"  # text-embedding-3-small
    MODEL = "text-embedding-3-small"

    def __init__(
        self,
        embeddings_service: Neo4jGenAIEmbeddingsService,
        backend: Any
    ):
        self.embeddings_service = embeddings_service
        self.backend = backend

    async def ensure_embedding(
        self,
        uid: str,
        text: str,
        force: bool = False
    ) -> Result[list[float]]:
        """
        Ensure entity has current embedding.

        Args:
            uid: Entity UID
            text: Text to embed
            force: Force regeneration even if version matches

        Returns:
            Result with embedding vector or error
        """
        # Step 1: Check existing embedding
        existing = await self._get_existing_embedding(uid)

        # Step 2: Return cached if version matches
        if not force and existing and existing["version"] == self.CURRENT_VERSION:
            logger.debug(f"Using cached embedding for {uid}")
            return Result.ok(existing["embedding"])

        # Step 3: Generate new embedding
        logger.info(f"Generating new embedding for {uid} (version: {self.CURRENT_VERSION})")
        embedding_result = await self.embeddings_service.generate_embedding(text)

        if embedding_result.is_error:
            return Errors.integration(
                f"Failed to generate embedding for {uid}",
                details={"error": str(embedding_result.error)}
            )

        embedding = embedding_result.value

        # Step 4: Store with metadata
        store_result = await self._store_embedding_with_metadata(
            uid=uid,
            embedding=embedding,
            text_length=len(text)
        )

        if store_result.is_error:
            # Log warning but return embedding (storage failure is non-critical)
            logger.warning(f"Failed to store embedding metadata for {uid}: {store_result.error}")

        return Result.ok(embedding)

    async def _get_existing_embedding(self, uid: str) -> dict[str, Any] | None:
        """Retrieve existing embedding and metadata."""
        query = """
        MATCH (n {uid: $uid})
        RETURN n.embedding AS embedding,
               n.embedding_version AS version,
               n.embedding_updated_at AS updated_at
        """

        result = await self.backend.driver.execute_query(query, uid=uid)

        if not result.records:
            return None

        record = result.records[0]

        if not record["embedding"]:
            return None

        return {
            "embedding": record["embedding"],
            "version": record["version"],
            "updated_at": record["updated_at"]
        }

    async def _store_embedding_with_metadata(
        self,
        uid: str,
        embedding: list[float],
        text_length: int
    ) -> Result[None]:
        """Store embedding with full metadata for tracking."""
        query = """
        MATCH (n {uid: $uid})
        SET n.embedding = $embedding,
            n.embedding_version = $version,
            n.embedding_model = $model,
            n.embedding_dimensions = $dimensions,
            n.embedding_updated_at = datetime(),
            n.embedding_cost_tokens = $cost_tokens
        RETURN n.uid
        """

        try:
            await self.backend.driver.execute_query(
                query,
                uid=uid,
                embedding=embedding,
                version=self.CURRENT_VERSION,
                model=self.MODEL,
                dimensions=len(embedding),
                cost_tokens=text_length // 4  # Rough estimate
            )
            return Result.ok(None)
        except Exception as e:
            return Errors.database(f"Failed to store embedding: {str(e)}")
```

### Trade-offs

**Pros:**
- Avoids unnecessary API calls (cost savings)
- Enables model migrations (v1 → v2 detection)
- Cost tracking (sum of cost_tokens)
- Debugging (when was this generated?)

**Cons:**
- Extra metadata storage (~50 bytes per entity)
- Slightly more complex update logic

### When to Use

- ✅ Production systems with cost concerns
- ✅ Systems that may change embedding models
- ✅ When debugging embedding quality
- ❌ One-off scripts (version tracking unnecessary)

---

## Pattern 2: Hybrid Search with Reciprocal Rank Fusion

### Problem
Vector search alone misses exact keyword matches, fulltext search alone misses semantic similarity.

### Solution
Combine both using Reciprocal Rank Fusion (RRF) with configurable weights.

### Algorithm Explanation

**Reciprocal Rank Fusion (RRF):**
```
RRF Score = Σ (1 / (k + rank))

Where:
- k = 60 (constant, from original paper)
- rank = position in result list (1-indexed)
```

**Example:**
```
Vector results:    Fulltext results:
1. Doc A (0.95)    1. Doc B (0.88)
2. Doc B (0.90)    2. Doc C (0.75)
3. Doc D (0.85)    3. Doc A (0.70)

RRF Scores:
Doc A: 1/(60+1) + 1/(60+3) = 0.0164 + 0.0159 = 0.0323
Doc B: 1/(60+2) + 1/(60+1) = 0.0161 + 0.0164 = 0.0325 ✓ Winner
Doc C: 0 + 1/(60+2) = 0.0161
Doc D: 1/(60+3) + 0 = 0.0159
```

### Full Implementation

```python
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.models.search.search_models import VectorSearchResult
from core.result import Result
from core.utils.logging import get_logger

logger = get_logger("skuel.search.hybrid")

class HybridSearchService:
    """Hybrid search combining vector and fulltext with RRF."""

    RRF_K = 60  # Constant from RRF paper

    def __init__(
        self,
        vector_search: Neo4jVectorSearchService,
        config: VectorSearchConfig
    ):
        self.vector_search = vector_search
        self.config = config

    async def hybrid_search(
        self,
        query_text: str,
        vector_index: str,
        fulltext_index: str,
        k: int = 10,
        vector_weight: float = 0.7,
        fulltext_weight: float = 0.3,
        min_similarity: float = 0.6
    ) -> Result[list[VectorSearchResult]]:
        """
        Hybrid search with RRF fusion.

        Args:
            query_text: Search query
            vector_index: Vector index name (e.g., 'ku_embeddings')
            fulltext_index: Fulltext index name (e.g., 'ku_fulltext')
            k: Number of results per search (final results will be top-k after fusion)
            vector_weight: Weight for vector scores (0-1)
            fulltext_weight: Weight for fulltext scores (0-1)
            min_similarity: Minimum similarity threshold for vector results

        Returns:
            Fused and ranked results
        """
        # Step 1: Vector search
        vector_results = await self.vector_search.search_by_text(
            query_text=query_text,
            index_name=vector_index,
            k=k * 2,  # Get more for fusion
            min_similarity=min_similarity
        )

        if vector_results.is_error:
            logger.warning(f"Vector search failed: {vector_results.error}")
            # Fallback to fulltext only
            return await self._fulltext_only_search(query_text, fulltext_index, k)

        # Step 2: Fulltext search
        fulltext_results = await self._fulltext_search(
            query_text=query_text,
            index_name=fulltext_index,
            k=k * 2
        )

        if fulltext_results.is_error:
            logger.warning(f"Fulltext search failed: {fulltext_results.error}")
            # Return vector results only
            return Result.ok(vector_results.value[:k])

        # Step 3: Reciprocal Rank Fusion
        fused_results = self._apply_rrf(
            vector_results=vector_results.value,
            fulltext_results=fulltext_results.value,
            vector_weight=vector_weight,
            fulltext_weight=fulltext_weight
        )

        # Step 4: Return top-k
        return Result.ok(fused_results[:k])

    def _apply_rrf(
        self,
        vector_results: list[VectorSearchResult],
        fulltext_results: list[VectorSearchResult],
        vector_weight: float,
        fulltext_weight: float
    ) -> list[VectorSearchResult]:
        """Apply Reciprocal Rank Fusion with weights."""
        # Build rank maps
        vector_ranks = {r.uid: idx + 1 for idx, r in enumerate(vector_results)}
        fulltext_ranks = {r.uid: idx + 1 for idx, r in enumerate(fulltext_results)}

        # Collect all unique UIDs
        all_uids = set(vector_ranks.keys()) | set(fulltext_ranks.keys())

        # Calculate RRF scores
        scored_results = []
        for uid in all_uids:
            # RRF score = Σ (weight / (k + rank))
            vector_score = vector_weight / (self.RRF_K + vector_ranks[uid]) if uid in vector_ranks else 0
            fulltext_score = fulltext_weight / (self.RRF_K + fulltext_ranks[uid]) if uid in fulltext_ranks else 0

            rrf_score = vector_score + fulltext_score

            # Get result object (prefer vector result for metadata)
            result = next((r for r in vector_results if r.uid == uid), None)
            if not result:
                result = next((r for r in fulltext_results if r.uid == uid), None)

            if result:
                # Store original scores for debugging
                result.metadata = result.metadata or {}
                result.metadata["vector_score"] = vector_ranks.get(uid)
                result.metadata["fulltext_score"] = fulltext_ranks.get(uid)
                result.metadata["rrf_score"] = rrf_score

                # Update similarity_score to RRF score
                result.similarity_score = rrf_score

                scored_results.append(result)

        # Sort by RRF score
        scored_results.sort(key=lambda x: x.similarity_score, reverse=True)

        return scored_results

    async def _fulltext_search(
        self,
        query_text: str,
        index_name: str,
        k: int
    ) -> Result[list[VectorSearchResult]]:
        """Execute fulltext search via Neo4j."""
        query = """
        CALL db.index.fulltext.queryNodes($index_name, $query_text)
        YIELD node, score
        RETURN node.uid AS uid,
               node.title AS title,
               node.content AS content,
               score
        ORDER BY score DESC
        LIMIT $k
        """

        try:
            result = await self.vector_search.backend.driver.execute_query(
                query,
                index_name=index_name,
                query_text=query_text,
                k=k
            )

            results = []
            for record in result.records:
                results.append(VectorSearchResult(
                    uid=record["uid"],
                    title=record["title"],
                    similarity_score=record["score"],
                    content=record.get("content"),
                    metadata={"source": "fulltext"}
                ))

            return Result.ok(results)

        except Exception as e:
            return Errors.database(f"Fulltext search failed: {str(e)}")

    async def _fulltext_only_search(
        self,
        query_text: str,
        index_name: str,
        k: int
    ) -> Result[list[VectorSearchResult]]:
        """Fallback to fulltext-only search."""
        logger.info("Using fulltext-only search (vector search unavailable)")
        return await self._fulltext_search(query_text, index_name, k)
```

### Trade-offs

**Pros:**
- Combines semantic and keyword matching
- Robust to query phrasing (vector) and exact terms (fulltext)
- Configurable weights (70/30 default in SKUEL)
- Graceful degradation (falls back to single method)

**Cons:**
- ~2x latency vs single search (30-60ms vs 10-30ms)
- Requires both vector and fulltext indexes
- More complex debugging

### When to Use

- ✅ User-facing search (best quality)
- ✅ When queries mix concepts and exact terms
- ✅ Production search endpoints
- ❌ Programmatic search (vector-only is faster)
- ❌ When only one index type exists

### Default: 70% Vector, 30% Fulltext

**Rationale:**
- Semantic understanding primary (most user queries are conceptual)
- Keyword matching secondary (exact terms still important)
- Validated via A/B testing in SKUEL

---

## Pattern 3: Semantic Relationship Inference

### Problem
Missing semantic connections in graph that aren't explicitly modeled.

### Solution
Find high-similarity entities via vector search, create `SEMANTICALLY_RELATED` relationships.

### Full Implementation

```python
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.services.unified_relationship_service import UnifiedRelationshipService
from core.models.shared_enums import RelationshipName
from core.result import Result
from core.errors import Errors
from datetime import datetime

class SemanticEnrichmentService:
    """Infer and create semantic relationships from embeddings."""

    DEFAULT_THRESHOLD = 0.85  # High threshold for quality
    BATCH_SIZE = 100

    def __init__(
        self,
        vector_search: Neo4jVectorSearchService,
        relationship_service: UnifiedRelationshipService,
        backend: Any
    ):
        self.vector_search = vector_search
        self.relationship_service = relationship_service
        self.backend = backend

    async def infer_semantic_relationships(
        self,
        uid: str,
        similarity_threshold: float = DEFAULT_THRESHOLD,
        max_relationships: int = 10
    ) -> Result[int]:
        """
        Find and create SEMANTICALLY_RELATED relationships.

        Args:
            uid: Source entity UID
            similarity_threshold: Minimum similarity (0.85 recommended)
            max_relationships: Maximum relationships to create

        Returns:
            Count of relationships created
        """
        # Step 1: Get entity embedding
        entity_result = await self._get_entity_with_embedding(uid)
        if entity_result.is_error:
            return entity_result

        entity = entity_result.value

        if not entity["embedding"]:
            return Errors.validation(f"Entity {uid} has no embedding")

        # Step 2: Find similar entities
        similar_result = await self.vector_search.search_by_vector(
            vector=entity["embedding"],
            index_name=entity["index_name"],
            k=max_relationships + 10,  # Get extras for filtering
            min_similarity=similarity_threshold
        )

        if similar_result.is_error:
            return similar_result

        # Step 3: Filter existing relationships
        candidates = await self._filter_existing_relationships(
            source_uid=uid,
            similar_entities=similar_result.value
        )

        # Step 4: Create relationships
        relationships_created = 0
        for candidate in candidates[:max_relationships]:
            create_result = await self._create_semantic_relationship(
                source_uid=uid,
                target_uid=candidate.uid,
                similarity_score=candidate.similarity_score
            )

            if not create_result.is_error:
                relationships_created += 1

        logger.info(f"Created {relationships_created} semantic relationships for {uid}")
        return Result.ok(relationships_created)

    async def enrich_all_entities(
        self,
        entity_type: str,
        index_name: str,
        similarity_threshold: float = DEFAULT_THRESHOLD
    ) -> Result[dict[str, int]]:
        """
        Batch process all entities of a type for semantic enrichment.

        Args:
            entity_type: Neo4j label (e.g., 'KnowledgeUnit')
            index_name: Vector index (e.g., 'ku_embeddings')
            similarity_threshold: Minimum similarity

        Returns:
            Stats: processed, relationships_created, errors
        """
        stats = {
            "processed": 0,
            "relationships_created": 0,
            "errors": 0,
            "skipped_no_embedding": 0
        }

        # Get entities needing enrichment
        query = """
        MATCH (n:$label)
        WHERE n.embedding IS NOT NULL
          AND NOT (n)-[:SEMANTICALLY_RELATED]-()
        RETURN n.uid AS uid
        LIMIT $batch_size
        """

        while True:
            result = await self.backend.driver.execute_query(
                query,
                label=entity_type,
                batch_size=self.BATCH_SIZE
            )

            if not result.records:
                break

            # Process batch
            for record in result.records:
                uid = record["uid"]

                infer_result = await self.infer_semantic_relationships(
                    uid=uid,
                    similarity_threshold=similarity_threshold
                )

                stats["processed"] += 1

                if infer_result.is_error:
                    stats["errors"] += 1
                    logger.error(f"Failed to enrich {uid}: {infer_result.error}")
                else:
                    stats["relationships_created"] += infer_result.value

            logger.info(f"Batch complete: {stats}")

        return Result.ok(stats)

    async def _get_entity_with_embedding(self, uid: str) -> Result[dict[str, Any]]:
        """Retrieve entity with embedding and determine index."""
        query = """
        MATCH (n {uid: $uid})
        RETURN n.embedding AS embedding,
               labels(n)[0] AS label
        """

        result = await self.backend.driver.execute_query(query, uid=uid)

        if not result.records:
            return Errors.not_found(f"Entity {uid} not found")

        record = result.records[0]

        # Determine index name from label
        label = record["label"]
        index_map = {
            "KnowledgeUnit": "ku_embeddings",
            "LearningSequence": "ls_embeddings",
            "LearningPath": "lp_embeddings",
            "User": "user_embeddings"
        }

        index_name = index_map.get(label)
        if not index_name:
            return Errors.validation(f"No vector index for label {label}")

        return Result.ok({
            "embedding": record["embedding"],
            "index_name": index_name,
            "label": label
        })

    async def _filter_existing_relationships(
        self,
        source_uid: str,
        similar_entities: list[VectorSearchResult]
    ) -> list[VectorSearchResult]:
        """Remove entities that already have semantic relationship."""
        # Get existing relationships
        query = """
        MATCH (source {uid: $uid})-[:SEMANTICALLY_RELATED]-(target)
        RETURN collect(target.uid) AS existing_uids
        """

        result = await self.backend.driver.execute_query(query, uid=source_uid)
        existing_uids = set(result.records[0]["existing_uids"])

        # Filter out self and existing
        candidates = [
            e for e in similar_entities
            if e.uid != source_uid and e.uid not in existing_uids
        ]

        return candidates

    async def _create_semantic_relationship(
        self,
        source_uid: str,
        target_uid: str,
        similarity_score: float
    ) -> Result[None]:
        """Create bidirectional SEMANTICALLY_RELATED relationship."""
        query = """
        MATCH (source {uid: $source_uid})
        MATCH (target {uid: $target_uid})
        MERGE (source)-[r:SEMANTICALLY_RELATED]-(target)
        SET r.similarity_score = $similarity_score,
            r.inferred = true,
            r.created_at = datetime()
        RETURN r
        """

        try:
            await self.backend.driver.execute_query(
                query,
                source_uid=source_uid,
                target_uid=target_uid,
                similarity_score=similarity_score
            )
            return Result.ok(None)
        except Exception as e:
            return Errors.database(f"Failed to create relationship: {str(e)}")
```

### Integration Point

**Add to `UnifiedIngestionService.ingest_single_ku()`:**

```python
async def ingest_single_ku(self, content: str, metadata: dict[str, Any]) -> Result[str]:
    # ... existing ingestion logic ...

    # Generate embedding
    embedding_result = await self.embeddings_service.ensure_embedding(
        uid=ku_uid,
        text=content,
        current_version="v2"
    )

    # Infer semantic relationships (non-blocking)
    if not embedding_result.is_error:
        asyncio.create_task(
            self.semantic_enrichment.infer_semantic_relationships(ku_uid)
        )

    return Result.ok(ku_uid)
```

### Trade-offs

**Pros:**
- Discovers non-obvious connections
- Enriches graph structure automatically
- Improves graph-enhanced RAG quality
- Emergent knowledge organization

**Cons:**
- Requires high similarity threshold (0.85+) to avoid noise
- Can create many relationships (storage cost)
- Slower ingestion if synchronous

### When to Use

- ✅ Post-ingestion enrichment
- ✅ Periodic batch jobs (weekly graph enhancement)
- ✅ When graph structure is sparse
- ❌ Real-time ingestion (adds latency)
- ❌ When relationships are well-defined manually

---

## Pattern 4: Learning-Aware Search (Personalized)

### Problem
Generic search ignores user's learning state - recommends mastered content or skips prerequisites.

### Solution
Boost based on mastery level (NOT_STARTED +15%, MASTERED -20%).

### Personalization Algorithm

**Boost formula:**
```
Final Score = Similarity Score × (1 + Boost)

Boost by mastery:
- NOT_STARTED: +15% (new material)
- IN_PROGRESS: +10% (current focus)
- REVIEW_NEEDED: +5% (reinforce)
- MASTERED: -20% (already learned)
```

### Full Implementation

```python
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.services.user.unified_user_context import UserContext
from core.models.shared_enums import MasteryLevel
from core.models.search.search_models import VectorSearchResult
from core.result import Result

class PersonalizedSearchService:
    """Learning-aware search with mastery-based boosting."""

    BOOST_MAP = {
        MasteryLevel.NOT_STARTED: 0.15,     # +15% boost
        MasteryLevel.IN_PROGRESS: 0.10,     # +10% boost
        MasteryLevel.REVIEW_NEEDED: 0.05,   # +5% boost
        MasteryLevel.MASTERED: -0.20,       # -20% penalty
    }

    def __init__(self, vector_search: Neo4jVectorSearchService):
        self.vector_search = vector_search

    async def learning_aware_search(
        self,
        query_text: str,
        user_context: UserContext,
        index_name: str = "ku_embeddings",
        k: int = 20,
        min_similarity: float = 0.6
    ) -> Result[list[VectorSearchResult]]:
        """
        Personalized search based on user's learning state.

        Args:
            query_text: Search query
            user_context: User's learning state (must be rich context)
            index_name: Vector index to search
            k: Results to return (gets 2x for reranking)
            min_similarity: Minimum base similarity

        Returns:
            Reranked results based on mastery
        """
        # Validate rich context
        try:
            user_context.require_rich_context("learning_aware_search")
        except ValueError as e:
            return Errors.validation(str(e))

        # Step 1: Get base vector search results (get more for reranking)
        search_result = await self.vector_search.search_by_text(
            query_text=query_text,
            index_name=index_name,
            k=k * 2,
            min_similarity=min_similarity
        )

        if search_result.is_error:
            return search_result

        # Step 2: Build mastery map from user context
        mastery_map = self._build_mastery_map(user_context)

        # Step 3: Apply learning-aware boost
        boosted_results = []
        for result in search_result.value:
            # Get mastery level for this entity
            mastery = mastery_map.get(result.uid, MasteryLevel.NOT_STARTED)

            # Calculate boost
            boost = self.BOOST_MAP.get(mastery, 0.0)

            # Apply boost to similarity score
            original_score = result.similarity_score
            boosted_score = original_score * (1 + boost)

            # Store boost metadata
            result.metadata = result.metadata or {}
            result.metadata["original_score"] = original_score
            result.metadata["mastery_level"] = mastery.value
            result.metadata["boost"] = boost
            result.metadata["boosted_score"] = boosted_score

            result.similarity_score = boosted_score
            boosted_results.append(result)

        # Step 4: Sort by boosted score and return top-k
        boosted_results.sort(key=lambda x: x.similarity_score, reverse=True)

        return Result.ok(boosted_results[:k])

    async def recommend_next_learning_steps(
        self,
        user_context: UserContext,
        k: int = 10
    ) -> Result[list[VectorSearchResult]]:
        """
        Recommend next KUs to learn based on current progress.

        Args:
            user_context: User's learning state (rich context required)
            k: Number of recommendations

        Returns:
            Personalized learning recommendations
        """
        # Validate rich context
        try:
            user_context.require_rich_context("recommend_next_learning_steps")
        except ValueError as e:
            return Errors.validation(str(e))

        # Get user's current KUs (in progress + recently completed)
        current_kus = (
            user_context.knowledge_units_in_progress +
            user_context.knowledge_units_recently_completed[:5]
        )

        if not current_kus:
            # No learning history - return beginner KUs
            return await self._recommend_beginner_kus(k)

        # Find semantically similar KUs to current learning
        recommendations = []
        for ku_uid in current_kus:
            similar_result = await self.vector_search.find_similar(
                uid=ku_uid,
                index_name="ku_embeddings",
                k=10
            )

            if not similar_result.is_error:
                recommendations.extend(similar_result.value)

        # Remove duplicates and already mastered
        mastered_uids = set(user_context.knowledge_units_mastered)
        seen_uids = set()
        unique_recommendations = []

        for rec in recommendations:
            if rec.uid not in seen_uids and rec.uid not in mastered_uids:
                seen_uids.add(rec.uid)

                # Boost based on prerequisites met
                prerequisite_score = await self._calculate_prerequisite_score(
                    rec.uid,
                    user_context
                )

                rec.similarity_score *= (1 + prerequisite_score)
                rec.metadata = rec.metadata or {}
                rec.metadata["prerequisite_score"] = prerequisite_score

                unique_recommendations.append(rec)

        # Sort by adjusted score
        unique_recommendations.sort(key=lambda x: x.similarity_score, reverse=True)

        return Result.ok(unique_recommendations[:k])

    def _build_mastery_map(self, user_context: UserContext) -> dict[str, MasteryLevel]:
        """Build UID → MasteryLevel map from user context."""
        mastery_map = {}

        # Map from context fields
        for uid in user_context.knowledge_units_mastered:
            mastery_map[uid] = MasteryLevel.MASTERED

        for uid in user_context.knowledge_units_in_progress:
            mastery_map[uid] = MasteryLevel.IN_PROGRESS

        # All other KUs are NOT_STARTED (default in boost calculation)

        return mastery_map

    async def _calculate_prerequisite_score(
        self,
        ku_uid: str,
        user_context: UserContext
    ) -> float:
        """
        Calculate boost based on prerequisite completion.

        Returns:
            0.0-0.3 boost (0% to +30%)
        """
        # Get prerequisites for this KU
        query = """
        MATCH (ku:KnowledgeUnit {uid: $uid})<-[:PREREQUISITE_FOR]-(prereq)
        RETURN collect(prereq.uid) AS prerequisite_uids
        """

        result = await self.vector_search.backend.driver.execute_query(query, uid=ku_uid)
        prerequisite_uids = result.records[0]["prerequisite_uids"]

        if not prerequisite_uids:
            return 0.0  # No prerequisites

        # Calculate completion percentage
        mastered = set(user_context.knowledge_units_mastered)
        completed = sum(1 for uid in prerequisite_uids if uid in mastered)
        completion_ratio = completed / len(prerequisite_uids)

        # Boost = completion_ratio * 0.3 (max 30% boost)
        return completion_ratio * 0.3

    async def _recommend_beginner_kus(self, k: int) -> Result[list[VectorSearchResult]]:
        """Recommend KUs with no prerequisites for beginners."""
        query = """
        MATCH (ku:KnowledgeUnit)
        WHERE NOT (ku)<-[:PREREQUISITE_FOR]-()
          AND ku.embedding IS NOT NULL
        RETURN ku.uid AS uid,
               ku.title AS title,
               1.0 AS score
        LIMIT $k
        """

        result = await self.vector_search.backend.driver.execute_query(query, k=k)

        recommendations = [
            VectorSearchResult(
                uid=record["uid"],
                title=record["title"],
                similarity_score=record["score"],
                metadata={"type": "beginner"}
            )
            for record in result.records
        ]

        return Result.ok(recommendations)
```

### Integration Point

**Add to `SearchRouter.faceted_search()`:**

```python
async def faceted_search(
    self,
    query: str,
    domains: list[EntityType],
    user_context: UserContext,
    k: int = 20
) -> Result[list[dict[str, Any]]]:
    # Use learning-aware search for curriculum domains
    if EntityType.KU in domains:
        personalized = await self.personalized_search.learning_aware_search(
            query_text=query,
            user_context=user_context,
            index_name="ku_embeddings",
            k=k
        )
        if not personalized.is_error:
            return personalized

    # Fallback to standard search
    return await self._standard_search(query, domains, k)
```

### Trade-offs

**Pros:**
- Tailored to user's learning journey
- Avoids recommending mastered content
- Boosts prerequisite-ready content
- Improves learning efficiency

**Cons:**
- Requires rich UserContext (expensive to build)
- Reranking adds ~10ms latency
- May miss serendipitous discoveries

### When to Use

- ✅ User-facing curriculum search
- ✅ "What should I learn next?" features
- ✅ Personalized dashboards
- ❌ Admin search (user-agnostic)
- ❌ When UserContext unavailable

---

## Pattern 5: Batch Embedding with Error Isolation

### Problem
One bad text in a batch fails entire embedding generation.

### Solution
Try batch first, fall back to individual processing on failure.

### Full Implementation

```python
from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
from core.result import Result
from core.errors import Errors
from typing import Any

class ResilientEmbeddingService:
    """Batch embedding with error isolation and retry logic."""

    OPTIMAL_BATCH_SIZE = 50

    def __init__(self, embeddings_service: Neo4jGenAIEmbeddingsService):
        self.embeddings_service = embeddings_service

    async def batch_embed_with_resilience(
        self,
        items: list[dict[str, Any]],
        text_key: str = "content"
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Batch embed with error isolation.

        Args:
            items: List of dicts with UID and text
            text_key: Key for text field in items

        Returns:
            (successes, failures) - lists of items
        """
        successes = []
        failures = []

        # Process in optimal batches
        for i in range(0, len(items), self.OPTIMAL_BATCH_SIZE):
            batch = items[i:i+self.OPTIMAL_BATCH_SIZE]

            # Try batch operation first
            batch_result = await self._try_batch_embedding(batch, text_key)

            if not batch_result.is_error:
                # Batch succeeded
                successes.extend(batch_result.value)
                logger.debug(f"Batch {i//self.OPTIMAL_BATCH_SIZE + 1}: {len(batch)} embeddings generated")
                continue

            # Batch failed - process individually for error isolation
            logger.warning(
                f"Batch {i//self.OPTIMAL_BATCH_SIZE + 1} failed: {batch_result.error}. "
                f"Processing {len(batch)} items individually."
            )

            batch_successes, batch_failures = await self._process_individually(batch, text_key)
            successes.extend(batch_successes)
            failures.extend(batch_failures)

        logger.info(f"Batch embedding complete: {len(successes)} success, {len(failures)} failed")
        return successes, failures

    async def _try_batch_embedding(
        self,
        batch: list[dict[str, Any]],
        text_key: str
    ) -> Result[list[dict[str, Any]]]:
        """Attempt batch embedding generation."""
        texts = [item[text_key] for item in batch]

        # Generate embeddings
        embeddings_result = await self.embeddings_service.generate_embeddings_batch(texts)

        if embeddings_result.is_error:
            return embeddings_result

        embeddings = embeddings_result.value

        # Attach embeddings to items
        enriched_items = []
        for item, embedding in zip(batch, embeddings):
            enriched_item = item.copy()
            enriched_item["embedding"] = embedding
            enriched_items.append(enriched_item)

        return Result.ok(enriched_items)

    async def _process_individually(
        self,
        batch: list[dict[str, Any]],
        text_key: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Process items individually after batch failure."""
        successes = []
        failures = []

        for item in batch:
            text = item[text_key]

            embedding_result = await self.embeddings_service.generate_embedding(text)

            if embedding_result.is_error:
                # Log error and mark as failure
                logger.error(f"Failed to embed {item.get('uid', 'unknown')}: {embedding_result.error}")
                failure_item = item.copy()
                failure_item["error"] = str(embedding_result.error)
                failures.append(failure_item)
            else:
                # Success - attach embedding
                success_item = item.copy()
                success_item["embedding"] = embedding_result.value
                successes.append(success_item)

        return successes, failures
```

### Usage Example

**Ingestion pipeline:**

```python
async def ingest_knowledge_units_from_directory(
    self,
    directory_path: str,
    user_uid: str
) -> Result[dict[str, Any]]:
    """Ingest KUs from markdown files with batch embedding."""

    # Step 1: Parse markdown files
    files = await self._parse_markdown_files(directory_path)

    # Step 2: Create KUs in graph
    ku_items = []
    for file in files:
        ku_result = await self.ku_service.create_knowledge_unit(
            request=KuRequest(title=file["title"], content=file["content"]),
            user_uid=user_uid
        )

        if not ku_result.is_error:
            ku_items.append({
                "uid": ku_result.value,
                "content": file["content"]
            })

    # Step 3: Batch embed with resilience
    successes, failures = await self.resilient_embedding.batch_embed_with_resilience(
        items=ku_items,
        text_key="content"
    )

    # Step 4: Store embeddings
    for item in successes:
        await self.embeddings_service.store_embedding(
            uid=item["uid"],
            embedding=item["embedding"],
            version="v2"
        )

    # Step 5: Return stats
    return Result.ok({
        "total": len(files),
        "kus_created": len(ku_items),
        "embeddings_generated": len(successes),
        "embedding_failures": len(failures),
        "failed_uids": [f["uid"] for f in failures]
    })
```

### Trade-offs

**Pros:**
- Resilient to individual failures
- Batch processing for speed
- Error isolation (one bad text doesn't fail all)
- Detailed failure tracking

**Cons:**
- Slower than pure batch (on failures)
- More complex error handling
- Retry logic adds latency

### When to Use

- ✅ Ingestion pipelines (many unknown texts)
- ✅ User-submitted content (unpredictable quality)
- ✅ When failure isolation is critical
- ❌ Clean, validated text (pure batch is faster)
- ❌ Real-time single-item processing

---

## Pattern 6: Graph-Enhanced RAG Context

### Problem
Vector search alone misses graph relationships (prerequisites, sequences, paths).

### Solution
Expand vector search results with 1-2 hop graph traversal for richer context.

**See SKILL.md, "RAG Workflows" section for full implementation.**

### Trade-offs

**Pros:**
- Richer context (discovers related knowledge)
- Better answers for complex questions
- Leverages graph structure

**Cons:**
- +100ms latency (graph traversal)
- More tokens (higher LLM cost)
- Risk of irrelevant context (noise)

### When to Use

- ✅ Complex questions requiring multi-faceted understanding
- ✅ When graph structure is rich
- ✅ Askesis-style synthesis tasks
- ❌ Simple factual questions
- ❌ Real-time chat (latency-sensitive)

---

## Pattern 7: Progressive Enhancement (Graceful Degradation)

### Problem
App should work without GenAI plugin enabled.

### Solution
Feature detection + fallback to keyword search.

### Full Implementation

```python
from core.config.unified_config import settings
from core.result import Result

class SearchOrchestrator:
    """Orchestrates search with progressive enhancement."""

    def __init__(
        self,
        vector_search: Neo4jVectorSearchService | None,
        keyword_search: KeywordSearchService
    ):
        self.vector_search = vector_search
        self.keyword_search = keyword_search
        self.genai_enabled = settings.genai.enabled

    async def search(
        self,
        query: str,
        index: str,
        k: int = 10
    ) -> Result[list[dict[str, Any]]]:
        """
        Search with progressive enhancement.

        Falls back to keyword search if GenAI unavailable.
        """
        # Try semantic search if enabled
        if self.genai_enabled and self.vector_search:
            semantic_result = await self._semantic_search(query, index, k)

            if not semantic_result.is_error:
                logger.info("Using semantic search")
                return semantic_result

            # Log degradation
            logger.warning(
                f"Semantic search failed: {semantic_result.error}. "
                "Falling back to keyword search."
            )

        # Fallback to keyword search (always available)
        logger.info("Using keyword search")
        return await self._keyword_search(query, index, k)

    async def _semantic_search(
        self,
        query: str,
        index: str,
        k: int
    ) -> Result[list[dict[str, Any]]]:
        """Semantic search via vector similarity."""
        return await self.vector_search.search_by_text(
            query_text=query,
            index_name=index,
            k=k
        )

    async def _keyword_search(
        self,
        query: str,
        index: str,
        k: int
    ) -> Result[list[dict[str, Any]]]:
        """Keyword search via fulltext index."""
        return await self.keyword_search.search(
            query_text=query,
            index_name=index,
            k=k
        )
```

### SKUEL Requirement

**All GenAI features MUST degrade gracefully:**
- Search → Keyword fallback
- Recommendations → Graph-only recommendations
- Embeddings → Skip (non-critical)
- RAG → Return error (no fallback for generation)

### When to Use

- ✅ Always (SKUEL architectural requirement)
- ✅ Production systems
- ✅ When GenAI is optional enhancement
- ❌ Never skip this pattern

---

**See SKILL.md for detailed documentation and QUICK_REFERENCE.md for fast lookups.**
